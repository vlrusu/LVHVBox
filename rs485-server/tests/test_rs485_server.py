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
from urllib.request import Request, urlopen

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

    def test_direct_tvs_http_conversions_and_client_commands(self):
        names = ['ROC_RAIL_1V','ROC_RAIL_1.8V','ROC_RAIL_2.5V','ROC_TEMP']
        raws = [8000,14400,20000,4800]
        self.bus.read_direct.side_effect = lambda address, cmd: raws[cmd-3]
        advertised = [item['name'] for item in self.client.get_parameters()['parameters']
                      if item.get('direct_command') is not None]
        self.assertEqual(advertised, names)
        for name, raw, cmd in zip(names, raws, range(3,7)):
            result = self.client.direct_read('MN253',name)
            self.assertEqual(result['raw'],raw)
            self.assertAlmostEqual(result['value'],raw/16-273.15 if cmd==6 else raw/8)
            self.assertEqual(result['source'],'FPGA TVS')
            self.assertEqual(result['commands'],[cmd])
        self.bus.read_direct.reset_mock()
        result = self.run_cli('rs485_direct_read MN253')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for name in names:
            self.assertIn(name,result.stdout)
        self.assertEqual([call.args for call in self.bus.read_direct.call_args_list],
                         [(253,cmd) for cmd in range(3,7)])
        self.bus.read_direct.reset_mock()
        result = self.run_cli('rs485_direct_read MN253 ROC_TEMP ROC_RAIL_1.8V')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual([call.args for call in self.bus.read_direct.call_args_list],[(253,6),(253,4)])
        self.bus.read_scalar.assert_not_called()
        self.bus.control.assert_not_called()
        # Original names/commands still use the CPU path.
        for name, cmd in zip(names,range(28,32)):
            self.assertEqual(self.client.read(253,name)['commands'],[cmd])
        self.assertEqual([call.args for call in self.bus.read_scalar.call_args_list],
                         [(253,cmd) for cmd in range(28,32)])

    def test_direct_tvs_rejects_invalid_busy_and_stale_without_fallback(self):
        for path in ('/direct-read?address=512&name=ROC_TEMP',
                     '/direct-read?address=253&name=DBG',
                     '/direct-read?address=253&name=ROC_TEMP&name=ROC_RAIL_1V',
                     '/direct-read?address=253&name=ROC_TEMP&command=1'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(f'http://127.0.0.1:{self.server.server_port}'+path)
            self.assertEqual(caught.exception.code,400)
            caught.exception.close()
        with self.telemetry.lock:
            with self.assertRaisesRegex(RuntimeError,'busy'):
                self.client.direct_read(253,'ROC_TEMP')
        self.bus.read_direct.assert_not_called()
        for error in (com.ROCError('FPGA TVS sample unavailable or stale'),TimeoutError('no reply')):
            self.bus.read_direct.side_effect = error
            with self.assertRaisesRegex(RuntimeError,str(error)):
                self.client.direct_read(253,'ROC_TEMP')
            self.assertFalse(self.telemetry.lock.locked())
        self.assertEqual(self.bus.read_direct.call_count,2)
        self.bus.read_scalar.assert_not_called()
        self.bus.control.assert_not_called()

    def test_fpga_panel_id_http_and_actual_client(self):
        self.bus.read_panel_id.return_value = 253
        result = self.client.panel_id('MN253')
        self.assertEqual(result, {'address':253,'panel_id':253,'panel':'MN253','source':'FPGA cached NVM'})
        self.bus.read_panel_id.assert_called_once_with(253)
        self.bus.read_panel_id.reset_mock()
        result = self.run_cli('rs485_panel_id MN253')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('MN253 panel ID: 253',result.stdout)
        self.bus.read_panel_id.assert_called_once_with(253)
        self.bus.control.assert_not_called()
        self.bus.read_scalar.assert_not_called()
        for path in ('/panel-id?address=512','/panel-id?address=-1',
                     '/panel-id?address=253&address=254','/panel-id?address=253&name=ID'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(f'http://127.0.0.1:{self.server.server_port}'+path)
            self.assertEqual(caught.exception.code,400)
            caught.exception.close()
        self.bus.read_panel_id.assert_called_once_with(253)

    def test_user_initiated_recovery_and_status(self):
        self.bus.control.return_value = 0
        self.client.get_health()
        self.client.get_parameters()
        self.client.read(253, 'DBG')
        self.bus.control.assert_not_called()  # never activated by telemetry
        result = self.client.recovery('MN253', activate=True)
        self.assertTrue(result['accepted'])
        self.assertFalse(result['boot_verified'])
        self.assertEqual(result['image_index'], 0)
        self.bus.control.assert_called_once_with(253, activate=True)
        self.bus.control.reset_mock()
        self.bus.control.return_value = 0x150E
        self.assertTrue(self.client.recovery('MN253')['failed'])
        self.bus.control.assert_called_once_with(253, activate=False)
        self.bus.control.return_value = 0
        self.bus.control.reset_mock()
        cli_result = self.run_cli('rs485_recover_golden MN253')
        self.assertEqual(cli_result.returncode, 0, cli_result.stderr + cli_result.stdout)
        self.assertIn('boot_verified', cli_result.stdout)
        self.bus.control.assert_called_once_with(253, activate=True)

    def test_recovery_requires_explicit_post_and_valid_target(self):
        base = f'http://127.0.0.1:{self.server.server_port}'
        invalid = [base+'/recover-golden?address=253']
        for body in ({'address': 253}, {'address': 253, 'action': 'read'},
                     {'address': 253, 'action': 'activate-golden', 'index': 2},
                     {'address': 0, 'action': 'activate-golden'},
                     {'address': True, 'action': 'activate-golden'}):
            invalid.append(Request(base+'/recover-golden', data=json.dumps(body).encode(), method='POST'))
        for request in invalid:
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertIn(caught.exception.code, (400,404))
            caught.exception.close()
        self.bus.control.assert_not_called()
        self.bus.control.side_effect = TimeoutError('Recovery outcome unknown; no automatic retry.')
        with self.assertRaisesRegex(RuntimeError,'outcome unknown'):
            self.client.recovery(253, activate=True)
        self.bus.control.assert_called_once_with(253, activate=True)

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

    def test_client_address_only_reads_all_advertised_variables(self):
        # An extra server-only variable proves discovery does not use a local
        # hard-coded catalog. Include pasted nonbreaking whitespace in input.
        self.telemetry.rules['SERVER_ONLY'] = {'cmdid': 17, 'expression': 'x'}
        result = self.run_cli('rs485_read\u00a0MN253\u00a0')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        names = [line.split()[1] for line in result.stdout.splitlines() if line.startswith('MN253 ')]
        self.assertEqual(names, list(self.telemetry.rules))
        self.assertEqual([call.args for call in self.bus.read_scalar.call_args_list],
                         [(253, command) for rule in self.telemetry.rules.values()
                          for command in com.command_ids(rule)])


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
