"""Shared LVHV codec and bounded socket framing. Never reconnects or replays."""
import math
import struct
import time

from lvhv_protocol_generated import (
    COUNT_BYTES, COUNT_FORMAT, ENDIAN, FRAME_TIMEOUT_MS, MAGIC, MAX_BLOCKS,
    MAX_MESSAGE_BYTES, REQUEST, REQUEST_FIELDS, TYPES,
)


def encode_block(kind, values):
    if kind not in TYPES:
        raise ValueError('Unknown LVHV type code')
    count = len(values)
    if count > (MAX_MESSAGE_BYTES - COUNT_BYTES - 1) // TYPES[kind]['bytes']:
        raise ValueError('LVHV block exceeds size limit')
    return (kind.encode('ascii') + struct.pack(COUNT_FORMAT, count)
            + struct.pack(ENDIAN + str(count) + TYPES[kind]['format'], *values))


def encode_message(blocks):
    if not 1 <= len(blocks) <= MAX_BLOCKS:
        raise ValueError('Invalid LVHV block count')
    size = COUNT_BYTES + sum(1 + COUNT_BYTES + len(values) * TYPES[kind]['bytes']
                             for kind, values in blocks if kind in TYPES)
    if size > MAX_MESSAGE_BYTES:
        raise ValueError('LVHV message exceeds size limit')
    return struct.pack(COUNT_FORMAT, len(blocks)) + b''.join(encode_block(*b) for b in blocks)


def encode_request(command, subsystem, channel, numeric=0.0):
    if not math.isfinite(float(numeric)):
        raise ValueError('LVHV numeric parameter must be finite')
    values = {'command': (command,), 'subsystem': (subsystem,),
              'channel': (bytes((channel,)),), 'numeric': (numeric,)}
    return encode_message([('C', tuple(bytes((b,)) for b in MAGIC))]
                          + [(kind, values[name]) for name, kind, count in REQUEST_FIELDS])


def decode_message(data, max_blocks=MAX_BLOCKS, max_bytes=MAX_MESSAGE_BYTES):
    if not COUNT_BYTES <= len(data) <= max_bytes:
        raise ValueError('Invalid LVHV reply length')
    count = struct.unpack_from(COUNT_FORMAT, data)[0]
    if not 1 <= count <= min(max_blocks, MAX_BLOCKS):
        raise ValueError('Invalid LVHV reply block count')
    offset, blocks = COUNT_BYTES, []
    for _ in range(count):
        if offset + 1 + COUNT_BYTES > len(data):
            raise ValueError('Truncated LVHV block header')
        kind = chr(data[offset])
        if kind not in TYPES:
            raise ValueError('Unknown LVHV type code')
        elements = struct.unpack_from(COUNT_FORMAT, data, offset + 1)[0]
        offset += 1 + COUNT_BYTES
        size = elements * TYPES[kind]['bytes']
        if size > len(data) - offset:
            raise ValueError('Truncated or excessive LVHV block payload')
        blocks.append((kind, struct.unpack_from(ENDIAN + str(elements) + TYPES[kind]['format'], data, offset)))
        offset += size
    if offset != len(data):
        raise ValueError('Trailing bytes in LVHV reply')
    return blocks


def recv_exact(sock, size, deadline, context='reply data'):
    chunks, remaining = [], size
    while remaining:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError('LVHV reply deadline expired')
        sock.settimeout(timeout)
        part = sock.recv(min(65536, remaining))
        if not part:
            raise EOFError(f'Connection closed receiving LVHV {context} ({size-remaining}/{size} bytes)')
        chunks.append(part)
        remaining -= len(part)
    return b''.join(chunks)


def recv_message(sock, timeout=FRAME_TIMEOUT_MS / 1000, *, max_blocks=MAX_BLOCKS,
                 max_bytes=MAX_MESSAGE_BYTES, max_elements=None, deadline=None):
    if deadline is None:
        deadline = time.monotonic() + timeout
    prefix = recv_exact(sock, COUNT_BYTES, deadline, 'block count')
    count = struct.unpack(COUNT_FORMAT, prefix)[0]
    if not 1 <= count <= min(max_blocks, MAX_BLOCKS):
        raise ValueError('Invalid LVHV reply block count')
    blocks, total = [prefix], COUNT_BYTES
    for _ in range(count):
        block = recv_block(sock, deadline, min(max_bytes, MAX_MESSAGE_BYTES) - total, max_elements)
        blocks.append(block)
        total += len(block)
    return decode_message(b''.join(blocks), max_blocks, max_bytes)


def recv_block(sock, deadline, budget=MAX_MESSAGE_BYTES, max_elements=None):
    if budget < 1 + COUNT_BYTES:
        raise ValueError('LVHV reply exceeds size limit')
    header = recv_exact(sock, 1 + COUNT_BYTES, deadline, 'block header')
    kind = chr(header[0])
    if kind not in TYPES:
        raise ValueError('Unknown LVHV type code')
    elements = struct.unpack_from(COUNT_FORMAT, header, 1)[0]
    if max_elements is not None and elements > max_elements:
        raise ValueError('Invalid LVHV reply block size')
    size = elements * TYPES[kind]['bytes']
    if size > budget - len(header):
        raise ValueError('LVHV reply exceeds size limit')
    return header + recv_exact(sock, size, deadline, 'block payload')


def verify_magic(blocks):
    expected = ('C', tuple(bytes((b,)) for b in MAGIC))
    if not blocks or blocks[0] != expected:
        raise ValueError('Invalid LVHV reply magic header')
    return blocks[1:]


def recv_reply(sock, timeout=FRAME_TIMEOUT_MS / 1000, **limits):
    return verify_magic(recv_message(sock, timeout, **limits))


def request_reply(sock, command, subsystem, channel, numeric=0.0, timeout=5.0, **limits):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('LVHV timeout must be finite and positive')
    payload = encode_request(command, subsystem, channel, numeric)
    deadline = time.monotonic() + timeout
    sock.settimeout(timeout)
    sock.sendall(payload)
    return recv_reply(sock, timeout, deadline=deadline, **limits)


def require_success(reply):
    if reply != [('I', (0,))]:
        raise RuntimeError('LVHV powerOff did not return success')
