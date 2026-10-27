"""Transport tests with fake sockets only: no GUI, network or hardware access."""
import ctypes
import ast
import importlib.util
from pathlib import Path
import socket
import struct
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'MessagingConnection.py'
spec = importlib.util.spec_from_file_location('lvhv_transport_under_test', SOURCE)
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


class FakeSocket:
    def __init__(self):
        self.fragments = []
        self.closed = False
        self.sent = []
        self.timeouts = []
        self.recv_calls = 0

    def connect(self, address):
        self.address = address

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def setblocking(self, value):
        pass

    def recv(self, size):
        self.recv_calls += 1
        if self.recv_calls > 1000:
            raise RuntimeError('Test aborted nonterminating receive loop')
        if not self.fragments:
            return b''
        fragment = self.fragments.pop(0)
        if isinstance(fragment, Exception):
            raise fragment
        result = fragment[:size]
        if len(fragment) > size:
            self.fragments.insert(0, fragment[size:])
        return result

    def sendall(self, payload):
        self.sent.append(payload)

    def close(self):
        self.closed = True


class MessagingConnectionTests(unittest.TestCase):
    def setUp(self):
        self.socket = FakeSocket()
        with patch.object(transport.socket, 'socket', return_value=self.socket):
            self.connection = transport.MessagingConnection('fake-psu', 12000)

    def reply(self):
        return self.connection.encode_message(self.connection.header, ctypes.c_float(12.5))

    def receive(self, payload):
        self.socket.fragments = [payload]
        return self.connection.recv_message()

    def test_fragmented_reply_one_byte_at_a_time(self):
        self.socket.fragments = [bytes([byte]) for byte in self.reply()]
        # The old reader uses select; patch it so the regression does not touch
        # any real file descriptor even before the implementation is fixed.
        if hasattr(transport, 'select'):
            with patch.object(transport.select, 'select', return_value=([self.socket], [], [])):
                result = self.connection.recv_message()
        else:
            result = self.connection.recv_message()
        self.assertEqual(result, [(12.5,)])

    def test_two_replies_in_one_tcp_chunk_stay_separate(self):
        self.socket.fragments = [self.reply() + self.reply()]
        self.assertEqual(self.connection.recv_message(), [(12.5,)])
        self.assertEqual(self.connection.recv_message(), [(12.5,)])

    def test_eof_in_count_closes_connection_with_clear_error(self):
        self.socket.fragments = [self.reply()[:2]]
        with self.assertRaisesRegex(EOFError, '2/4 bytes'):
            self.connection.recv_message()
        self.assertTrue(self.socket.closed)

    def test_eof_in_payload_terminates_instead_of_looping(self):
        self.socket.fragments = [self.reply()[:-2]]
        with self.assertRaisesRegex(EOFError, 'payload'):
            self.connection.recv_message()
        self.assertTrue(self.socket.closed)
        self.assertLess(self.socket.recv_calls, 20)

    def test_timeout_is_explicit_and_discards_connection(self):
        self.socket.fragments = [socket.timeout('fake stalled peer')]
        with self.assertRaisesRegex(TimeoutError, 'fake-psu:12000'):
            self.connection.recv_message()
        self.assertTrue(self.socket.closed)

    def test_all_reply_fields_share_one_deadline(self):
        self.connection.timeout = 1.0
        self.socket.fragments = [self.reply()]
        with patch.object(transport.time, 'monotonic', side_effect=[0.0, 0.1, 0.2, 1.1]):
            with self.assertRaises(TimeoutError):
                self.connection.recv_message()
        self.assertTrue(self.socket.closed)
        self.assertAlmostEqual(self.socket.timeouts[-1], 0.8)

    def test_truncated_or_invalid_frame_is_rejected(self):
        for payload in (b'', struct.pack('I', 1),
                        struct.pack('I', 1) + b'Z' + struct.pack('I', 1) + b'x'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.connection.decode_message(payload)

    def test_excessive_counts_and_bad_header_close_connection(self):
        for payload in (struct.pack('I', 0), struct.pack('I', 0xffffffff),
                        struct.pack('I', 1) + b'F' + struct.pack('I', 0xffffffff),
                        self.connection.encode_message([ctypes.c_char(c) for c in b'NOPE'])):
            with self.subTest(payload=payload):
                self.socket.closed = False
                with self.assertRaises(ValueError):
                    self.receive(payload)
                self.assertTrue(self.socket.closed)

    def test_send_uses_sendall_without_retry(self):
        self.connection.send_message(ctypes.c_uint(123))
        self.assertEqual(self.socket.sent, [self.connection.encode_message(
            self.connection.header, ctypes.c_uint(123))])

    def test_send_failure_closes_without_replaying_command(self):
        attempted = []
        def fail(payload):
            attempted.append(payload)
            raise socket.timeout('unknown delivery')
        self.socket.sendall = fail
        with self.assertRaises(TimeoutError):
            self.connection.send_message(ctypes.c_uint(123))
        self.assertTrue(self.socket.closed)
        self.assertEqual(len(attempted), 1)

    def test_incomplete_readback_aborts_actual_ramp_before_dac_write(self):
        # Use the actual ramp/WriteRead methods without constructing a PSU or
        # importing calibration libraries. Only the fake transport is attached.
        path = SOURCE.parent / 'PowerSupplyServerConnection.py'
        tree = ast.parse(path.read_text())
        definitions = ast.Module(body=[node for node in tree.body
                                       if isinstance(node, ast.ClassDef)], type_ignores=[])
        namespace = dict(ctypes=ctypes)
        exec(compile(definitions, str(path), 'exec'), namespace)
        power = object.__new__(namespace['PowerSupplyServerConnection'])
        power.connection = self.connection
        power.specials = dict(COMMAND_get_vhv=1089429348, TYPE_pico=131229678)
        power.types = {'get_vhv': 'pico'}
        self.socket.fragments = [self.reply()[:2]]
        with self.assertRaises(EOFError):
            power.SetWireVoltage(0, 1200.0)
        self.assertTrue(self.socket.closed)
        self.assertEqual(len(self.socket.sent), 1)
        command = self.connection.decode_message(self.socket.sent[0])
        self.assertEqual(command[1], (power.specials['COMMAND_get_vhv'],))

    def test_connect_has_timeout_before_connect_and_failure_closes(self):
        fake = FakeSocket()
        seen = []
        def fail(address):
            seen.extend(fake.timeouts)
            raise socket.timeout('no server')
        fake.connect = fail
        with patch.object(transport.socket, 'socket', return_value=fake):
            with self.assertRaises(TimeoutError):
                transport.MessagingConnection('fake-psu', 12000)
        self.assertTrue(seen)
        self.assertTrue(fake.closed)


if __name__ == '__main__':
    unittest.main()
