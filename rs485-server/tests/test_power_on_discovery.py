"""Fake hardware plus the actual C-to-Python local notification transport."""
import ctypes
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from power_on_discovery import EVENT, PowerOnDiscovery
from rs485 import BusyError
from discovery_history import DiscoveryHistory
from rs485_server import run_discovery


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.scan = Mock(return_value={'count': 12})
        self.power = Mock()
        self.power.voltages.return_value = [6] * 6
        self.worker = PowerOnDiscovery('/unused', self.scan, self.power)

    def test_boot_delay_then_one_scan(self):
        self.worker.receive(EVENT, 0)
        self.worker.step(4.99)
        self.scan.assert_not_called()
        self.worker.step(5)
        self.worker.step(100)
        self.scan.assert_called_once_with(power_on=True)

    def test_pending_events_coalesce_and_restart_boot_delay(self):
        for now in [0, 1, 2]:
            self.worker.receive(EVENT, now)
        self.worker.step(5)
        self.scan.assert_not_called()
        self.worker.step(7)
        self.scan.assert_called_once_with(power_on=True)

    def test_busy_scan_retried_without_losing_request(self):
        self.scan.side_effect = [BusyError('busy'), {'count': 2}]
        self.worker.receive(EVENT, 0)
        self.worker.step(5)
        self.worker.step(5.1)
        self.assertEqual(self.scan.call_count, 1)
        self.worker.step(5.25)
        self.assertEqual(self.scan.call_count, 2)
        self.assertIsNone(self.worker.due)

    def test_busy_does_not_extend_deadline_forever(self):
        self.scan.side_effect = BusyError('busy')
        self.worker.receive(EVENT, 0)
        self.worker.step(5)
        self.worker.step(66)
        self.assertIsNone(self.worker.due)
        self.assertEqual(self.scan.call_count, 1)

    def test_power_off_before_scan_cancels(self):
        self.power.voltages.return_value = [0] * 6
        self.worker.receive(EVENT, 0)
        self.worker.step(5)
        self.scan.assert_not_called()
        self.assertIsNone(self.worker.due)

    def test_one_channel_at_two_volts_is_on(self):
        self.power.voltages.return_value = [0, 0, 2, 0, 0, 0]
        self.worker.receive(EVENT, 0)
        self.worker.step(5)
        self.scan.assert_called_once()

    def test_unknown_power_retries_then_recovers(self):
        self.power.voltages.side_effect = [TimeoutError('unknown'), [6] * 6]
        self.worker.receive(EVENT, 0)
        self.worker.step(5)
        self.scan.assert_not_called()
        self.worker.step(7)
        self.scan.assert_called_once()

    def test_scan_failure_retries(self):
        self.scan.side_effect = [OSError('UART unavailable'), {'count': 12}]
        self.worker.receive(EVENT, 0)
        self.worker.step(5)
        self.worker.step(7)
        self.assertEqual(self.scan.call_count, 2)

    def test_invalid_or_stopped_event_never_scans(self):
        for payload in (b'powerOn 0', b'', EVENT + b'extra'):
            self.worker.receive(payload, 0)
        self.worker.step(5)
        self.scan.assert_not_called()
        self.worker.receive(EVENT, 0)
        self.worker.stop.set()
        self.worker.step(5)
        self.scan.assert_not_called()


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='rs485-on-', dir='/tmp')
        cls.path = Path(cls.tmp.name) / 'event.sock'
        library = Path(cls.tmp.name) / 'notify.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DRS485_POWER_ON_SOCKET="' + str(cls.path) + '"',
                        str(ROOT.parent / 'lvhv-server/rs485_notify.c'), '-o', str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library), use_errno=True)
        cls.lib.rs485_notify_power_on.argtypes = [ctypes.c_uint, ctypes.c_int]
        cls.lib.rs485_notify_power_on.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_c_sender_only_all_channels_and_success(self):
        with PowerOnDiscovery(self.path, Mock(), Mock()) as worker:
            for channel in range(6):
                self.assertEqual(self.lib.rs485_notify_power_on(channel, 0), 0)
            self.assertEqual(self.lib.rs485_notify_power_on(8, 0), 0)
            self.assertEqual(self.lib.rs485_notify_power_on(6, -1), 0)
            with self.assertRaises(BlockingIOError):
                worker.sock.recv(128)
            self.assertEqual(self.lib.rs485_notify_power_on(6, 0), 0)
            self.assertEqual(worker.sock.recv(128), EVENT)
            self.assertEqual(self.lib.rs485_notify_power_on(7, -1), 0)
            with self.assertRaises(BlockingIOError):
                worker.sock.recv(128)
            self.assertEqual(self.lib.rs485_notify_power_on(7, 0), 0)
            self.assertEqual(worker.sock.recv(128), EVENT)
            with self.assertRaises(BlockingIOError):
                worker.sock.recv(128)
            self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertFalse(self.path.exists())

    def test_unavailable_receiver_returns_without_waiting(self):
        began = time.monotonic()
        self.assertEqual(self.lib.rs485_notify_power_on(6, 0), -1)
        self.assertLess(time.monotonic() - began, 0.5)

    def test_full_socket_queue_does_not_block_sender(self):
        with PowerOnDiscovery(self.path, Mock(), Mock()):
            began = time.monotonic()
            for _ in range(10000):
                if self.lib.rs485_notify_power_on(6, 0) == -1:
                    break
            else:
                self.fail('Could not fill notification queue')
            self.assertLess(time.monotonic() - began, 2)

    def test_c_event_drives_background_scan(self):
        scanned = threading.Event()
        power = Mock(); power.voltages.return_value = [6] * 6
        def scan(*, power_on=False):
            scanned.set()
            return {'count': 12}
        with PowerOnDiscovery(self.path, scan, power, delay=0.01) as worker:
            worker.start()
            self.assertEqual(self.lib.rs485_notify_power_on(6, 0), 0)
            self.assertTrue(scanned.wait(2))
        self.assertFalse(worker.thread.is_alive())

    def test_c_power_on_event_queues_delivers_and_preserves_expected_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = DiscoveryHistory(Path(tmp) / 'history.json', 'test-psu')
            def inventory(addresses):
                return {'scanned': True, 'start': 0, 'end': 300,
                        'addresses': addresses, 'count': len(addresses)}
            history.record(inventory([1,2]), True)
            power = Mock(); power.voltages.return_value = [6] * 6
            telemetry = Mock(); telemetry.discover.return_value = inventory([1])
            scanned = threading.Event()
            def discover(**kwargs):
                result = run_discovery(telemetry, history, power, **kwargs)
                scanned.set()
                return result
            with PowerOnDiscovery(self.path, discover, power, delay=0) as worker:
                worker.start()
                self.assertEqual(self.lib.rs485_notify_power_on(6, 0), 0)
                self.assertTrue(scanned.wait(2))
            restored = DiscoveryHistory(history.path, 'test-psu')
            self.assertEqual(restored.status()['last_discovered'], [1,2])
            self.assertEqual(restored.status()['last_scan']['missing'], [2])
            self.assertEqual(restored.status()['pending_notifications'], 1)
            notifier = Mock(); notifier.users = ['test-recipient']
            restored.deliver(notifier, power)
            notifier.send.assert_called_once()
            recipient, title, body = notifier.send.call_args.args
            self.assertEqual(recipient, 'test-recipient')
            self.assertIn('power-on discovery', title)
            self.assertIn('MN002', body)
            self.assertIn('never requests power-off', body)
            self.assertEqual(restored.status()['pending_notifications'], 0)

    def test_shutdown_waits_for_active_scan_before_releasing_socket(self):
        started = threading.Event(); release = threading.Event(); exited = threading.Event()
        power = Mock(); power.voltages.return_value = [6] * 6
        def scan(*, power_on=False):
            started.set(); release.wait(2)
            return {'count': 1}
        worker = PowerOnDiscovery(self.path, scan, power, delay=0)
        worker.__enter__(); worker.start()
        self.lib.rs485_notify_power_on(6, 0)
        self.assertTrue(started.wait(2))
        def close():
            worker.__exit__(); exited.set()
        closer = threading.Thread(target=close); closer.start()
        try:
            self.assertFalse(exited.wait(0.05))
        finally:
            release.set(); closer.join(3)
        self.assertTrue(exited.is_set())

    def test_regular_file_socket_path_is_not_removed(self):
        self.path.write_text('keep')
        try:
            with self.assertRaises(ValueError):
                PowerOnDiscovery(self.path, Mock(), Mock()).__enter__()
            self.assertEqual(self.path.read_text(), 'keep')
        finally:
            self.path.unlink()


if __name__ == '__main__':
    unittest.main()
