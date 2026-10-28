"""Local LVHV all-channel power-on events schedule read-only RS485 discovery."""
import logging
import os
from pathlib import Path
import select
import socket
import stat
import threading
import time

from rs485 import BusyError

LOG = logging.getLogger('rs485-power-on')
EVENT = b'lv-all-on-v1'


class PowerOnDiscovery:
    def __init__(self, path, discover, power_reader, delay=5, retry_seconds=60):
        self.path = Path(path)
        self.discover = discover
        self.power_reader = power_reader
        self.delay = delay
        self.retry_seconds = retry_seconds
        self.due = self.expires = None
        self.stop = threading.Event()
        self.thread = None
        self.sock = None

    def __enter__(self):
        # Main enters this only after taking exclusive ownership of the UART.
        # A leftover socket from a crashed instance can therefore be removed.
        try:
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise ValueError('Power-on socket path exists and is not a socket')
            self.path.unlink()
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.sock.bind(str(self.path))
            os.chmod(self.path, 0o600)  # service account and root LVHV only
            self.sock.setblocking(False)
        except Exception:
            self.sock.close()
            raise
        return self

    def start(self):
        self.thread = threading.Thread(target=self.run, name='power-on-discovery')
        self.thread.start()

    def receive(self, payload, now):
        if payload != EVENT:
            LOG.warning('Ignored invalid local power-on event')
            return
        if self.due is None:
            LOG.warning('All-channel LV power-on: discovery scheduled after %.1fs', self.delay)
        # Coalesce pending requests and restart the boot delay on another powerOn.
        self.due = now + self.delay
        self.expires = self.due + self.retry_seconds

    def step(self, now):
        if self.due is None or now < self.due or self.stop.is_set():
            return
        if now > self.expires:
            LOG.error('Power-on discovery expired: power unavailable or RS485 bus busy')
            self.due = self.expires = None
            return
        try:
            if self.power_reader is None:
                raise RuntimeError('V6 reader unavailable')
            if not any(v >= 2 for v in self.power_reader.voltages()):
                LOG.warning('Power-on discovery cancelled: PSU is OFF')
                self.due = self.expires = None
                return
            if self.stop.is_set():
                return
            result = self.discover(power_on=True)
        except BusyError:
            self.due = now + 0.25
            return
        except (OSError, ValueError, RuntimeError):
            LOG.exception('Power-on discovery failed; retrying within request window')
            self.due = now + 2
            return
        LOG.warning('Power-on discovery completed: %d panels', result['count'])
        self.due = self.expires = None

    def run(self):
        while not self.stop.is_set():
            if select.select([self.sock], [], [], 0.25)[0]:
                # Bound draining so even a sender flood cannot starve stop checks.
                for _ in range(64):
                    try:
                        self.receive(self.sock.recv(128), time.monotonic())
                    except BlockingIOError:
                        break
            self.step(time.monotonic())

    def __exit__(self, *args):
        self.stop.set()
        if self.thread is not None:
            # Finish any read-only scan before the outer context closes the UART.
            self.thread.join()
        if self.sock is not None:
            self.sock.close()
            self.path.unlink(missing_ok=True)
