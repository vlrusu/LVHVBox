"""Shared codec and real protection-client adapters; fake sockets, no hardware."""
import ctypes
import ast
import __future__
import importlib.util
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Client'))
sys.path.insert(0, str(ROOT / 'common'))
import lvhv_protocol as protocol
from MessagingConnection import MessagingConnection


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


watch = load('shared_protocol_watch', 'network-watch/network-watch.py')
roc = load('shared_protocol_roc', 'roc-temperature-monitor/roc_temperature_monitor.py')
# Only notification transport is stubbed; nothing can send real notifications.
with patch.dict(sys.modules, requests=types.ModuleType('requests')):
    alerts = load('shared_protocol_alerts', 'i2c-sensor-alerts/i2c-sensor-alerts.py')
# Import only; no real GPIO implementation can be reached by these tests.
gpio = types.ModuleType('gpiod')
gpio.line = types.ModuleType('gpiod.line')
gpio.line.Bias = gpio.line.Direction = gpio.line.Edge = object()
with patch.dict(sys.modules, {'gpiod': gpio, 'gpiod.line': gpio.line}):
    health = load('shared_protocol_health', 'pi-health-server/pi-health-server.py')

MAGIC = ('C', tuple(bytes((b,)) for b in protocol.MAGIC))


def health_client(channel=6):
    return health.LvhvPowerOffClient(types.SimpleNamespace(
        lvhv_commands_path=ROOT / 'commands.h', lvhv_host='fake-psu',
        lvhv_port=12000, lvhv_poweroff_channel=channel,
        gpio21_repeat_window_seconds=10.,
    ))


class Socket:
    def __init__(self, payload=b'', send_error=None):
        self.payload, self.send_error = payload, send_error
        self.sent, self.timeouts, self.closed = [], [], False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, value):
        self.sent.append(value)
        if self.send_error:
            raise self.send_error

    def recv(self, size):
        value, self.payload = self.payload[:min(size, 2)], self.payload[min(size, 2):]
        return value


class SharedProtocolTests(unittest.TestCase):
    def clients(self):
        return (watch.LocalPowerOffClient(ROOT / 'commands.h'),
                alerts.FleetPowerOffClient(ROOT / 'commands.h'),
                roc.LVHVClient(ROOT / 'commands.h'), health_client())

    def invoke(self, index, client):
        if index in (0, 3):
            return client.power_off('offline test')
        if index == 1:
            return client.power_off_host('fake-psu')
        return client.power_off()

    def test_all_protection_clients_send_same_request_and_validate_success(self):
        for index, client in enumerate(self.clients()):
            codes = (client.codes if index == 2 else
                     client._command_codes if index == 3 else client.command_codes)
            expected = protocol.encode_request(codes['COMMAND_powerOff'], codes['TYPE_lv'], 6)
            sock = Socket(protocol.encode_message([MAGIC, ('I', (0,))]))
            with self.subTest(client=index), patch.object(socket, 'create_connection', return_value=sock) as connect:
                self.invoke(index, client)
                self.assertEqual(sock.sent, [expected])
                self.assertEqual(connect.call_count, 1)
                self.assertTrue(sock.closed)

    def test_protection_clients_reject_error_wrong_magic_and_truncated_replies_without_retry(self):
        for index, client in enumerate(self.clients()):
            for frame in (protocol.encode_message([MAGIC, ('I', (-1,))]),
                          protocol.encode_message([('C', (b'N',)), ('I', (0,))]),
                          protocol.encode_message([MAGIC, ('I', (0,))])[:-1]):
                sock = Socket(frame)
                with self.subTest(client=index, frame=frame), patch.object(socket, 'create_connection', return_value=sock) as connect:
                    with self.assertRaises((ValueError, RuntimeError, EOFError)):
                        self.invoke(index, client)
                    self.assertEqual(len(sock.sent), 1)
                    self.assertEqual(connect.call_count, 1)
                    self.assertTrue(sock.closed)

    def test_uncertain_send_is_not_replayed_by_any_protection_client(self):
        for index, client in enumerate(self.clients()):
            sock = Socket(send_error=socket.timeout('unknown delivery'))
            with self.subTest(client=index), patch.object(socket, 'create_connection', return_value=sock) as connect:
                with self.assertRaises(TimeoutError):
                    self.invoke(index, client)
                self.assertEqual(len(sock.sent), 1)
                self.assertEqual(connect.call_count, 1)
                self.assertTrue(sock.closed)

    def test_ctypes_facade_matches_shared_request(self):
        connection = object.__new__(MessagingConnection)
        connection.typecodes = {getattr(ctypes, value['ctype']): key for key, value in protocol.TYPES.items()}
        header = [ctypes.c_char(b) for b in protocol.MAGIC]
        self.assertEqual(connection.encode_message(header, ctypes.c_uint(1), ctypes.c_uint(2),
            ctypes.c_char(3), ctypes.c_float(1.25)), protocol.encode_request(1, 2, 3, 1.25))

    def test_cli_and_gui_helpers_use_generated_request_layout(self):
        connection = object.__new__(MessagingConnection)
        connection.client = Socket()
        connection.timeout, connection.host, connection.port = 1., 'fake-psu', 12000
        connection.recv_message = lambda: [(1.25,) * 6]
        codes = {'COMMAND_read': 1, 'TYPE_lv': 2}
        for filename, names in (('Client.py', ['send_command']),
                ('gui.py', ['send_msg_and_recv_scalar', 'send_msg_and_recv_vector6'])):
            path = ROOT / 'Client' / filename
            tree = ast.parse(path.read_text())
            definitions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name in names], type_ignores=[])
            namespace = {'command_map': lambda: codes, 'parse_vector6': lambda value: list(value[0])}
            exec(compile(definitions, str(path), 'exec', flags=__future__.annotations.compiler_flag), namespace)
            if filename == 'Client.py':
                command = types.SimpleNamespace(name='read', type_key='lv', in_val_type=int)
                namespace['send_command'](connection, command, 3, 4)
                self.assertEqual(connection.client.sent[-1], protocol.encode_request(1, 2, 3, 4))
            else:
                namespace['send_msg_and_recv_scalar'](connection, 'read', 'lv', 3, 1.25)
                self.assertEqual(connection.client.sent[-1], protocol.encode_request(1, 2, 3, 1.25))
                namespace['send_msg_and_recv_vector6'](connection, 'read', 'lv')
                self.assertEqual(connection.client.sent[-1], protocol.encode_request(1, 2, 6))

    def test_size_and_element_limits_reject_headers_before_reading_payload(self):
        for frame, limits in ((struct.pack('<I', 1025), {}),
                (struct.pack('<I', 1) + b'D' + struct.pack('<I', 0xffffffff), {}),
                (struct.pack('<I', 1) + b'F' + struct.pack('<I', 65), {'max_elements': 64})):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                protocol.recv_message(Socket(frame), **limits)

    def test_one_deadline_covers_request_and_reply(self):
        sock = Socket(protocol.encode_message([MAGIC, ('I', (0,))]))
        with patch.object(protocol.time, 'monotonic', side_effect=[0., .1, .2, 1.1]):
            with self.assertRaises(TimeoutError):
                protocol.request_reply(sock, 1, 2, 6, timeout=1.)
        self.assertEqual(len(sock.sent), 1)

    def test_scalar_roundtrip_and_trailing_bytes(self):
        blocks = [MAGIC, ('I', (-2147483648, 2147483647)), ('U', (0, 0xffffffff)),
                  ('F', (1.25,)), ('D', (1e100,)), ('C', (b'%', b'\0'))]
        frame = protocol.encode_message(blocks)
        self.assertEqual(protocol.decode_message(frame), blocks)
        with self.assertRaises(ValueError):
            protocol.decode_message(frame + b'x')

    def test_invalid_timeouts_and_nonfinite_parameters_fail_before_send(self):
        for value in (0, -1, float('nan'), float('inf')):
            sock = Socket()
            with self.subTest(timeout=value), self.assertRaises(ValueError):
                protocol.request_reply(sock, 1, 2, 6, timeout=value)
            self.assertEqual(sock.sent, [])
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                protocol.encode_request(1, 2, 6, value)


class PiHealthShutdownTests(unittest.TestCase):
    def event(self, name, source='edge', present=False):
        return health.AcPowerState(name, 6, present, int(present), source,
                                   'test', '', '')

    def test_configured_endpoint_and_channel_are_preserved(self):
        client = health_client(channel=3)
        sock = Socket(protocol.encode_message([MAGIC, ('I', (0,))]))
        with patch.object(socket, 'create_connection', return_value=sock) as connect:
            client.power_off('offline test')
        connect.assert_called_once_with(('fake-psu', 12000), timeout=5.)
        self.assertEqual(sock.sent, [protocol.encode_request(
            client._command_codes['COMMAND_powerOff'], client._command_codes['TYPE_lv'], 3)])

    def test_startup_present_and_unrelated_events_do_not_shut_down(self):
        client = Mock()
        for event in (self.event('gpio6_ac_status', source='startup'),
                      self.event('gpio6_ac_status', present=True),
                      self.event('gpio21_ac_fail', source='startup'),
                      self.event('gpio21_ac_fail', present=True), self.event('other')):
            health.maybe_trigger_poweroff(event, client)
        client.power_off.assert_not_called()

    def test_gpio6_loss_requests_immediate_shutdown(self):
        client = Mock()
        health.maybe_trigger_poweroff(self.event('gpio6_ac_status'), client)
        client.power_off.assert_called_once_with('gpio6 power lost')

    def test_gpio21_requires_repeat_within_window_and_resets_latch(self):
        client = health_client()
        with patch.object(client, 'power_off') as off, \
                patch.object(health, 'gpio21_last_loss_monotonic', None), \
                patch.object(health.time, 'monotonic', side_effect=[0., 11., 20., 21.]):
            for _ in range(2):
                health.maybe_trigger_poweroff(self.event('gpio21_ac_fail'), client)
            off.assert_not_called()  # The first pair was more than 10 seconds apart.
            health.maybe_trigger_poweroff(self.event('gpio21_ac_fail'), client)
            off.assert_called_once_with('gpio21 repeated power loss within 10.000s')
            self.assertIsNone(health.gpio21_last_loss_monotonic)
            health.maybe_trigger_poweroff(self.event('gpio21_ac_fail'), client)
            self.assertEqual(off.call_count, 1)

    def test_bad_replies_are_logged_without_success_or_retry_by_either_gpio_handler(self):
        frames = (struct.pack('<I', 0),
                  protocol.encode_message([('C', (b'N',)), ('I', (0,))]),
                  protocol.encode_message([MAGIC, ('I', (-1,))]),
                  protocol.encode_message([MAGIC, ('U', (0,))]),
                  protocol.encode_message([MAGIC, ('I', (0,))])[:-1],
                  struct.pack('<I', 9),
                  struct.pack('<I', 2) + protocol.encode_block(*MAGIC)
                  + b'I' + struct.pack('<I', 65))
        for name in ('gpio6_ac_status', 'gpio21_ac_fail'):
            for frame in frames:
                sock = Socket(frame)
                with self.subTest(name=name, frame=frame), \
                        patch.object(socket, 'create_connection', return_value=sock) as connect, \
                        patch.object(health, 'gpio21_last_loss_monotonic', 0.), \
                        patch.object(health.time, 'monotonic', return_value=1.), \
                        self.assertLogs(level='ERROR') as logs:
                    health.maybe_trigger_poweroff(self.event(name), health_client())
                self.assertIn('failed to issue', '\n'.join(logs.output))
                self.assertEqual(connect.call_count, 1)
                self.assertEqual(len(sock.sent), 1)
                self.assertTrue(sock.closed)


class ServiceImportTests(unittest.TestCase):
    def test_source_and_flat_installed_layouts_resolve_shared_codec(self):
        # A fresh interpreter prevents prior tests' sys.path/module cache from
        # hiding a missing deployment dependency. No service main is executed.
        script = '''
import importlib.util, pathlib, sys, types
root = pathlib.Path(sys.argv[1])
gpio = types.ModuleType('gpiod')
gpio.line = types.ModuleType('gpiod.line')
gpio.line.Bias = gpio.line.Direction = gpio.line.Edge = object()
sys.modules.update({'gpiod': gpio, 'gpiod.line': gpio.line})
sys.modules['requests'] = types.ModuleType('requests')
conversion = types.ModuleType('WireAnalogDigitalConversion')
conversion.WireAnalogDigitalConversion = object
sys.modules['WireAnalogDigitalConversion'] = conversion
sys.path.insert(0, str(root / 'Client'))
if sys.argv[2] == 'flat':
    sys.path.insert(0, str(root / 'modules'))
name, path = sys.argv[4:]
spec = importlib.util.spec_from_file_location(name, root / path)
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)
for shared in ('lvhv_protocol', 'lvhv_protocol_generated'):
    assert pathlib.Path(sys.modules[shared].__file__).resolve() == (
        root / sys.argv[3] / (shared + '.py')).resolve()
'''
        adapters = (
            ('MessagingConnection', 'Client/MessagingConnection.py'),
            ('PowerSupplyServerConnection', 'Client/PowerSupplyServerConnection.py'),
            ('watch', 'network-watch/network-watch.py'),
            ('roc', 'roc-temperature-monitor/roc_temperature_monitor.py'),
            ('alerts', 'i2c-sensor-alerts/i2c-sensor-alerts.py'),
            ('health', 'pi-health-server/pi-health-server.py'),
            ('discovery', 'rs485-server/discovery_history.py'),
        )
        services = tuple(path for name, path in adapters) + ('config/alarm-policy.json',)
        modules = ('lvhv_protocol.py', 'lvhv_protocol_generated.py', 'alarm_policy.py')
        for module in modules:
            self.assertFalse((ROOT / 'Client' / module).exists())
        for layout, module_dir in (('source', 'common'), ('flat', 'modules')):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for source, dest in ([(p, p) for p in services] +
                        [('common/' + p, module_dir + '/' + p) for p in modules]):
                    target = root / dest
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((ROOT / source).read_bytes())
                for name, path in adapters:
                    with self.subTest(adapter=name):
                        result = subprocess.run([sys.executable, '-I', '-c', script,
                                                 tmp, layout, module_dir, name, path], cwd=tmp,
                                                capture_output=True, text=True, timeout=15)
                        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
