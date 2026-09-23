#!/usr/bin/env python3
"""Shared ROC RS485 v2 implementation; importing this module never opens hardware."""
from dataclasses import dataclass
import struct

FLAG, ESC = 0x7E, 0x7D
VERSION, REQUEST, RESPONSE = 2, 1, 2
MAX_PAYLOAD = 32
HEADER = struct.Struct('<BBHHBB')


def fcs16(data: bytes) -> int:
    """RFC1662 FCS (CRC-16/IBM-SDLC); check('123456789') == 0x906e."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc ^ 0xFFFF


def frame_bytes(body_with_fcs: bytes) -> bytes:
    out = bytearray([FLAG])
    for byte in body_with_fcs:
        if byte in (FLAG, ESC):
            out.extend((ESC, byte ^ 0x20))
        else:
            out.append(byte)
    out.append(FLAG)
    return bytes(out)


@dataclass(frozen=True)
class Packet:
    kind: int
    roc: int
    transaction: int
    command: int
    payload: bytes = b''

    def encode(self) -> bytes:
        if self.kind not in (REQUEST, RESPONSE) or not 0 <= self.roc <= 511:
            raise ValueError('invalid packet type or ROC address')
        if not 0 <= self.transaction <= 65535 or not 0 <= self.command <= 255:
            raise ValueError('invalid transaction or command')
        if len(self.payload) > MAX_PAYLOAD:
            raise ValueError('payload exceeds32 bytes')
        body = HEADER.pack(VERSION, self.kind, self.roc, self.transaction,
                           self.command, len(self.payload)) + self.payload
        return frame_bytes(body + struct.pack('<H', fcs16(body)))

    @staticmethod
    def decode(wire: bytes) -> 'Packet':
        if len(wire) < 2 or wire[0] != FLAG or wire[-1] != FLAG:
            raise ValueError('missing delimiters')
        body = bytearray()
        escaped = False
        for byte in wire[1:-1]:
            if byte == FLAG:
                raise ValueError('unexpected delimiter')
            if escaped:
                if byte not in (0x5D, 0x5E):
                    raise ValueError('invalid escape')
                body.append(byte ^ 0x20)
                escaped = False
            elif byte == ESC:
                escaped = True
            else:
                body.append(byte)
            if len(body) > HEADER.size + MAX_PAYLOAD + 2:
                raise ValueError('oversized frame')
        if escaped or len(body) < HEADER.size + 2:
            raise ValueError('incomplete frame')
        version, kind, roc, transaction, command, length = HEADER.unpack(body[:HEADER.size])
        if version != VERSION or kind not in (REQUEST, RESPONSE) or roc > 511:
            raise ValueError('invalid header')
        if length > MAX_PAYLOAD or len(body) != HEADER.size + length + 2:
            raise ValueError('invalid length')
        if fcs16(body[:-2]) != int.from_bytes(body[-2:], 'little'):
            raise ValueError('bad FCS')
        return Packet(kind, roc, transaction, command, bytes(body[HEADER.size:-2]))

    def scalar_result(self, request: 'Packet') -> int:
        """Validate response identity and status before exposing a measurement."""
        if request.kind != REQUEST or self.kind != RESPONSE:
            raise ValueError('not a request/response pair')
        if (self.roc, self.transaction, self.command) != (request.roc, request.transaction, request.command):
            raise ValueError('response does not match outstanding request')
        if len(self.payload) != 3:
            raise ValueError('expected status plus16-bit value')
        if self.payload[0] != 0:
            raise ValueError(f'ROC status={self.payload[0]}')
        return int.from_bytes(self.payload[1:], 'little')


# Pi transport. Hardware dependencies are imported only when opening a bus.
from datetime import datetime, timezone
import threading
from contextlib import ExitStack, contextmanager
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time

STATUS_NAMES = {
    1: 'unsupported command', 2: 'bad request payload length',
    3: 'CPU completion missing ACK or fresh data',
    4: 'sensor setup/read failed', 5: 'panel-ID NVM read failed',
}
MAX_WIRE = 2 + 2 * (HEADER.size + MAX_PAYLOAD + 2)


class ROCError(RuntimeError):
    pass


class FrameStream:
    """Bounded delimiter parser; corrupt/partial traffic cannot become a value."""
    def __init__(self):
        self.frame = None
        self.bad_frames = 0

    def feed(self, data):
        packets = []
        for byte in data:
            if byte == FLAG:
                if self.frame is not None and len(self.frame) > 1:
                    try:
                        packets.append(Packet.decode(bytes(self.frame) + bytes([FLAG])))
                    except ValueError:
                        self.bad_frames += 1
                self.frame = bytearray([FLAG])
            elif self.frame is not None:
                self.frame.append(byte)
                if len(self.frame) >= MAX_WIRE:
                    self.bad_frames += 1
                    self.frame = None  # discard through the next delimiter
        return packets


class BusSession:
    """One client per UART, persistent transaction IDs and restart holdoff.

    The reservation is saved before transmission. If interrupted, the next
    invocation waits out that request's response window before reusing the bus.
    Linux flock is advisory; all users of this bus must use this client/lock.
    """
    def __init__(self, path):
        self.path = path
        self.file = None

    def __enter__(self):
        import fcntl
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.file = os.fdopen(fd, 'r+', encoding='ascii')
        try:
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('another RS485 process owns this UART; stop rs485-server before using com_v2.py') from None
            self.file.seek(0)
            content = self.file.read()
            self.state = json.loads(content) if content else {
                'next_id': secrets.randbelow(65536), 'not_before': 0.0}
            if (not isinstance(self.state, dict) or
                    type(self.state.get('next_id')) is not int or
                    not 0 <= self.state['next_id'] <= 65535 or
                    not isinstance(self.state.get('not_before'), (int, float)) or
                    not math.isfinite(self.state['not_before'])):
                raise ValueError('invalid RS485 transaction state: ' + str(self.path))
            self.wait_ready()
            return self
        except BaseException:
            self.file.close()
            raise

    def wait_ready(self):
        delay = self.state['not_before'] - time.time()
        if delay > 0:
            print(f'Waiting {delay:.2f}s for previous response window', file=sys.stderr)
            time.sleep(delay)
        # This process has waited out the old window; keep the disk record
        # until the next reservation/complete for interrupted-process safety.
        self.state['not_before'] = 0.0

    def save(self):
        self.file.seek(0)
        json.dump(self.state, self.file)
        self.file.truncate()
        self.file.flush()
        os.fsync(self.file.fileno())

    def reserve(self, window):
        # Also enforce holdoff within a long-lived server session after failure.
        self.wait_ready()
        transaction = self.state['next_id']
        self.state['next_id'] = (transaction + 1) & 0xFFFF
        self.state['not_before'] = time.time() + window
        self.save()
        return transaction

    def complete(self):
        self.state['not_before'] = 0.0
        self.save()

    def __exit__(self, *exc):
        self.file.close()  # releases flock


class PiBus:
    def __init__(self, serial_port, direction, session, timeout=6.0, debug=False):
        self.serial = serial_port
        self.direction = direction
        self.session = session
        self.timeout = timeout
        self.debug = debug

    def read_scalar(self, address, command):
        # Allow up to 1s write timeout plus turnaround before the response window.
        request = Packet(REQUEST, address, self.session.reserve(self.timeout + 1.1), command)
        wire = request.encode()
        self.direction(False)
        self.serial.reset_input_buffer()
        if self.debug:
            print(f'TX id={request.transaction}: {wire.hex(" ")}', file=sys.stderr)
        try:
            self.direction(True)
            time.sleep(0.0001)  # DE setup; the FPGA still receives one continuous frame
            if self.serial.write(wire) != len(wire):
                raise OSError('short UART write')
            self.serial.flush()  # tcdrain: keep DE high until the UART has sent the frame
        finally:
            self.direction(False)  # release bus on every exit, including Ctrl-C
        deadline = time.monotonic() + self.timeout
        stream = FrameStream()
        ignored = 0
        while time.monotonic() < deadline:
            self.serial.timeout = min(0.05, max(0.0, deadline - time.monotonic()))
            data = self.serial.read(min(128, max(1, self.serial.in_waiting)))
            if self.debug and data:
                print('RX: ' + data.hex(' '), file=sys.stderr)
            for response in stream.feed(data):
                if (response.kind != RESPONSE or
                        (response.roc, response.transaction, response.command) !=
                        (request.roc, request.transaction, request.command)):
                    ignored += 1
                    continue
                if len(response.payload) != 3:
                    stream.bad_frames += 1
                    continue
                # A matching, CRC-checked complete response finishes ownership.
                self.session.complete()
                time.sleep(10 / 38400)  # let the closing byte's stop bit finish
                status = response.payload[0]
                if status:
                    raise ROCError(f'ROC status {status}: {STATUS_NAMES.get(status, "CPU error")}')
                return response.scalar_result(request)
        raise TimeoutError(
            f'No matching response within {self.timeout:g}s '
            f'(invalid frames={stream.bad_frames}, other replies={ignored}). '
            'No automatic retry; check CPU/FPGA readiness and RS485 address.')


def default_lock_path(port):
    key = hashlib.sha256(os.path.realpath(port).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / ('lvhv-rs485-v2-' + key + '.json')


def command_ids(rule):
    if 'cmdids' in rule:
        commands = rule['cmdids']
        if 'cmdid' in rule or not isinstance(commands, list) or len(commands) != 2:
            raise ValueError('cmdids must contain exactly two commands, low word then high word')
    else:
        commands = [rule['cmdid']]
    if any(type(command) is not int or not 0 <= command <= 255 for command in commands):
        raise ValueError('command IDs must be integers in 0..255')
    return commands


def read_rule(bus, address, rule):
    commands = command_ids(rule)
    low = bus.read_scalar(address, commands[0])
    if len(commands) == 1:
        return low
    # Each word must pass the normal CRC/identity/status checks. These are
    # separate sensor acquisitions in the current CPU, not an atomic sample.
    high = bus.read_scalar(address, commands[1])
    return (high << 16) | low


def convert_value(name, raw, rule, calibrations, panel):
    if name == 'Flow':
        factor, offset = calibrations[('A0', panel)]
        value = factor * raw + offset
    else:
        # Expressions come only from trusted local configuration.
        value = eval(rule['expression'], {'__builtins__': {}}, {'x': raw})
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('conversion did not produce a finite real number')
    return value


def format_value(name, raw, rule, calibrations, panel):
    value = convert_value(name, raw, rule, calibrations, panel)
    kind = rule.get('format', 'float')
    if kind == 'int':
        return f'{name:<20} = {int(value):8d}'
    if kind == 'hex':
        return f'{name:<20} = {int(value):#010x}'
    return f'{name:<20} = {value:8.4f}'


@contextmanager
def open_bus(port='/dev/ttyAMA0', gpiochip='/dev/gpiochip0', dir_pin=24,
             timeout=6.0, debug=False):
    """Own the UART and GPIO until context exit; honor persisted reply holdoff."""
    # Lazy imports: --help, --dry-run and offline tests need no Pi libraries.
    import serial
    import gpiod
    from gpiod.line import Direction, Value
    with ExitStack() as stack:
        session = stack.enter_context(BusSession(default_lock_path(port)))
        lines = stack.enter_context(gpiod.request_lines(
            gpiochip, consumer='LVHVBox-rs485-v2',
            config={dir_pin: gpiod.LineSettings(
                direction=Direction.OUTPUT, output_value=Value.INACTIVE)}))
        def direction(transmit):
            lines.set_value(dir_pin, Value.ACTIVE if transmit else Value.INACTIVE)
        # Explicit low before release even if opening UART or executing a read fails.
        stack.callback(direction, False)
        uart = stack.enter_context(serial.Serial(
            port=port, baudrate=38400, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=0.05, write_timeout=1.0, exclusive=True))
        yield PiBus(uart, direction, session, timeout, debug)


DATA_DIR = Path(__file__).resolve().parent


class BusyError(RuntimeError):
    pass


class RS485:
    """Named telemetry and exclusive bus ownership shared by server and CLI.

    Construction loads configuration only. Use ``with RS485() as device`` to
    acquire the UART/GPIO once, read any number of variables, then release them.
    ``bus_factory`` is an optional context-manager factory for offline testing.
    """
    def __init__(self, rules_path=None, calibrations_path=None, *,
                 port='/dev/ttyAMA0', gpiochip='/dev/gpiochip0', dir_pin=24,
                 timeout=6.0, debug=False, bus_factory=None):
        if not math.isfinite(timeout) or timeout < 6:
            raise ValueError('timeout must be finite and at least 6 seconds')
        if type(dir_pin) is not int or dir_pin < 0:
            raise ValueError('dir_pin must be a nonnegative integer')
        self.rules = json.loads(Path(rules_path or DATA_DIR / 'transformations.json').read_text())
        if not isinstance(self.rules, dict) or not self.rules:
            raise ValueError('rules must be a nonempty object')
        for rule in self.rules.values():
            command_ids(rule)
            compile(rule['expression'], '<transformation>', 'eval')
            if rule.get('format', 'float') not in ('float', 'int', 'hex'):
                raise ValueError('unknown transformation format')
        self.calibrations = {}
        path = Path(calibrations_path or DATA_DIR / 'panel_calibrations.csv')
        # Missing calibrations do not disable unrelated variables. Flow is
        # validated before its request is sent, never silently uncalibrated.
        if path.exists():
            with path.open(newline='') as source:
                for row in csv.DictReader(source):
                    values = float(row['factor']), float(row['offset'])
                    if not all(math.isfinite(x) for x in values):
                        raise ValueError('non-finite Flow calibration')
                    self.calibrations[(row['variable'].strip(), row['mn'].strip())] = values
        self._bus_factory = bus_factory or (lambda: open_bus(port, gpiochip, dir_pin, timeout, debug))
        self._bus = None
        self._stack = None
        self.lock = threading.Lock()

    def __enter__(self):
        with self.lock:
            if self._stack is not None:
                raise RuntimeError('RS485 device is already open')
            with ExitStack() as stack:
                self._bus = stack.enter_context(self._bus_factory())
                self._stack = stack.pop_all()
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        # Wait for an active read to finish before releasing the device.
        with self.lock:
            try:
                if self._stack is not None:
                    self._stack.close()
            finally:
                self._stack = self._bus = None

    def parameters(self):
        return {'parameters': [dict(name=name, commands=command_ids(rule),
                                    format=rule.get('format', 'float'), unit=rule.get('unit'))
                               for name, rule in self.rules.items()]}

    def validate(self, address, name, panel=None, *, require_calibration=True):
        if type(address) is not int or not 0 <= address <= 511:
            raise ValueError('address must be 0..511 (ROC/MN address, not LV/HV channel)')
        if name not in self.rules:
            raise ValueError('unknown parameter: ' + name)
        panel = panel or f'MN{address:03d}'
        if require_calibration and name == 'Flow' and ('A0', panel) not in self.calibrations:
            raise ValueError('Flow: no calibration for A0,' + panel)
        return panel

    def preview(self, address, names):
        """Describe wire requests without acquiring GPIO/UART or reserving IDs."""
        requests = []
        for name in names:
            self.validate(address, name, require_calibration=False)
            for command in command_ids(self.rules[name]):
                packet = Packet(REQUEST, address, len(requests) & 0xFFFF, command)
                requests.append(dict(name=name, command=command, request=packet.encode().hex(' ')))
        return requests

    def read(self, address, name, panel=None):
        panel = self.validate(address, name, panel)
        if not self.lock.acquire(blocking=False):
            raise BusyError('RS485 bus is busy; request was not sent')
        try:
            if self._bus is None:
                raise RuntimeError('RS485 device is not open; use it as a context manager')
            rule = self.rules[name]
            # Keep both pressure words under one lock. BusSession.reserve()
            # honors pending holdoff after a timeout even without reopening.
            raw = read_rule(self._bus, address, rule)
            value = convert_value(name, raw, rule, self.calibrations, panel)
            return dict(address=address, panel=panel, name=name, raw=raw,
                        value=value, unit=rule.get('unit'),
                        formatted=format_value(name, raw, rule, self.calibrations, panel),
                        commands=command_ids(rule), atomic=len(command_ids(rule)) == 1,
                        timestamp_utc=datetime.now(timezone.utc).isoformat())
        finally:
            self.lock.release()
