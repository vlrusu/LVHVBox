# Ed Callaghan
# De/serialization protocol for structured messaging
# January 2025

import ctypes
import socket
import struct

class MessagingConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
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
        }

    def reestablish(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.connect((self.host, self.port))
        self.client.settimeout(0.5)

    def close(self):
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
        lo = 0
        hi = 4
        nblocks = struct.unpack('i', buff[lo:hi])[0]
        lo = hi

        rvs = []
        for i in range(nblocks):
            typecode = buff[lo:lo+1].decode()
            key = self.formats[typecode]
            lo += 1
            hi = lo + 4
            count = struct.unpack('i', buff[lo:hi])[0]
            fmt = '%d%s' % (count, key)
            size = struct.calcsize(fmt)
            lo = hi
            hi = lo + size
            unpacked = struct.unpack(fmt, buff[lo:hi])
            rvs.append(unpacked)
            lo = hi

        assert(lo == hi == len(buff))

        return rvs

    def send_message(self, *items):
        encoded = self.encode_message(self.header, *items)
        self.client.send(encoded)

    # TODO disable timeout and calculate rolling size for exact read
    def recv_message(self):
        chunk = 1024
        rv = b''
        recv = self.client.recv(chunk)
        while 0 < len(recv):
            rv += recv
            try:
                recv = self.client.recv(chunk)
            except:
                recv = b''

        rv = self.decode_message(rv)
        assert(rv[0] == self.check)
        rv = rv[1:]
        return rv
