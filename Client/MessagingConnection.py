# Ed Callaghan
# De/serialization protocol for structured messaging
# January 2025

import ctypes
import math
import socket
import time
from pathlib import Path
import sys

# Support both the installed flat modules and a direct source-file import.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import lvhv_protocol as protocol

class MessagingConnection:
    MAX_BLOCKS = protocol.MAX_BLOCKS
    MAX_MESSAGE_BYTES = protocol.MAX_MESSAGE_BYTES

    def __init__(self, host, port, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('LVHV connection timeout must be finite and positive')
        self.reestablish()

        self.header = [ctypes.c_char(c) for c in protocol.MAGIC]
        self.check = tuple(bytes((c,)) for c in protocol.MAGIC)
        self.inverse_typecodes = {key: getattr(ctypes, value['ctype']) for key, value in protocol.TYPES.items()}
        self.typecodes = {value: key for key, value in self.inverse_typecodes.items()}
        self.formats = {key: value['format'] for key, value in protocol.TYPES.items()}
        self.formats.update({kind: self.formats[code] for kind, code in self.typecodes.items()})

    def reestablish(self):
        if getattr(self, 'client', None) is not None:
            self.close()
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client.settimeout(self.timeout)
            self.client.connect((self.host, self.port))
        except Exception:
            self.close()
            raise

    def close(self):
        if getattr(self, 'client', None) is not None:
            self.client.close()

    def encode_block(self, *items):
        if not items or type(items[0]) not in self.typecodes:
            raise ValueError('Unknown or empty LVHV block')
        kind = self.typecodes[type(items[0])]
        return protocol.encode_block(kind, tuple(x.value for x in items))

    def aggregate_types(self, *items):
        return [item if isinstance(item, list) else [item] for item in items]

    def encode_message(self, *items):
        blocks = []
        for values in self.aggregate_types(*items):
            if not values or type(values[0]) not in self.typecodes:
                raise ValueError('Unknown or empty LVHV block')
            blocks.append((self.typecodes[type(values[0])], tuple(x.value for x in values)))
        return protocol.encode_message(blocks)

    def decode_message(self, buff):
        return [values for kind, values in protocol.decode_message(
            buff, self.MAX_BLOCKS, self.MAX_MESSAGE_BYTES)]

    def send_message(self, *items):
        encoded = self.encode_message(self.header, *items)
        self._send_encoded(encoded)

    def send_request(self, command, subsystem, channel, numeric=0.0):
        self._send_encoded(protocol.encode_request(command, subsystem, channel, numeric))

    def _send_encoded(self, encoded):
        try:
            self.client.settimeout(self.timeout)
            self.client.sendall(encoded)
        except TimeoutError as error:
            self.close()
            raise TimeoutError('Timed out sending LVHV command to %s:%d; '
                               'delivery uncertain, command not retried' %
                               (self.host, self.port)) from error
        except OSError as error:
            self.close()
            raise ConnectionError('Failed sending LVHV command to %s:%d; '
                                  'delivery uncertain, command not retried: %s' %
                                  (self.host, self.port, error)) from error

    def safe_recv(self, chunk, deadline=None, context='reply data'):
        if deadline is None:
            deadline = time.monotonic() + self.timeout
        try:
            return protocol.recv_exact(self.client, chunk, deadline, context)
        except Exception:
            self.close()
            raise

    def recv_block(self, deadline=None, max_bytes=None):
        if deadline is None:
            deadline = time.monotonic() + self.timeout
        return protocol.recv_block(self.client, deadline,
            self.MAX_MESSAGE_BYTES if max_bytes is None else max_bytes)

    def recv_message(self):
        try:
            blocks = protocol.recv_message(self.client, self.timeout,
                max_blocks=self.MAX_BLOCKS, max_bytes=self.MAX_MESSAGE_BYTES)
            return [values for kind, values in protocol.verify_magic(blocks)]
        except Exception as error:
            self.close()
            # Never reconnect/replay automatically: a command may have executed.
            if isinstance(error, TimeoutError):
                raise TimeoutError('Timed out receiving LVHV reply from %s:%d' %
                                   (self.host, self.port)) from error
            raise
