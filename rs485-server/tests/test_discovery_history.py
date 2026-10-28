"""Offline discovery persistence and notification-only startup changes."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from discovery_history import DiscoveryHistory, PowerReader
import lvhv_protocol as protocol
from rs485_server import run_discovery


def scan(addresses, start=0, end=300):
    return {'scanned': True, 'addresses': addresses, 'start': start, 'end': end,
            'timestamp_utc': '2026-09-26T12:00:00Z'}


class Notifications:
    users = ['first', 'second']
    def __init__(self):
        self.calls = []
        self.fail = set()
    def send(self, user, title, body):
        if user in self.fail:
            raise RuntimeError('not delivered')
        self.calls.append((user, title, body))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'history.json'
        self.history = DiscoveryHistory(self.path, 'test-psu')

    def test_first_scan_saves_discovery_without_inventing_missing_panels(self):
        self.history.record(scan([153,280]), True, startup=True)
        self.assertEqual(self.history.status()['last_discovered'], [153,280])
        self.assertEqual(self.history.status()['pending_notifications'], 0)

    def test_next_startup_detects_only_newly_missing_and_survives_restart(self):
        self.history.record(scan([138,153,272]), True, startup=True)
        self.history = DiscoveryHistory(self.path, 'test-psu')
        self.history.record(scan([153]), True, startup=True)
        restored = DiscoveryHistory(self.path)
        self.assertEqual(restored.status()['last_scan']['missing'], [138,272])
        self.assertEqual(restored.status()['last_discovered'], [153])
        notifier = Notifications()
        restored.deliver(notifier)
        self.assertEqual(len(notifier.calls), 2)
        self.assertIn('MN138, MN272', notifier.calls[0][2])
        self.assertIn('Notification only', notifier.calls[0][2])
        restored = DiscoveryHistory(self.path)
        restored.deliver(notifier)
        self.assertEqual(len(notifier.calls), 2)
        self.assertNotIn('first', self.path.read_text())

    def test_partial_notification_failure_retries_only_failed_recipient(self):
        self.history.record(scan([1,2]), True)
        self.history.record(scan([1]), True, startup=True)
        notifier = Notifications();notifier.fail.add('first')
        self.history.deliver(notifier)
        self.assertEqual([x[0] for x in notifier.calls], ['second'])
        notifier.fail.clear()
        self.history = DiscoveryHistory(self.path)
        self.history.deliver(notifier)
        self.assertEqual([x[0] for x in notifier.calls], ['second','first'])
        self.assertEqual(self.history.status()['pending_notifications'], 0)

    def test_off_and_unknown_do_not_erase_last_discovery_or_notify(self):
        self.history.record(scan([1,2]), True)
        for powered in (False,None):
            self.history.record(scan([]), powered, startup=True)
            self.assertEqual(self.history.status()['last_discovered'], [1,2])
            self.assertEqual(self.history.status()['pending_notifications'], 0)

    def test_pending_notification_waits_while_power_is_off(self):
        self.history.record(scan([1,2]), True)
        self.history.record(scan([1]), True, startup=True)
        notifier=Notifications();power=Mock();power.voltages.return_value=[0]*6
        self.history.deliver(notifier,power)
        self.assertEqual(notifier.calls,[])
        self.assertEqual(self.history.status()['pending_notifications'],1)
        power.voltages.return_value=[0,0,0,0,0,2]
        self.history.deliver(notifier,power)
        self.assertEqual(len(notifier.calls),2)

    def test_partial_scan_preserves_unprobed_addresses(self):
        self.history.record(scan([1,2,100]), True)
        self.history.record(scan([2],0,10), True, startup=True)
        self.assertEqual(self.history.status()['last_discovered'], [2,100])
        self.assertEqual(self.history.status()['last_scan']['missing'], [1])

    def test_manual_scan_updates_baseline_without_startup_notification(self):
        self.history.record(scan([1,2]), True)
        self.history.record(scan([1]), True)
        self.assertEqual(self.history.status()['last_discovered'], [1])
        self.assertEqual(self.history.status()['pending_notifications'], 0)

    def test_full_loss_while_on_warns_without_any_power_write_interface(self):
        self.history.record(scan([1,2]), True)
        self.history.record(scan([]), True, startup=True)
        notifier = Notifications();self.history.deliver(notifier)
        self.assertEqual(len(notifier.calls), 2)
        self.assertFalse(hasattr(PowerReader, 'power_off'))

    def test_large_loss_is_chunked_below_pushover_limit(self):
        self.history.record(scan(list(range(512)),0,511), True)
        self.history.record(scan([],0,511), True, startup=True)
        notifier = Notifications();self.history.deliver(notifier)
        self.assertTrue(all(len(msg[2]) <= 1024 for msg in notifier.calls))

    def test_incomplete_or_invalid_scan_does_not_change_saved_list(self):
        self.history.record(scan([1,2]), True)
        before = self.path.read_text()
        for payload in ({'scanned': False}, scan([True]), scan([512]), scan([1,1]), scan([11],0,10)):
            with self.assertRaises(ValueError):
                self.history.record(payload, True, startup=True)
            self.assertEqual(self.path.read_text(), before)

    def test_corrupt_history_is_not_silently_overwritten(self):
        self.path.write_text('bad json')
        with self.assertRaises(ValueError):DiscoveryHistory(self.path)
        self.assertEqual(self.path.read_text(), 'bad json')

    def test_uart_failure_preserves_history(self):
        self.history.record(scan([1,2]), True)
        telemetry=Mock();telemetry.discover.side_effect=OSError('UART unavailable')
        power=Mock();power.voltages.return_value=[6]*6
        with self.assertRaises(OSError):run_discovery(telemetry,self.history,power,startup=True)
        self.assertEqual(self.history.status()['last_discovered'], [1,2])
        self.assertEqual(self.history.status()['pending_notifications'], 0)

    def test_power_off_during_scan_preserves_baseline(self):
        self.history.record(scan([1,2]), True)
        telemetry=Mock();telemetry.discover.return_value=scan([])
        power=Mock();power.voltages.side_effect=[[6]*6,[0]*6]
        run_discovery(telemetry,self.history,power,startup=True)
        self.assertEqual(self.history.status()['last_discovered'], [1,2])
        self.assertEqual(self.history.status()['pending_notifications'], 0)
        self.assertEqual([c[0] for c in power.mock_calls], ['voltages','voltages'])
        telemetry.recovery.assert_not_called()

    def test_two_power_samples_at_threshold_allow_startup_warning(self):
        self.history.record(scan([1,2]), True)
        telemetry=Mock();telemetry.discover.return_value=scan([1])
        power=Mock();power.voltages.return_value=[0,0,0,0,0,2]
        run_discovery(telemetry,self.history,power,startup=True)
        self.assertEqual(self.history.status()['pending_notifications'], 1)


class ReadOnlyPowerTests(unittest.TestCase):
    def test_fragmented_reply_and_only_read_voltage_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            header=Path(tmp)/'commands.h'
            header.write_text('#define TYPE_lv 123\n#define COMMAND_readMonV6 456\n')
            reader=PowerReader(header)
        reply=protocol.encode_message([('C',(b'L',b'V',b'H',b'V')),('F',(6,0,0,0,0,0))])
        sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
        data=bytearray(reply)
        def recv(size):
            b=bytes(data[:1]);del data[:1];return b
        sock.recv.side_effect=recv
        with patch('discovery_history.socket.create_connection',return_value=sock) as connect:
            self.assertEqual(reader.voltages(), (6,0,0,0,0,0))
        connect.assert_called_once_with(('127.0.0.1',12000),5)
        self.assertEqual(sock.sendall.call_count,1)
        # Golden request keeps the command/header codes and all-channel selector.
        self.assertEqual(sock.sendall.call_args.args[0],
            bytes.fromhex('05000000 43040000004c564856 5501000000c8010000 '
                          '55010000007b000000 430100000006 460100000000000000'))

    def test_bad_voltage_is_unknown(self):
        reader=PowerReader(ROOT.parent/'commands.h')
        for values in ((0,)*5, (-1,)*6, (-2,)*6, (float('nan'),)*6, (float('inf'),)*6):
            with patch.object(reader,'request',return_value=(b'F',values)), self.assertRaises(ValueError):
                reader.voltages()

    def test_signed_adc_noise_zero_and_powered_values_remain_valid(self):
        reader=PowerReader(ROOT.parent/'commands.h')
        values=(-.1,0.,1.,2.,5.9,6.)
        with patch.object(reader,'request',return_value=(b'F',values)):
            self.assertEqual(reader.voltages(),values)

    def test_invalid_frames_are_unknown_power_without_retry(self):
        magic=('C',(b'L',b'V',b'H',b'V'))
        good=protocol.encode_message([magic,('F',(6.,)*6)])
        frames=(good[:-1], struct.pack('<I',0), struct.pack('<I',9),
                protocol.encode_message([('C',(b'N',)),('F',(6.,)*6)]),
                protocol.encode_message([magic,('F',(6.,)*6),('I',(0,))]),
                protocol.encode_message([magic,('I',(6,)*6)]),
                protocol.encode_message([magic,('F',(6.,)*5)]),
                protocol.encode_message([magic,('F',(-1.,)*6)]),
                protocol.encode_message([magic,('F',(float('nan'),)*6)]),
                struct.pack('<I',2)+protocol.encode_block(*magic)+b'F'+struct.pack('<I',65))
        reader=PowerReader(ROOT.parent/'commands.h')
        for frame in frames:
            sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
            data=bytearray(frame)
            def recv(size):
                result=bytes(data[:min(size,2)]);del data[:len(result)];return result
            sock.recv.side_effect=recv
            with self.subTest(frame=frame), patch('discovery_history.socket.create_connection',return_value=sock) as connect:
                with self.assertRaises((ValueError,ConnectionError)):
                    reader.voltages()
            self.assertEqual(sock.sendall.call_count,1)
            self.assertEqual(connect.call_count,1)
            sock.__exit__.assert_called_once()

    def test_closed_reply_preserves_inventory_in_real_discovery_path(self):
        reader=PowerReader(ROOT.parent/'commands.h')
        sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
        sock.recv.return_value=b''
        with tempfile.TemporaryDirectory() as tmp:
            history=DiscoveryHistory(Path(tmp)/'history.json','test-psu')
            history.record(scan([1,2]),True)
            telemetry=Mock();telemetry.discover.return_value=scan([])
            with patch('discovery_history.socket.create_connection',return_value=sock), self.assertLogs(level='ERROR'):
                run_discovery(telemetry,history,reader,startup=True)
            self.assertEqual(history.status()['last_discovered'],[1,2])
            self.assertEqual(history.status()['pending_notifications'],0)

    def test_connection_time_is_included_in_deadline(self):
        reader=PowerReader(ROOT.parent/'commands.h',timeout=5.)
        sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
        with patch('discovery_history.socket.create_connection',return_value=sock), \
                patch('discovery_history.time.monotonic',side_effect=[0.,6.]):
            with self.assertRaises(TimeoutError):
                reader.voltages()
        sock.sendall.assert_not_called()


if __name__=='__main__':unittest.main()
