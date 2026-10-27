"""Deterministic bus ownership and HTTP admission tests with fake hardware."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fair_queue import FairQueue, QueueFull, QueueExpired, QueueCancelled, QueueClosed
import test_rs485_server as http_fixtures
from RS485Connection import RS485Connection


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('Timed out waiting for test condition')
        time.sleep(.005)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.queue = FairQueue()
        self.lock = threading.Lock()
        self.release = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=12)
        self.addCleanup(self.pool.shutdown)
        self.addCleanup(self.release.set)
        self.order = []

    def submit(self, client, label, gate=None, timeout=5, cancel=None, reserve=0):
        def work():
            with self.queue.request(client, timeout, cancel), self.queue.turn(self.lock, reserve):
                self.order.append(label)
                if gate:
                    if not gate.wait(3):
                        raise AssertionError('Test gate not released')
            return label
        return self.pool.submit(work)

    def occupy(self):
        active = self.submit('graphite', 'active', self.release)
        wait_for(lambda: self.queue.status()['active_client'] == 'graphite')
        return active

    def test_waiting_monitor_runs_before_next_graphite(self):
        active = self.occupy()
        g = self.submit('graphite', 'graphite')
        wait_for(lambda: self.queue.status()['pending'] == 1)
        m = self.submit('temperature-monitor', 'monitor')
        wait_for(lambda: self.queue.status()['pending'] == 2)
        self.release.set()
        for f in (active, g, m): f.result(2)
        self.assertEqual(self.order, ['active', 'monitor', 'graphite'])

    def test_all_consumers_get_turns_and_same_consumer_is_fifo(self):
        self.occupy()
        futures = []
        for client in self.queue.CLIENTS:
            for index in range(2):
                futures.append(self.submit(client, f'{client}{index}'))
                wait_for(lambda: self.queue.status()['pending'] == len(futures))
        wait_for(lambda: self.queue.status()['pending'] == 8)
        self.release.set()
        for f in futures: f.result(2)
        self.assertEqual(self.order[1:], [f'{c}{i}' for i in range(2)
                                         for c in ('interactive','discovery','temperature-monitor','graphite')])

    def test_single_consumer_never_waits_for_absent_clients(self):
        for i in range(5): self.submit('graphite', str(i)).result(.5)
        self.assertEqual(self.order, list(map(str, range(5))))

    def test_per_client_bound_rejects_without_execution(self):
        self.occupy()
        a = self.submit('graphite', 'a'); b = self.submit('graphite', 'b')
        wait_for(lambda: self.queue.status()['pending'] == 2)
        with self.assertRaises(QueueFull): self.submit('graphite', 'overflow').result(1)
        self.release.set(); a.result(2); b.result(2)
        self.assertNotIn('overflow', self.order)

    def test_total_capacity_bound(self):
        self.queue.capacity = 1
        self.occupy()
        waiting = self.submit('interactive', 'waiting')
        wait_for(lambda: self.queue.status()['pending'] == 1)
        with self.assertRaises(QueueFull): self.submit('temperature-monitor', 'overflow').result(1)
        self.release.set(); waiting.result(2)

    def test_expired_waiter_never_runs_later(self):
        self.occupy()
        with self.assertRaises(QueueExpired):
            self.submit('interactive', 'stale', timeout=.05).result(1)
        self.release.set()
        self.assertNotIn('stale', self.order)
        self.assertEqual(self.queue.status()['pending'], 0)

    def test_reserve_leaves_time_for_active_transaction(self):
        with self.assertRaises(QueueExpired):
            self.submit('interactive', 'stale', timeout=.1, reserve=.2).result(1)
        self.assertEqual(self.order, [])

    def test_callable_reserve_accounts_for_pending_reply_holdoff(self):
        with self.assertRaises(QueueExpired):
            self.submit('interactive', 'stale', timeout=.1, reserve=lambda: .2).result(1)
        self.assertEqual(self.order, [])

    def test_disconnected_waiter_is_cancelled(self):
        self.occupy()
        gone = threading.Event()
        waiting = self.submit('interactive', 'cancelled', cancel=gone.is_set)
        wait_for(lambda: self.queue.status()['pending'] == 1)
        gone.set()
        with self.assertRaises(QueueCancelled): waiting.result(1)
        self.assertNotIn('cancelled', self.order)

    def test_close_cancels_waiters_but_active_turn_finishes(self):
        active = self.occupy()
        waiting = self.submit('interactive', 'cancelled')
        wait_for(lambda: self.queue.status()['pending'] == 1)
        self.queue.close()
        with self.assertRaises(QueueClosed): waiting.result(1)
        self.assertFalse(active.done())
        self.release.set(); active.result(2)
        with self.assertRaises(QueueClosed): self.submit('graphite', 'new').result(1)

    def test_callback_failure_releases_bus(self):
        with self.assertRaises(ValueError):
            with self.queue.request('interactive', 1), self.queue.turn(self.lock):
                raise ValueError('bad response')
        self.assertFalse(self.lock.locked())
        self.submit('graphite', 'next').result(1)


class HTTPQueueTests(unittest.TestCase):
    setUp = http_fixtures.ServerTests.setUp
    tearDown = http_fixtures.ServerTests.tearDown

    def test_short_budget_expires_without_uart_request(self):
        request = Request(f'http://127.0.0.1:{self.server.server_port}/direct-read?address=1&name=ROC_TEMP',
                          headers={'X-RS485-Timeout': '.1'})
        with self.assertRaises(HTTPError) as error: urlopen(request)
        self.assertEqual(error.exception.code, 408)
        error.exception.close()
        self.bus.read_direct.assert_not_called()

    def test_invalid_queue_headers_never_send(self):
        for headers in ({'X-RS485-Timeout': 'nan'}, {'X-RS485-Timeout': '121'},
                        {'X-RS485-Client': 'new-client'}):
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(f'http://127.0.0.1:{self.server.server_port}/panel-id?address=1', headers=headers))
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        self.bus.read_panel_id.assert_not_called()

    def test_discovery_yields_to_waiting_temperature_and_publishes_atomically(self):
        entered = threading.Event(); release = threading.Event(); sequence = []
        self.telemetry._discovery = {'scanned': True, 'addresses': [99], 'panels': ['MN099']}
        def probe(address, **kwargs):
            sequence.append(f'id{address}')
            if address == 0:
                entered.set(); self.assertTrue(release.wait(3))
            return address
        def temperature(*args):
            sequence.append('temperature'); return 4843
        self.bus.read_panel_id.side_effect = probe
        self.bus.read_direct.side_effect = temperature
        monitor = RS485Connection(port=self.server.server_port, client_id='temperature-monitor')
        with ThreadPoolExecutor(2) as pool:
            scan = pool.submit(self.client.discover, 0, 2)
            try:
                self.assertTrue(entered.wait(2))
                reading = pool.submit(monitor.direct_read, 1, 'ROC_TEMP')
                wait_for(lambda: self.telemetry.queue.status()['pending'] == 1)
                self.assertEqual(self.telemetry.queue.status()['pending_by_client']['temperature-monitor'], 1)
                self.assertEqual(self.client.get_panels()['addresses'], [99])
            finally:
                release.set()
            self.assertEqual(scan.result(3)['addresses'], [0,1,2])
            reading.result(3)
        self.assertEqual(sequence, ['id0','temperature','id1','id2'])

    def test_disconnected_http_request_removed_before_execution(self):
        entered = threading.Event(); release = threading.Event()
        def probe(*args):
            entered.set(); self.assertTrue(release.wait(3)); return 1
        self.bus.read_panel_id.side_effect = probe
        with ThreadPoolExecutor(1) as pool:
            active = pool.submit(self.client.panel_id, 1)
            sock = None
            try:
                self.assertTrue(entered.wait(2))
                sock = socket.create_connection(self.server.server_address)
                sock.sendall(b'GET /direct-read?address=1&name=ROC_TEMP HTTP/1.0\r\nX-RS485-Client: graphite\r\n\r\n')
                wait_for(lambda: self.telemetry.queue.status()['pending'] == 1)
                sock.close(); sock = None
                wait_for(lambda: self.telemetry.queue.status()['cancelled'] == 1)
            finally:
                if sock is not None: sock.close()
                release.set()
            active.result(2)
        self.bus.read_direct.assert_not_called()

    def test_scan_deadline_preserves_previous_completed_inventory(self):
        old = {'scanned': True, 'addresses': [99], 'panels': ['MN099']}
        self.telemetry._discovery = old
        # Probe 0 takes long enough to exhaust the next probe's allowance.
        self.telemetry.transaction_allowance = lambda *a, **k: .02
        def probe(address, **kwargs):
            time.sleep(.1)
            return address
        self.bus.read_panel_id.side_effect = probe
        request = Request(f'http://127.0.0.1:{self.server.server_port}/discover?start=0&end=2',
                          headers={'X-RS485-Timeout': '.08'})
        with self.assertRaises(HTTPError) as error: urlopen(request)
        self.assertEqual(error.exception.code, 408); error.exception.close()
        self.assertEqual(self.bus.read_panel_id.call_count, 1)
        self.assertEqual(self.telemetry.panels(), old)
        self.assertFalse(self.telemetry._scan_lock.locked())

    def test_waiting_recovery_is_cancelled_on_disconnect_and_never_activated(self):
        entered = threading.Event(); release = threading.Event()
        def probe(*args):
            entered.set(); self.assertTrue(release.wait(3)); return 1
        self.bus.read_panel_id.side_effect = probe
        with ThreadPoolExecutor(1) as pool:
            active = pool.submit(self.client.panel_id, 1)
            sock = None
            try:
                self.assertTrue(entered.wait(2))
                sock = socket.create_connection(self.server.server_address)
                body = b'{"address":1,"action":"activate-golden"}'
                sock.sendall(b'POST /recover-golden HTTP/1.0\r\nContent-Type: application/json\r\n'
                             + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
                wait_for(lambda: self.telemetry.queue.status()['pending'] == 1)
                sock.close(); sock = None
                wait_for(lambda: self.telemetry.queue.status()['cancelled'] == 1)
            finally:
                if sock is not None: sock.close()
                release.set()
            active.result(2)
        self.bus.control.assert_not_called()


if __name__ == '__main__': unittest.main()
