import importlib.util
import json
import io
from urllib.error import HTTPError
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'roc_temperature_monitor.py'
spec = importlib.util.spec_from_file_location('monitor', MODULE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakePower:
    def __init__(self, volts=None):
        self.values = volts or [6.0] * 6
        self.off_calls = 0
        self.reads = 0
        self.off_on_recheck = False

    def voltages(self):
        self.reads += 1
        if self.off_on_recheck and self.reads > 1:
            return [0] * 6
        return self.values

    def power_off(self):
        self.off_calls += 1
        self.values = [0] * 6


class FakeTemperatures:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def panels(self):
        return tuple(self.values)

    def read(self, panel, deadline, stop):
        self.calls.append(panel)
        value = self.values[panel]
        if isinstance(value, Exception):
            raise value
        return value


class FakeNotifications:
    users = ['recipient-a', 'recipient-b']

    def __init__(self):
        self.messages = []
        self.fail = set()

    def send(self, user, title, message):
        if user in self.fail:
            raise RuntimeError('network error')
        self.messages.append((user, title, message))


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.monitor = m.Monitor({'MN001': 0, 'MN002': 1})
        self.power = FakePower()
        self.temperatures = FakeTemperatures({'MN001': 37, 'MN002': 30})
        self.notifier = FakeNotifications()
        self.stop = threading.Event()

    def run_cycle(self, now, **kwargs):
        m.cycle(self.monitor, self.power, self.temperatures, self.notifier,
                'psu-test', self.stop, clock=lambda: now, **kwargs)

    def test_three_high_readings_and_default_dry_run(self):
        self.run_cycle(0)
        self.run_cycle(60)
        self.assertFalse(self.notifier.messages)
        self.run_cycle(120)
        self.assertEqual(len(self.notifier.messages), 2)
        self.assertIn('MN001', self.notifier.messages[0][2])
        self.assertIn('DRY RUN', self.notifier.messages[0][2])
        self.assertEqual(self.power.off_calls, 0)
        self.run_cycle(180)
        self.assertEqual(len(self.notifier.messages), 2)

    def test_exact_threshold_is_not_hot(self):
        self.temperatures.values['MN001'] = 36
        for now in (0, 60, 120, 180):
            self.run_cycle(now)
        self.assertFalse(self.notifier.messages)

    def test_failed_sample_breaks_streak_but_not_timer(self):
        self.run_cycle(0)
        self.run_cycle(60)
        self.temperatures.values['MN001'] = TimeoutError()
        self.run_cycle(120)
        self.assertEqual(self.monitor.states['MN001'].high_count, 0)
        self.temperatures.values['MN001'] = 38
        self.run_cycle(180)
        self.run_cycle(240)
        self.assertFalse(self.notifier.messages)
        self.run_cycle(300)
        self.assertEqual(len(self.notifier.messages), 2)

    def test_missing_from_startup_still_monitored_and_strict_timeout(self):
        self.temperatures.values['MN001'] = TimeoutError()
        for now in (0, 60, 120, 180):
            self.run_cycle(now)
        self.assertFalse(self.notifier.messages)
        self.run_cycle(181)
        self.assertEqual(len(self.notifier.messages), 2)
        self.assertIn('Fewer than 2 panels', self.notifier.messages[0][2])

    def test_missing_is_per_panel_not_success_elsewhere(self):
        self.run_cycle(0)
        self.temperatures.values['MN001'] = TimeoutError()
        self.run_cycle(180)
        self.assertFalse(self.notifier.messages)
        self.run_cycle(240)
        self.assertEqual(len(self.notifier.messages), 2)
        self.assertEqual(self.monitor.states['MN002'].last_good, 240)

    def test_off_does_nothing_and_repower_grace(self):
        self.power.values = [0] * 6
        self.run_cycle(0)
        self.run_cycle(500)
        self.assertFalse(self.temperatures.calls)
        self.assertFalse(self.notifier.messages)
        self.power.values = [6] * 6
        self.temperatures.values['MN001'] = TimeoutError()
        self.run_cycle(600)
        self.run_cycle(780)
        self.assertFalse(self.notifier.messages)
        self.run_cycle(781)
        self.assertEqual(len(self.notifier.messages), 2)

    def test_any_one_of_six_channels_powers_every_panel(self):
        for channel in range(6):
            with self.subTest(channel=channel):
                power = FakePower([0] * 6)
                power.values[channel] = 2.0
                temperatures = FakeTemperatures({'MN001': 30, 'MN002': 30})
                m.cycle(m.Monitor(self.monitor.panels), power, temperatures,
                        self.notifier, 'test', self.stop, clock=lambda: 0)
                self.assertEqual(set(temperatures.calls), {'MN001', 'MN002'})

    def test_manual_poweroff_during_reads_suppresses_alarm(self):
        self.monitor.states['MN001'] = m.PanelState(0, 60, 2, 37)
        self.power.off_on_recheck = True
        self.run_cycle(120)
        self.assertFalse(self.notifier.messages)
        self.assertEqual(self.power.off_calls, 0)

    def test_unknown_power_preserves_timer_without_action(self):
        self.run_cycle(0)
        with patch.object(self.power, 'voltages', side_effect=TimeoutError('unavailable')):
            self.run_cycle(240)
        self.assertFalse(self.notifier.messages)
        self.assertEqual(self.monitor.states['MN001'].last_good, 0)
        self.assertEqual(self.monitor.states['MN001'].high_count, 0)

    def test_notification_failure_retries_only_failed_recipient(self):
        self.notifier.fail.add('recipient-b')
        for now in (0, 60, 120):
            self.run_cycle(now)
        self.assertEqual(len(self.notifier.messages), 1)
        self.notifier.fail.clear()
        self.run_cycle(180)
        self.assertEqual(len(self.notifier.messages), 2)
        self.assertEqual(self.notifier.messages[-1][0], 'recipient-b')

    def test_cool_then_hot_rearms(self):
        for now in (0, 60, 120):
            self.run_cycle(now)
        self.temperatures.values['MN001'] = 35
        self.run_cycle(180)
        self.temperatures.values['MN001'] = 37
        for now in (240, 300, 360):
            self.run_cycle(now)
        self.assertEqual(len(self.notifier.messages), 4)

    def test_explicit_live_mode_calls_local_off_and_verifies(self):
        self.monitor.states['MN001'] = m.PanelState(0, 60, 2, 37)
        self.run_cycle(120, dry_run=False)
        self.assertEqual(self.power.off_calls, 1)
        self.assertIn('All six measured', self.notifier.messages[0][2])

    def test_all_v6_below_two_never_reads_or_alerts(self):
        for index, value in enumerate([0.98, 1.083, 1.108, 1.13, 1.148,
                                       0.979, 1.124, 1.051, 1.999, 0.8]):
            self.power.values = [value] * 6
            self.run_cycle(index * 60)
        self.assertFalse(self.temperatures.calls)
        self.assertFalse(self.notifier.messages)
        self.assertTrue(all(s.powered_since is None for s in self.monitor.states.values()))

    def test_all_v6_below_two_resets_all_timers_and_alarms(self):
        for now in (0, 60, 120):
            self.run_cycle(now)
        self.assertTrue(self.monitor.delivered)
        self.temperatures.calls.clear()
        self.power.values = [1.999] * 6
        self.run_cycle(240)
        self.assertFalse(self.temperatures.calls)
        self.assertFalse(self.monitor.delivered)
        self.assertTrue(all(s == m.PanelState() for s in self.monitor.states.values()))

    def test_single_powered_channel_detects_missing_panels_on_other_channels(self):
        self.power.values = [0, 0, 0, 0, 2.1, 0]
        self.temperatures.values['MN001'] = TimeoutError()
        for now in (0, 60, 120, 181):
            self.run_cycle(now)
        self.assertEqual(len(self.notifier.messages), 2)
        self.assertIn('Fewer than 2 panels', self.notifier.messages[0][2])

    def test_all_v6_drop_below_two_before_alert_suppresses_it(self):
        self.monitor.states['MN001'] = m.PanelState(0, 60, 2, 37)
        with patch.object(self.power, 'voltages', side_effect=[[6] * 6, [1.999] * 6]):
            self.run_cycle(120)
        self.assertFalse(self.notifier.messages)
        self.assertEqual(self.power.off_calls, 0)

    def test_psu9_never_monitors_undiscovered_panels(self):
        self.monitor = m.Monitor(())
        self.temperatures = FakeTemperatures({'MN153': 25, 'MN280': 27})
        for now in (0, 60, 120, 181, 600):
            self.run_cycle(now)
        self.assertEqual(set(self.monitor.states), {'MN153', 'MN280'})
        self.assertNotIn('MN138', self.temperatures.calls)
        self.assertNotIn('MN272', self.temperatures.calls)
        self.assertFalse(self.notifier.messages)

    def test_refresh_removes_panel_and_its_hot_alarm(self):
        for now in (0, 60, 120):
            self.run_cycle(now)
        self.assertIn('MN001:hot', self.monitor.delivered)
        del self.temperatures.values['MN001']
        self.run_cycle(180)
        self.assertNotIn('MN001', self.monitor.states)
        self.assertNotIn('MN001:hot', self.monitor.delivered)
        self.assertEqual(len(self.notifier.messages), 2)

    def test_two_good_panels_tolerate_any_number_of_missing_panels(self):
        self.temperatures = FakeTemperatures({'MN001': 25, 'MN002': 26,
                                              'MN003': TimeoutError(), 'MN004': TimeoutError()})
        for now in (0, 60, 120, 240, 600):
            self.run_cycle(now)
        self.assertFalse(self.notifier.messages)
        self.assertEqual(self.monitor.last_quorum, 600)

    def test_coverage_recovery_rearms_single_psu_alarm(self):
        self.temperatures.values = {'MN001': TimeoutError(), 'MN002': 25}
        for now in (0, 181, 240):
            self.run_cycle(now)
        self.assertEqual(len(self.notifier.messages), 2)
        self.temperatures.values['MN001'] = 25
        self.run_cycle(300)
        self.assertNotIn('PSU:missing', self.monitor.delivered)
        self.temperatures.values['MN001'] = TimeoutError()
        self.run_cycle(480)
        self.assertEqual(len(self.notifier.messages), 2)
        self.run_cycle(481)
        self.assertEqual(len(self.notifier.messages), 4)

    def test_discovery_http_outage_preserves_known_missing_panels(self):
        self.temperatures.values['MN001'] = TimeoutError()
        self.run_cycle(0)
        with patch.object(self.temperatures, 'panels', side_effect=TimeoutError()):
            self.run_cycle(181)
        self.assertIn('PSU:missing', self.monitor.delivered)

    def test_empty_discovery_with_power_on_alarms_after_three_minutes(self):
        self.run_cycle(0)
        self.temperatures.values.clear()
        self.temperatures.calls.clear()
        self.run_cycle(600)
        self.assertEqual(self.monitor.states, {})
        self.assertFalse(self.temperatures.calls)
        self.assertIn('PSU:missing', self.monitor.delivered)

    def test_no_discovery_with_power_on_reports_insufficient_coverage(self):
        self.monitor = m.Monitor(())
        with patch.object(self.temperatures, 'panels', side_effect=TimeoutError()):
            self.run_cycle(0)
            self.run_cycle(600)
        self.assertFalse(self.temperatures.calls)
        self.assertIn('PSU:missing', self.monitor.delivered)

    def test_state_survives_restart_without_exposing_credentials(self):
        self.run_cycle(0)
        self.run_cycle(60)
        self.run_cycle(120)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            with patch.object(m.time, 'monotonic', return_value=120):
                m.save(path, 'boot-policy', self.monitor)
            self.assertNotIn('recipient-a', path.read_text())
            restored = m.Monitor(())
            m.restore(path, 'boot-policy', restored, 130)
            self.assertEqual(restored.states, self.monitor.states)
            self.assertEqual(restored.delivered, self.monitor.delivered)
            rebooted = m.Monitor(self.monitor.panels)
            m.restore(path, 'new-boot', rebooted, 130)
            self.assertIsNone(rebooted.states['MN001'].last_good)


class LiveTransitionTests(unittest.TestCase):
    setUp = LogicTests.setUp
    run_cycle = LogicTests.run_cycle

    def test_dry_run_to_live_preserves_timers_and_notifies_real_shutdown(self):
        for now in (0, 60, 120):
            self.run_cycle(now)
        for legacy in (False, True):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'state.json'
                with patch.object(m.time, 'monotonic', return_value=120):
                    m.save(path, 'boot-policy', self.monitor)
                if legacy:
                    data = json.loads(path.read_text())
                    data.pop('dry_run')
                    path.write_text(json.dumps(data))
                restored = m.Monitor(())
                m.restore(path, 'boot-policy', restored, 130, dry_run=False)
                self.assertEqual(restored.states, self.monitor.states)
                self.assertEqual(restored.powered_since, self.monitor.powered_since)
                self.assertEqual(restored.last_quorum, self.monitor.last_quorum)
                self.assertFalse(restored.delivered)
                power, notifier = FakePower(), FakeNotifications()
                m.cycle(restored, power, self.temperatures, notifier, 'psu-test',
                        self.stop, dry_run=False, clock=lambda: 130)
                self.assertEqual(power.off_calls, 1)
                self.assertEqual(len(notifier.messages), 2)
                self.assertTrue(all('powerOff(channel 6) sent' in msg[2]
                                    for msg in notifier.messages))

    def test_live_restart_retains_delivery_latches(self):
        for now in (0, 60, 120):
            self.run_cycle(now)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            with patch.object(m.time, 'monotonic', return_value=120):
                m.save(path, 'boot-policy', self.monitor, dry_run=False)
            restored = m.Monitor(())
            m.restore(path, 'boot-policy', restored, 130, dry_run=False)
            self.assertEqual(restored.delivered, self.monitor.delivered)

    def test_live_missing_quorum_shuts_down_empty_discovery(self):
        self.temperatures.values = {}
        for now in (0, 60, 120, 180):
            self.run_cycle(now, dry_run=False)
        self.assertEqual(self.power.off_calls, 0)
        self.run_cycle(181, dry_run=False)
        self.assertEqual(self.power.off_calls, 1)
        self.assertEqual(len(self.notifier.messages), 2)
        self.assertTrue(all('Fewer than 2' in msg[2] for msg in self.notifier.messages))

    def test_live_power_off_recheck_suppresses_shutdown(self):
        self.monitor.states['MN001'] = m.PanelState(0, 60, 2, 37)
        self.power.off_on_recheck = True
        self.run_cycle(120, dry_run=False)
        self.assertEqual(self.power.off_calls, 0)
        self.assertFalse(self.notifier.messages)


class HTTPTests(unittest.TestCase):
    def test_cached_discovery_validates_addresses_and_accepts_empty_scan(self):
        client = m.TemperatureClient()
        for payload in ({'scanned': False, 'addresses': []},
                        {'scanned': True, 'addresses': [153,153]},
                        {'scanned': True, 'addresses': [True]},
                        {'scanned': True, 'addresses': [512]},
                        {'scanned': True, 'addresses': ['153']},
                        {'scanned': True}, []):
            with self.subTest(payload=payload), patch.object(m, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaises(ValueError):
                    client.panels()
        for addresses, expected in (([280,153], ('MN153','MN280')), ([], ())):
            payload = {'scanned': True, 'addresses': addresses}
            with patch.object(m, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as request:
                self.assertEqual(client.panels(), expected)
                self.assertTrue(request.call_args.args[0].endswith('/panels'))

    def test_direct_response_must_match_panel_parameter_and_source(self):
        client = m.TemperatureClient()
        payload = {'panel': 'MN001', 'name': 'ROC_TEMP', 'source': 'FPGA TVS', 'value': 37}
        for update in ({'panel': 'MN002'}, {'name': 'Flow'}, {'source': 'CPU'}, {'value': float('nan')}, {'value': True}):
            with self.subTest(update=update), patch.object(m, 'urlopen', return_value=io.BytesIO(json.dumps({**payload, **update}).encode())):
                with self.assertRaises(ValueError):
                    client.read('MN001', m.time.monotonic() + 10, threading.Event())
        with patch.object(m, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            self.assertEqual(client.read('MN001', m.time.monotonic() + 10, threading.Event()), 37)
            self.assertIn('/direct-read?address=1&name=ROC_TEMP', request.call_args.args[0].full_url)
            self.assertEqual(request.call_args.args[0].get_header('X-rs485-client'), 'temperature-monitor')

    def test_server_timeout_is_not_retried(self):
        client = m.TemperatureClient()
        with patch.object(m, 'urlopen', side_effect=HTTPError('url', 504, 'timeout', {}, None)) as request:
            with self.assertRaisesRegex(RuntimeError, '504'):
                client.read('MN001', m.time.monotonic() + 10, threading.Event())
            self.assertEqual(request.call_count, 1)

    def test_bus_busy_can_retry_without_counting_as_multiple_readings(self):
        payload = {'panel': 'MN001', 'name': 'ROC_TEMP', 'source': 'FPGA TVS', 'value': 37}
        with patch.object(m, 'urlopen', side_effect=[HTTPError('url', 409, 'busy', {}, None), io.BytesIO(json.dumps(payload).encode())]) as request:
            self.assertEqual(m.TemperatureClient().read('MN001', m.time.monotonic() + 10, threading.Event()), 37)
            self.assertEqual(request.call_count, 2)

    def test_pushover_error_does_not_expose_credentials(self):
        with patch.dict(m.os.environ, {'ROC_MONITOR_PUSHOVER_API_TOKEN': 'secret-token', 'ROC_MONITOR_PUSHOVER_USER_KEY': 'secret-user'}):
            notifier = m.Pushover()
        with patch.object(m, 'urlopen', side_effect=RuntimeError('secret-token secret-user')):
            with self.assertRaises(RuntimeError) as raised:
                notifier.send('secret-user', 'test', 'test')
            self.assertNotIn('secret', str(raised.exception))

    def test_missing_panels_produce_one_psu_alarm(self):
        monitor = m.Monitor({f'MN{i:03d}': i % 6 for i in range(12)})
        monitor.apply_power([6] * 6, 0)
        notifier = FakeNotifications()
        m.notify(monitor, monitor.alarms(181), notifier, 'psu-test', 'DRY RUN')
        self.assertEqual(len(notifier.messages), 2)
        self.assertTrue(all(len(msg[2]) <= 1024 for msg in notifier.messages))
        self.assertEqual(len(monitor.delivered), 1)


class ProtocolTests(unittest.TestCase):
    def test_fragmented_lv_reply_and_exact_read_command(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        received = []
        def serve():
            with listener:
                for values in ([6., 6., 0., 0., 6., 6.],):
                    with listener.accept()[0] as conn:
                        request = b''
                        while len(request) < 46:
                            request += conn.recv(46 - len(request))
                        received.append(request)
                        reply = struct.pack('=I', 2) + m.LVHVClient.block('C', [b'L', b'V', b'H', b'V']) + m.LVHVClient.block('F', values)
                        for byte in reply:
                            conn.sendall(bytes([byte]))
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        client = m.LVHVClient(MODULE.parents[1] / 'commands.h', port=listener.getsockname()[1])
        self.assertEqual(client.voltages(), (6, 6, 0, 0, 6, 6))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIn(struct.pack('=I', client.codes['COMMAND_readMonV6']), received[0])
        for request in received:
            self.assertNotIn(struct.pack('=I', client.codes['COMMAND_powerOff']), request)

    def test_negative_nan_and_malformed_power_are_unknown(self):
        client = m.LVHVClient(MODULE.parents[1] / 'commands.h')
        for reply in [(b'F', (6,)*5), (b'I', (-1,)), (b'F', (float('nan'),)*6), (b'F', (-1,)*6)]:
            with self.subTest(reply=reply), patch.object(client, 'request', return_value=reply):
                with self.assertRaises(ValueError):
                    client.voltages()

    def test_powered_off_adc_offset_is_valid(self):
        client = m.LVHVClient(MODULE.parents[1] / 'commands.h')
        values = (0.01, 0.02, 0.03, -0.1277, 0.002, 0.008)
        with patch.object(client, 'request', return_value=(b'F', values)):
            self.assertEqual(client.voltages(), values)

    def test_header_commands_used_instead_of_hardcoded_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'commands.h'
            path.write_text('#define TYPE_lv 10\n#define COMMAND_powerOff 11\n#define COMMAND_readMonV6 12\n')
            client = m.LVHVClient(path)
            self.assertEqual(client.codes['COMMAND_readMonV6'], 12)


if __name__ == '__main__':
    unittest.main()
