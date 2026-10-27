#!/usr/bin/env python3
"""On-demand ROC telemetry HTTP service with exclusive RS485 bus ownership."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import math
import select
import signal
import socket
import sys
import threading
from urllib.parse import parse_qs, urlsplit

from rs485 import RS485, BusyError, ROCError
from discovery_history import DiscoveryHistory, DiscoveryNotifier, PowerReader
from power_on_discovery import PowerOnDiscovery
from fair_queue import QueueFull, QueueExpired, QueueCancelled, QueueClosed


def run_discovery(telemetry, history=None, power_reader=None, start=0, end=300, *, startup=False):
    def powered():
        if power_reader is None:
            return None
        try:
            return any(v >= 2 for v in power_reader.voltages())
        except Exception:
            logging.error('Cannot verify V6 during discovery; preserving previous discovery list')
            return None
    before = powered() if history is not None else None
    inventory = telemetry.discover(start, end)
    if history is not None:
        after = powered()
        state = True if before is True and after is True else False if before is False or after is False else None
        try:
            history.record(inventory, state, startup=startup)
        except (OSError, ValueError, KeyError):
            logging.exception('Cannot persist discovery history; telemetry remains available')
    return inventory


def make_handler(telemetry, history=None, power_reader=None):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def disconnected(self):
            try:
                return bool(select.select([self.connection], [], [], 0)[0]) and \
                    self.connection.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b''
            except BlockingIOError:
                return False
            except OSError:
                return True

        def request_context(self):
            client = self.headers.get('X-RS485-Client', 'interactive')
            timeout = float(self.headers.get('X-RS485-Timeout', '30'))
            if not math.isfinite(timeout) or not 0 < timeout <= 120:
                raise ValueError('X-RS485-Timeout must be in (0, 120] seconds')
            return telemetry.queue.request(client, timeout, self.disconnected)

        def send_json(self, status, payload):
            body = json.dumps(payload, allow_nan=False).encode() + b'\n'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            if status == 429:
                self.send_header('Retry-After', '1')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # hardware operation and cleanup have already finished

        def do_POST(self):
            try:
                with self.request_context():
                    self.handle_POST()
            except (ValueError, TypeError) as exc:
                self.send_json(400, {'error': str(exc)})

        def handle_POST(self):
            # Mutating action has no GET route, arbitrary index, or retry loop.
            try:
                if self.path != '/recover-golden':
                    self.send_json(404, {'error': 'unknown endpoint'})
                    return
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Content-Type must be application/json')
                if self.headers.get('Transfer-Encoding'):
                    raise ValueError('chunked requests are not supported')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 128:
                    raise ValueError('expected a short JSON request')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {'address', 'action'} or body['action'] != 'activate-golden':
                    raise ValueError('expected address and action=activate-golden')
                self.send_json(200, telemetry.recovery(body['address'], activate=True))
            except QueueFull as exc:
                self.send_json(429, {'error': str(exc)})
            except (QueueExpired, QueueCancelled) as exc:
                self.send_json(408, {'error': str(exc)})
            except QueueClosed as exc:
                self.send_json(503, {'error': str(exc)})
            except BusyError as exc:
                self.send_json(409, {'error': str(exc)})
            except TimeoutError as exc:
                self.send_json(504, {'error': str(exc)})
            except ROCError as exc:
                self.send_json(502, {'error': str(exc)})
            except (ValueError, TypeError) as exc:
                self.send_json(400, {'error': str(exc)})
            except (OSError, RuntimeError, ImportError) as exc:
                self.send_json(503, {'error': str(exc)})

        def do_GET(self):
            try:
                with self.request_context():
                    self.handle_GET()
            except (ValueError, TypeError) as exc:
                self.send_json(400, {'error': str(exc)})

        def handle_GET(self):
            try:
                url = urlsplit(self.path)
                params = parse_qs(url.query, keep_blank_values=True, max_num_fields=4)
                if url.path == '/health' and not params:
                    result = {'status': 'ok', 'protocol': 'RS485 v2',
                              'busy': telemetry.lock.locked(), 'queue': telemetry.queue.status()}
                elif url.path == '/parameters' and not params:
                    result = telemetry.parameters()
                elif url.path == '/panels' and not params:
                    result = telemetry.panels()
                    if history is not None:
                        result['discovery_history'] = history.status()
                elif url.path == '/discover':
                    if not params:
                        result = run_discovery(telemetry, history, power_reader)
                    elif set(params) == {'start', 'end'} and all(len(v) == 1 for v in params.values()):
                        result = run_discovery(telemetry, history, power_reader, int(params['start'][0]), int(params['end'][0]))
                    else:
                        raise ValueError('use /discover or /discover?start=0&end=300')
                elif url.path == '/panel-id':
                    if set(params) != {'address'} or len(params['address']) != 1:
                        raise ValueError('use /panel-id?address=253')
                    result = telemetry.panel_id(int(params['address'][0]))
                elif url.path == '/recovery-status':
                    if set(params) != {'address'} or len(params['address']) != 1:
                        raise ValueError('use /recovery-status?address=253')
                    result = telemetry.recovery(int(params['address'][0]))
                elif url.path in ('/read', '/direct-read'):
                    if set(params) != {'address', 'name'} or any(len(v) != 1 for v in params.values()):
                        raise ValueError('use ' + url.path + '?address=253&name=ROC_TEMP')
                    read = telemetry.direct_read if url.path == '/direct-read' else telemetry.read
                    result = read(int(params['address'][0]), params['name'][0])
                else:
                    self.send_json(404, {'error': 'unknown endpoint'})
                    return
                self.send_json(200, result)
            except QueueFull as exc:
                self.send_json(429, {'error': str(exc)})
            except (QueueExpired, QueueCancelled) as exc:
                self.send_json(408, {'error': str(exc)})
            except QueueClosed as exc:
                self.send_json(503, {'error': str(exc)})
            except BusyError as exc:
                self.send_json(409, {'error': str(exc)})
            except TimeoutError as exc:
                self.send_json(504, {'error': str(exc)})
            except ROCError as exc:
                self.send_json(502, {'error': str(exc)})
            except (ValueError, ArithmeticError, KeyError) as exc:
                self.send_json(400, {'error': str(exc)})
            except (OSError, RuntimeError, ImportError) as exc:
                self.send_json(503, {'error': str(exc)})
            except Exception:
                logging.exception('Unhandled RS485 request failure')
                self.send_json(500, {'error': 'internal server error'})

    return Handler


class Server(ThreadingHTTPServer):
    # Finish the active serial operation and release DE before process exit.
    daemon_threads = False
    block_on_close = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=12004, help='HTTP listen port')
    parser.add_argument('--serial-port', default='/dev/ttyAMA0')
    parser.add_argument('--gpiochip', default='/dev/gpiochip0')
    parser.add_argument('--dir-pin', type=int, default=24)
    parser.add_argument('--timeout', type=float, default=6.0)
    parser.add_argument('--rules', help='Transformation JSON (default: beside this script)')
    parser.add_argument('--calibrations', help='Flow CSV (default: beside this script)')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--discovery-history', default='/var/lib/rs485-server/discovery-history.json')
    parser.add_argument('--commands', default='/etc/mu2e-tracker-lvhv-tools/commands.h')
    parser.add_argument('--power-on-socket', default='/run/rs485-server/power-on.sock')
    parser.add_argument('--power-on-delay', type=float, default=5,
                        help='Boot delay before discovery after all-channel LV powerOn (seconds)')
    parser.add_argument('--no-discovery', action='store_true',
                        help='Skip the default FPGA panel-ID startup scan of addresses 0..300')
    parser.add_argument('--check-config', action='store_true', help='Validate files without GPIO/UART or HTTP')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('invalid HTTP port')
    if not math.isfinite(args.power_on_delay) or args.power_on_delay < 0:
        parser.error('power-on delay must be finite and nonnegative')
    try:
        telemetry = RS485(args.rules, args.calibrations, port=args.serial_port,
                          gpiochip=args.gpiochip, dir_pin=args.dir_pin,
                          timeout=args.timeout, debug=args.debug)
        if args.check_config:
            print(json.dumps(telemetry.parameters(), indent=2))
            return 0
        history = notifier = power_reader = None
        try:
            history = DiscoveryHistory(args.discovery_history)
            power_reader = PowerReader(args.commands)
        except (OSError, ValueError, KeyError):
            logging.exception('Discovery history unavailable; continuing telemetry without comparison')
        try:
            notifier = DiscoveryNotifier()
        except ValueError:
            logging.error('Discovery notification credentials unavailable; events will remain queued')
        notification_stop = threading.Event()
        def background_discovery(*, startup=False):
            with telemetry.queue.request('discovery', 120, notification_stop.is_set):
                return run_discovery(telemetry, history, power_reader, startup=startup)
        # Exit order matters: drain HTTP handlers before releasing UART/GPIO.
        with telemetry, Server((args.bind, args.port), make_handler(telemetry, history, power_reader)) as server, \
                PowerOnDiscovery(args.power_on_socket,
                                 background_discovery,
                                 power_reader, args.power_on_delay) as power_events:
            def stop(signum, frame):
                telemetry.queue.close()
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            if not args.no_discovery:
                try:
                    inventory = background_discovery(startup=True)
                    print('Startup discovery: ' + json.dumps(inventory), flush=True)
                except (OSError, RuntimeError):
                    logging.exception('Startup discovery failed; server will remain available')
            print(f'rs485-server listening on {args.bind}:{server.server_port}', flush=True)
            power_events.start()
            if history is not None and notifier is not None:
                threading.Thread(target=history.notification_loop,
                                 args=(notifier, notification_stop, power_reader), daemon=True).start()
            try:
                server.serve_forever()
            finally:
                notification_stop.set()
                telemetry.queue.close()
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        print(f'rs485-server: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
