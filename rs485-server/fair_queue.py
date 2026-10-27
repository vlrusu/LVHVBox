"""Bounded round-robin admission to one UART; callers execute their own turn."""
from collections import deque
from contextlib import contextmanager
import threading
import time
import math


class BusyError(RuntimeError):
    pass


class QueueFull(BusyError):
    pass


class QueueExpired(TimeoutError):
    pass


class QueueCancelled(RuntimeError):
    pass


class QueueClosed(RuntimeError):
    pass


class FairQueue:
    CLIENTS = ('temperature-monitor', 'graphite', 'interactive', 'discovery')

    def __init__(self, per_client=2, capacity=8):
        self.per_client, self.capacity = per_client, capacity
        self.condition = threading.Condition()
        self.local = threading.local()
        self.waiting = {client: deque() for client in self.CLIENTS}
        self.active = None
        self.last = len(self.CLIENTS) - 1
        self.closed = False
        self.counts = dict(completed=0, expired=0, cancelled=0, rejected=0)

    @contextmanager
    def request(self, client, timeout, disconnected=None):
        if client not in self.CLIENTS:
            raise ValueError('unknown RS485 client')
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('RS485 request timeout must be positive and finite')
        previous = getattr(self.local, 'request', None)
        self.local.request = (client, time.monotonic() + timeout, disconnected)
        try:
            yield
        finally:
            self.local.request = previous

    @contextmanager
    def as_client(self, client):
        previous = getattr(self.local, 'request', None)
        if previous is not None:
            self.local.request = (client, *previous[1:])
        try:
            yield
        finally:
            self.local.request = previous

    def _next(self):
        for offset in range(1, len(self.CLIENTS) + 1):
            client = self.CLIENTS[(self.last + offset) % len(self.CLIENTS)]
            if self.waiting[client]:
                return client

    def status(self):
        with self.condition:
            return dict(active_client=self.active, pending=sum(map(len, self.waiting.values())),
                        pending_by_client={k: len(v) for k, v in self.waiting.items()},
                        capacity=self.capacity, per_client_limit=self.per_client,
                        closed=self.closed, **self.counts)

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()

    @contextmanager
    def turn(self, device_lock, reserve=0):
        request = getattr(self.local, 'request', None)
        if request is None:
            # Keep the direct, in-process API's nonblocking behavior. Production
            # HTTP and automatic discovery always supply a request context.
            if not device_lock.acquire(blocking=False):
                raise BusyError('RS485 bus is busy; request was not sent')
            try:
                yield
            finally:
                device_lock.release()
            return

        client, deadline, disconnected = request
        ticket = object()
        with self.condition:
            if self.closed:
                raise QueueClosed('RS485 queue is stopping; request was not sent')
            if self.active is None and device_lock.locked():
                raise BusyError('RS485 bus is busy outside queue; request was not sent')
            if (len(self.waiting[client]) >= self.per_client or
                    sum(map(len, self.waiting.values())) >= self.capacity):
                self.counts['rejected'] += 1
                raise QueueFull('RS485 queue is full; request was not sent')
            self.waiting[client].append(ticket)
            try:
                while True:
                    if self.closed:
                        raise QueueClosed('RS485 queue is stopping; request was not sent')
                    allowance = reserve() if callable(reserve) else reserve
                    remaining = deadline - allowance - time.monotonic()
                    if remaining <= 0:
                        self.counts['expired'] += 1
                        raise QueueExpired('RS485 deadline expired before next transaction; no new UART request sent')
                    if disconnected is not None and disconnected():
                        self.counts['cancelled'] += 1
                        raise QueueCancelled('RS485 caller disconnected; no new UART request sent')
                    if (self.active is None and self._next() == client and
                            self.waiting[client][0] is ticket and device_lock.acquire(blocking=False)):
                        self.waiting[client].popleft()
                        self.active = client
                        self.last = self.CLIENTS.index(client)
                        break
                    self.condition.wait(min(0.05, remaining))
            except BaseException:
                self.waiting[client].remove(ticket)
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            with self.condition:
                device_lock.release()
                self.active = None
                self.counts['completed'] += 1
                self.condition.notify_all()
