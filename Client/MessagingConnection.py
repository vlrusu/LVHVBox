# Ed Callaghan
# De/serialization protocol for structured messaging
# January 2025

import ctypes
import math
import socket
import struct
import time

class MessagingConnection:
    # Defensive client framing bounds, not detector/hardware limits.
    MAX_BLOCKS = 1024
    MAX_MESSAGE_BYTES = 64 * 1024 * 1024

    def __init__(self, host, port, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('LVHV connection timeout must be finite and positive')
        self.reestablish()

        self.header = [ctypes.c_char(c) for c in 'LVHV'.encode()]
        self.check = (b'L', b'V', b'H', b'V')
        self.typecodes = {
          ctypes.c_char: 'C',
          ctypes.c_int: 'I',
          ctypes.c_uint: 'U',
          ctypes.c_float: 'F',
          ctypes.c_double: 'D',
        }
        self.formats = {
          ctypes.c_char: 'c',
          ctypes.c_int: 'i',
          ctypes.c_uint: 'I',
          ctypes.c_float: 'f',
          ctypes.c_double: 'd',

            'C': 'c',
            'I': 'i',
            'F': 'f',
            'U': 'I',
            'D': 'd',
        }
        self.inverse_typecodes = {
          'C': ctypes.c_char,
          'I': ctypes.c_int,
          'U': ctypes.c_uint,
          'F': ctypes.c_float,
          'D': ctypes.c_double,
        }

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
        _type = type(items[0])
        typecode = self.typecodes[_type]
        key = self.formats[_type]
        fmt = '%d%s' % (len(items), key)
        pfx = struct.pack('c', typecode.encode())
        pfx += struct.pack('I', len(items))
        packable = [x.value for x in items]
        payload = struct.pack(fmt, *packable)
        rv = pfx + payload
        return rv

    def encode_message(self, *items):
        itemss = self.aggregate_types(*items)

        rv = struct.pack('I', len(itemss))
        for items in itemss:
            rv += self.encode_block(*items)

        return rv

    def aggregate_types(self, *items):
        rvs = []
        for item in items:
            if type(item) == list:
                rvs.append(item)
            else:
                rvs.append([item])

        return rvs

    def decode_message(self, buff):
        if not 4 <= len(buff) <= self.MAX_MESSAGE_BYTES:
            raise ValueError('Invalid LVHV reply length')
        lo = 0
        hi = 4
        nblocks = struct.unpack('I', buff[lo:hi])[0]
        if not 1 <= nblocks <= self.MAX_BLOCKS:
            raise ValueError('Invalid LVHV reply block count: %d' % nblocks)
        lo = hi

        rvs = []
        for i in range(nblocks):
            if lo + 5 > len(buff):
                raise ValueError('Truncated LVHV block header')
            typecode = chr(buff[lo])
            if typecode not in self.inverse_typecodes:
                raise ValueError('Unknown LVHV type code: %r' % typecode)
            key = self.formats[typecode]
            lo += 1
            hi = lo + 4
            count = struct.unpack('I', buff[lo:hi])[0]
            if count * ctypes.sizeof(self.inverse_typecodes[typecode]) > len(buff) - hi:
                raise ValueError('Truncated or excessive LVHV block payload')
            fmt = '%d%s' % (count, key)
            size = struct.calcsize(fmt)
            lo = hi
            hi = lo + size
            unpacked = struct.unpack(fmt, buff[lo:hi])
            rvs.append(unpacked)
            lo = hi

        if hi != len(buff):
            raise ValueError('Trailing bytes in LVHV reply')

        return rvs

    def send_message(self, *items):
        encoded = self.encode_message(self.header, *items)
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
        """Read exactly chunk bytes, with EOF failure and one overall deadline."""
        if deadline is None:
            deadline = time.monotonic() + self.timeout
        received = bytearray()
        while len(received) < chunk:
            detail = '%s from %s:%d (%d/%d bytes)' % (
                context, self.host, self.port, len(received), chunk)
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('LVHV reply deadline expired')
                self.client.settimeout(remaining)
                data = self.client.recv(min(65536, chunk - len(received)))
            except TimeoutError as error:
                self.close()
                raise TimeoutError('Timed out receiving LVHV %s' % detail) from error
            except OSError as error:
                self.close()
                raise ConnectionError('Failed receiving LVHV %s: %s' % (detail, error)) from error
            if not data:
                self.close()
                raise EOFError('Connection closed receiving LVHV %s' % detail)
            received.extend(data)
        return bytes(received)

    def recv_block(self, deadline=None, max_bytes=None):
        if deadline is None:
            deadline = time.monotonic() + self.timeout
        if max_bytes is None:
            max_bytes = self.MAX_MESSAGE_BYTES
        typecode = self.safe_recv(1, deadline, 'block type')
        count_bytes = self.safe_recv(4, deadline, 'block element count')
        key = chr(typecode[0])
        if key not in self.inverse_typecodes:
            raise ValueError('Unknown LVHV type code: %r' % key)
        count = struct.unpack('I', count_bytes)[0]
        _type = self.inverse_typecodes[key]
        size = count * ctypes.sizeof(_type)
        if size + 5 > max_bytes:
            raise ValueError('LVHV block exceeds reply size limit')
        return typecode + count_bytes + self.safe_recv(size, deadline, 'block payload')

    def recv_message(self):
        try:
            deadline = time.monotonic() + self.timeout
            prefix = self.safe_recv(4, deadline, 'block count')
            nblocks = struct.unpack('I', prefix)[0]
            if not 1 <= nblocks <= self.MAX_BLOCKS:
                raise ValueError('Invalid LVHV reply block count: %d' % nblocks)
            blocks = [prefix]
            total = len(prefix)
            for i in range(nblocks):
                block = self.recv_block(deadline, self.MAX_MESSAGE_BYTES - total)
                blocks.append(block)
                total += len(block)
            reply = self.decode_message(b''.join(blocks))
            if reply[0] != self.check:
                raise ValueError('Invalid LVHV reply magic header')
            return reply[1:]
        except Exception:
            # A partial frame cannot safely be reused for the next command.
            # Never reconnect/replay automatically: a write may have executed.
            self.close()
            raise
