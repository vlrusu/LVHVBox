#!/usr/bin/env python3
"""On-demand ROC telemetry HTTP service with exclusive RS485 bus ownership."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import signal
import sys
import threading
from urllib.parse import parse_qs, urlsplit

from rs485 import RS485, BusyError, ROCError


def make_handler(telemetry):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def send_json(self, status, payload):
            body = json.dumps(payload, allow_nan=False).encode() + b'\n'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # hardware operation and cleanup have already finished

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                params = parse_qs(url.query, keep_blank_values=True, max_num_fields=4)
                if url.path == '/health' and not params:
                    result = {'status': 'ok', 'protocol': 'RS485 v2',
                              'busy': telemetry.lock.locked()}
                elif url.path == '/parameters' and not params:
                    result = telemetry.parameters()
                elif url.path == '/read':
                    if set(params) != {'address', 'name'} or any(len(v) != 1 for v in params.values()):
                        raise ValueError('use /read?address=59&name=ROC_TEMP')
                    result = telemetry.read(int(params['address'][0]), params['name'][0])
                else:
                    self.send_json(404, {'error': 'unknown endpoint'})
                    return
                self.send_json(200, result)
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
    parser.add_argument('--check-config', action='store_true', help='Validate files without GPIO/UART or HTTP')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('invalid HTTP port')
    try:
        telemetry = RS485(args.rules, args.calibrations, port=args.serial_port,
                          gpiochip=args.gpiochip, dir_pin=args.dir_pin,
                          timeout=args.timeout, debug=args.debug)
        if args.check_config:
            print(json.dumps(telemetry.parameters(), indent=2))
            return 0
        # Exit order matters: drain HTTP handlers before releasing UART/GPIO.
        with telemetry, Server((args.bind, args.port), make_handler(telemetry)) as server:
            def stop(signum, frame):
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            print(f'rs485-server listening on {args.bind}:{server.server_port}', flush=True)
            server.serve_forever()
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        print(f'rs485-server: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
