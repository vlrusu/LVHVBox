"""Discovery timing/ownership tests use a simulated UART; never touch hardware."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rs485 as com
import rs485_server
from test_rs485 import FakeClock, UART, response
import test_rs485_server as server_tests


class DiscoveryTests(unittest.TestCase):
    @contextmanager
    def device(self, reply):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            clock, events, packets = FakeClock(), [], []
            def receive(request):
                packets.append((clock.now, request))
                return reply(request)
            uart = UART(clock, receive, events)
            @contextmanager
            def factory():
                with com.BusSession(path) as session:
                    yield com.PiBus(uart, events.append, session)
            with patch.object(com.time, 'time', lambda: 100 + clock.now), \
                    patch.object(com.time, 'monotonic', clock.monotonic), \
                    patch.object(com.time, 'sleep', clock.sleep), patch('builtins.print'):
                with com.RS485(bus_factory=factory) as device:
                    yield device, clock, packets, uart, path

    def test_all_301_missing_fast_no_cpu_requests_or_retries(self):
        with self.device(lambda req: b'') as (device, clock, packets, uart, path):
            result = device.discover()
            self.assertEqual(result['no_response'], list(range(301)))
            self.assertEqual(result['addresses'], [])
            self.assertEqual(len(packets), 301)
            self.assertLess(clock.now, 18)
            self.assertGreater(clock.now, 16)
            for i, (sent, packet) in enumerate(packets):
                self.assertEqual((packet.kind, packet.command, packet.payload, packet.roc), (3, 2, b'', i))
                if i:
                    self.assertGreaterEqual(sent - packets[i-1][0], 0.0549)
            # The final missing reply retains the short guard even at scan end.
            self.assertGreater(json.loads(path.read_text())['not_before'], 100 + clock.now)
            snapshot = device.panels()
            snapshot['addresses'].append(999)
            self.assertEqual(device.panels()['addresses'], [])

    def test_matching_identity_only_and_cached_inventory(self):
        def reply(req):
            if req.roc == 2:
                return b''
            return response(req, kind=4, raw=req.roc if req.roc == 1 else 99)
        with self.device(reply) as (device, clock, packets, uart, path):
            self.assertFalse(device.panels()['scanned'])
            result = device.discover(1, 3)
            self.assertEqual(result['panels'], ['MN001'])
            self.assertEqual(result['no_response'], [2])
            self.assertEqual(result['errors'][0]['address'], 3)
            before = len(packets)
            self.assertEqual(device.panels(), result)
            self.assertEqual(len(packets), before)
            self.assertFalse(device.lock.locked())

    def test_legacy_timeout_and_pending_window_are_not_shortened(self):
        with self.device(lambda req: b'') as (device, clock, packets, uart, path):
            with self.assertRaises(com.ResponseTimeout):
                device.read(269, 'ID')
            self.assertGreaterEqual(clock.now, 6)
            device.discover(269, 269)
            self.assertGreaterEqual(packets[1][0] - packets[0][0], 7.099)
            with self.assertRaises(com.ResponseTimeout):
                device.read(269, 'ID')
            self.assertGreaterEqual(packets[2][0] - packets[1][0], .0549)
            self.assertEqual(device._bus.timeout, 6)

    def test_reopen_honors_persisted_short_reply_guard(self):
        with self.device(lambda req: b'') as (device, clock, packets, uart, path):
            device.discover(0, 0)
            not_before = json.loads(path.read_text())['not_before']
            device.close()
            with com.BusSession(path):
                self.assertGreaterEqual(100 + clock.now, not_before)

    def test_short_window_starts_only_after_uart_has_drained(self):
        with self.device(lambda req: b'') as (device, clock, packets, uart, path):
            def drain():
                self.assertGreater(json.loads(path.read_text())['not_before'], 100 + clock.now + 6)
                clock.sleep(0.020)
            device._bus.drain = drain
            device.discover(269, 269)
            self.assertGreaterEqual(clock.now, .070)
            remaining = json.loads(path.read_text())['not_before'] - (100 + clock.now)
            self.assertAlmostEqual(remaining, .005, places=5)

    def test_uart_timeout_aborts_without_overwriting_last_scan(self):
        with self.device(lambda req: response(req, kind=4, raw=req.roc)) as (device, clock, packets, uart, path):
            previous = device.discover(1, 1)
            with patch.object(uart, 'write', side_effect=TimeoutError('write timed out')):
                with self.assertRaisesRegex(TimeoutError, 'write timed out'):
                    device.discover(0, 300)
            self.assertEqual(device.panels(), previous)
            self.assertFalse(device.lock.locked())
            self.assertGreater(json.loads(path.read_text())['not_before'], 100 + clock.now + 6)

    def test_late_or_corrupt_responses_are_not_discovered(self):
        def reply(req):
            stale = response(req, kind=4, raw=req.roc, transaction=(req.transaction-1)&65535)
            corrupt = bytearray(response(req, kind=4, raw=req.roc))
            corrupt[-3] ^= 1
            return stale + corrupt
        with self.device(reply) as (device, clock, packets, uart, path):
            result = device.discover(269, 269)
            self.assertEqual(result['no_response'], [269])
            self.assertEqual(result['addresses'], [])

    def test_invalid_ranges_busy_bus_and_unsafe_fast_commands_never_transmit(self):
        with self.device(lambda req: b'') as (device, clock, packets, uart, path):
            for start, end in [(-1, 300), (0, 512), (4, 3), (True, 1)]:
                with self.assertRaises(ValueError):
                    device.discover(start, end)
            with device.lock:
                with self.assertRaises(com.BusyError):
                    device.discover()
                self.assertFalse(device.panels()['scanned'])
            for kind, cmd, payload in [(1, 252, b''), (3, 1, b'GOLD'), (3, 2, b'x')]:
                with self.assertRaises(ValueError):
                    device._bus._exchange(com.Packet(kind, 269, 1, cmd, payload), 4, discovery=True)
            self.assertEqual(packets, [])


class DiscoveryHTTPTests(unittest.TestCase):
    setUp = server_tests.ServerTests.setUp
    tearDown = server_tests.ServerTests.tearDown
    run_cli = server_tests.ServerTests.run_cli

    def test_scan_http_client_and_cached_panels(self):
        self.assertFalse(self.client.get_panels()['scanned'])
        self.bus.read_panel_id.side_effect = lambda address, **kw: address
        result = self.client.discover('MN268', 'MN270')
        self.assertEqual(result['addresses'], [268, 269, 270])
        self.assertEqual(self.client.get_panels(), result)
        self.assertTrue(all(c.kwargs == {'discovery': True} for c in self.bus.read_panel_id.call_args_list))
        self.bus.read_panel_id.reset_mock()
        output = self.run_cli('rs485_panels')
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn('MN269', output.stdout)
        self.bus.read_panel_id.assert_not_called()
        output = self.run_cli('rs485_discover 269 269')
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn('1 panels', output.stdout)
        self.bus.read_scalar.assert_not_called()
        self.bus.control.assert_not_called()

    def test_bad_range_and_busy_do_not_probe(self):
        for path in ['/discover?start=1', '/discover?start=5&end=4',
                     '/discover?start=0&end=512', '/discover?start=0&start=1&end=2',
                     '/discover?start=0&end=1&timeout=0.01']:
            with self.assertRaises(HTTPError) as error:
                urlopen(f'http://127.0.0.1:{self.server.server_port}'+path)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        with self.telemetry.lock:
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                self.client.discover()
        self.bus.read_panel_id.assert_not_called()


class StartupTests(unittest.TestCase):
    def test_startup_default_skip_and_config_check(self):
        for args, count in [([], 1), (['--no-discovery'], 0), (['--check-config'], 0)]:
            with self.subTest(args=args), patch.object(rs485_server, 'RS485') as cls, \
                    patch.object(rs485_server, 'Server'), patch.object(rs485_server.signal, 'signal'), \
                    patch('builtins.print'):
                cls.return_value.discover.return_value = {'panels': []}
                cls.return_value.parameters.return_value = {'parameters': []}
                self.assertEqual(rs485_server.main(args), 0)
                self.assertEqual(cls.return_value.discover.call_count, count)
                if '--check-config' in args:
                    cls.return_value.__enter__.assert_not_called()


if __name__ == '__main__':
    unittest.main()
