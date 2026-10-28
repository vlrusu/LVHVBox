"""Shared codec and real protection-client adapters; fake sockets, no hardware."""
import ctypes
import ast
import __future__
import importlib.util
from pathlib import Path
import socket
import struct
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Client'))
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

MAGIC = ('C', tuple(bytes((b,)) for b in protocol.MAGIC))


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
                roc.LVHVClient(ROOT / 'commands.h'))

    def invoke(self, index, client):
        if index == 0:
            return client.power_off('offline test')
        if index == 1:
            return client.power_off_host('fake-psu')
        return client.power_off()

    def test_all_protection_clients_send_same_request_and_validate_success(self):
        for index, client in enumerate(self.clients()):
            codes = client.codes if index == 2 else client.command_codes
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


if __name__ == '__main__':
    unittest.main()
