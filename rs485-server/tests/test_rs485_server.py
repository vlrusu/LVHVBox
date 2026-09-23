"""Offline HTTP/client integration tests; the serial boundary is faked."""
from contextlib import contextmanager
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Client'))
sys.path.insert(0, str(ROOT / 'rs485-server'))
import rs485 as com
from RS485Connection import RS485Connection
from rs485_server import Server, make_handler


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.rules = json.loads((ROOT / 'rs485-server/transformations.json').read_text())
        self.bus = Mock()
        self.bus.read_scalar.return_value = 2048
        self.opened = 0

        @contextmanager
        def factory():
            self.opened += 1
            yield self.bus

        self.telemetry = com.RS485(bus_factory=factory)
        self.telemetry.calibrations = {('A0', 'MN253'): (2, 1)}
        self.telemetry.__enter__()
        handler = make_handler(self.telemetry)
        handler.log_message = lambda *a: None
        self.server = Server(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.client = RS485Connection(port=self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.telemetry.close()

    def test_every_transformation_and_discovery_without_hardware(self):
        self.assertEqual(len(self.client.get_parameters()['parameters']), len(self.rules))
        self.assertEqual(self.client.get_health()['status'], 'ok')
        self.assertEqual(self.opened, 1)
        self.bus.read_scalar.assert_not_called()
        for name, rule in self.rules.items():
            with self.subTest(name=name):
                self.bus.reset_mock()
                result = self.client.read('MN253', name)
                self.assertEqual([c.args for c in self.bus.read_scalar.call_args_list],
                                 [(253, c) for c in com.command_ids(rule)])
                self.assertIsInstance(result['value'], (int, float))
        self.assertEqual(self.client.read(253, 'Flow')['value'], 4097)
        self.assertEqual(self.opened, 1)  # UART never reopened between reads

    def test_two_word_pressure_and_signed_temperature(self):
        self.bus.read_scalar.side_effect = [0x9400, 0x1F17, 0xFF9C]
        pressure = self.client.read(253, 'ILP_PRESSURE')
        self.assertEqual(pressure['raw'], 0x1F179400)
        self.assertAlmostEqual(pressure['value'], 994.947265625)
        self.assertFalse(pressure['atomic'])
        self.assertEqual(self.client.read(253, 'ILP_TEMP')['value'], -1)

    def test_errors_no_fabricated_values_and_recovery(self):
        for exc in (TimeoutError('no reply'), com.ROCError('sensor failed'), OSError('UART failed')):
            self.bus.read_scalar.side_effect = [0x9400, exc]
            with self.subTest(error=exc), self.assertRaisesRegex(RuntimeError, str(exc)):
                self.client.read(253, 'ILP_PRESSURE')
            self.assertFalse(self.telemetry.lock.locked())
        self.bus.read_scalar.side_effect = None
        self.bus.read_scalar.return_value = 0xBEEF
        self.assertEqual(self.client.read(253, 'DBG')['value'], 0xBEEF)

    def test_invalid_requests_and_missing_calibration_do_not_transmit(self):
        for path in ('/read?address=512&name=DBG', '/read?address=x&name=DBG',
                     '/read?address=253&name=BAD', '/read?address=254&name=Flow',
                     '/read?address=253&name=DBG&name=ID',
                     '/read?address=253&name=DBG&command=42'):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                urlopen(f'http://127.0.0.1:{self.server.server_port}{path}')
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()
        self.assertEqual(self.opened, 1)
        self.bus.read_scalar.assert_not_called()

    def test_overlapping_clients_rejected_without_interleaving_pressure(self):
        entered, release = threading.Event(), threading.Event()
        results = []
        def read(address, command):
            if command == 41:
                entered.set()
                self.assertTrue(release.wait(5))
                return 0x9400
            return 0x1F17
        self.bus.read_scalar.side_effect = read
        worker = threading.Thread(target=lambda: results.append(self.client.read(253, 'ILP_PRESSURE')))
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertTrue(self.client.get_health()['busy'])
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                self.client.read(101, 'DBG')
            self.assertEqual(self.opened, 1)
        finally:
            release.set()
            worker.join(5)
        self.assertEqual(results[0]['raw'], 0x1F179400)

    def run_cli(self, *commands):
        argv = [sys.executable, str(ROOT / 'Client/Client.py'), 'localhost',
                '--rs485-remote-port', str(self.server.server_port),
                '--header', '/does-not-exist', '--remote-port', '1']
        for command in commands:
            argv += ['-c', command]
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(argv, cwd=directory, text=True, capture_output=True, timeout=20)

    def test_actual_client_cli_without_lvhv_server_or_header(self):
        self.bus.read_scalar.return_value = 0xBEEF
        result = self.run_cli('rs485_list', 'rs485_read MN253 DBG')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('ILP_PRESSURE [hPa]', result.stdout)
        self.assertIn('MN253 DBG', result.stdout)
        self.assertIn('0x0000beef', result.stdout)
        failed = self.run_cli('rs485_read 253 not_a_variable')
        self.assertEqual(failed.returncode, 1)
        self.assertIn('unknown parameter', failed.stdout)

    def test_existing_lvhv_dispatch_still_connects_lazily(self):
        with patch.object(sys, 'argv', ['Client.py']), patch('readline.read_history_file'):
            scope = runpy.run_path(str(ROOT / 'Client/Client.py'), run_name='client_test')
        process = scope['process_command']
        namespace = process.__globals__
        connection = Mock()
        with patch.dict(namespace, {'connect_to_host': Mock(return_value=connection),
                                   'read_commands': Mock(), 'execute_command': Mock()}):
            process('readMonV48 0')
            namespace['connect_to_host'].assert_called_once_with('localhost')
            namespace['execute_command'].assert_called_once()
            self.assertIs(namespace['execute_command'].call_args.args[0], connection)


class BusLifecycleTests(unittest.TestCase):
    def test_open_bus_timeout_holdoff_and_cleanup_across_requests(self):
        # Exercise the real context manager and persisted BusSession with fake
        # hardware; the second request cannot skip the first response window.
        import types
        lines, uart = Mock(), Mock()
        lines.__enter__ = Mock(return_value=lines)
        lines.__exit__ = Mock(return_value=False)
        uart.__enter__ = Mock(return_value=uart)
        uart.__exit__ = Mock(return_value=False)
        gpio = types.SimpleNamespace(request_lines=Mock(return_value=lines), LineSettings=Mock())
        enums = types.SimpleNamespace(Direction=types.SimpleNamespace(OUTPUT=1),
                                      Value=types.SimpleNamespace(INACTIVE=0, ACTIVE=1))
        serial = types.SimpleNamespace(Serial=Mock(return_value=uart), EIGHTBITS=8,
                                       PARITY_NONE='N', STOPBITS_ONE=1)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            with patch.dict(sys.modules, {'serial': serial, 'gpiod': gpio, 'gpiod.line': enums}), \
                    patch.object(com, 'default_lock_path', return_value=state), \
                    patch.object(com.time, 'time', return_value=100), \
                    patch.object(com.time, 'sleep') as sleep:
                with self.assertRaises(TimeoutError):
                    with com.open_bus() as bus:
                        bus.session.reserve(7.1)
                        raise TimeoutError('injected')
                lines.set_value.assert_called_with(24, 0)
                with com.open_bus() as bus:
                    sleep.assert_called_once()
                    self.assertAlmostEqual(sleep.call_args.args[0], 7.1)
                    bus.session.complete()
                self.assertEqual(uart.__exit__.call_count, 2)
                self.assertEqual(lines.__exit__.call_count, 2)


if __name__ == '__main__':
    unittest.main()
