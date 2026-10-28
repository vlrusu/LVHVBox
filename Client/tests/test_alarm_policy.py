"""Policy validation and real monitor imports; all network/GPIO clients are stubbed."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'common'))
import alarm_policy


class AlarmPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = alarm_policy.load_policy(ROOT / 'config/alarm-policy.json')

    def test_preserved_defaults_and_dew_point_trigger(self):
        roc, env = self.policy['roc_temperature'], self.policy['i2c_environment']
        self.assertEqual((roc['high_c'], roc['consecutive_high_samples'], roc['missing_seconds'],
                          roc['minimum_temperature_panels'], roc['power_on_min_v']), (36, 3, 180, 2, 2))
        self.assertEqual((env['temperature_high_c'], env['humidity_high_rh'],
                          env['dew_point_limit_c'] - env['dew_point_margin_c'],
                          env['consecutive_unsafe_samples'], env['missing_samples']), (28, 60, 13, 3, 5))
        self.assertEqual(self.policy['network']['grace_period_seconds'], 1800)
        self.assertEqual(self.policy['ac_power']['gpio21_repeat_window_seconds'], 10)

    def test_rejects_missing_unknown_and_duplicate_keys(self):
        for mutate in (lambda p: p.pop('network'), lambda p: p.update(schema_version=2),
                       lambda p: p.update(schema_version=True),
                       lambda p: p['network'].update(grace_period_second=1),
                       lambda p: p['roc_temperature'].pop('missing_seconds')):
            candidate = copy.deepcopy(self.policy)
            mutate(candidate)
            with self.assertRaises(ValueError):
                alarm_policy.validate_policy(candidate)
        with self.assertRaisesRegex(ValueError, 'duplicate key'):
            alarm_policy.parse_policy('{"schema_version": 1, "schema_version": 1}')

    def test_rejects_nonfinite_bool_string_fractional_counts_and_bad_ranges(self):
        for section, key, value in (
            ('network', 'grace_period_seconds', 0),
            ('network', 'poll_seconds', -1),
            ('ac_power', 'gpio21_repeat_window_seconds', float('inf')),
            ('roc_temperature', 'high_c', float('nan')),
            ('roc_temperature', 'high_c', 10**1000),
            ('roc_temperature', 'consecutive_high_samples', 1.5),
            ('roc_temperature', 'minimum_temperature_panels', 0),
            ('roc_temperature', 'minimum_temperature_panels', 513),
            ('roc_temperature', 'poll_seconds', 19),
            ('i2c_environment', 'humidity_high_rh', 101),
            ('i2c_environment', 'dew_point_margin_c', -1),
            ('i2c_environment', 'missing_samples', True),
            ('i2c_environment', 'temperature_high_c', '28'),
        ):
            with self.subTest(section=section, key=key, value=value):
                candidate = copy.deepcopy(self.policy)
                candidate[section][key] = value
                with self.assertRaisesRegex(ValueError, section + '.' + key):
                    alarm_policy.validate_policy(candidate)

    def test_missing_and_malformed_policy_never_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'alarm-policy.json'
            with patch.dict(os.environ, LVHV_ALARM_POLICY=str(path)):
                with self.assertRaisesRegex(ValueError, 'Invalid alarm policy'):
                    alarm_policy.load_policy()
                path.write_text('{broken')
                with self.assertRaisesRegex(ValueError, 'Invalid alarm policy'):
                    alarm_policy.load_policy()

    def test_all_four_monitors_use_custom_policy_and_ignore_old_numeric_overrides(self):
        custom = copy.deepcopy(self.policy)
        custom['roc_temperature'].update(high_c=42, consecutive_high_samples=4,
            missing_seconds=240, poll_seconds=80, power_on_min_v=2.5, minimum_temperature_panels=3)
        custom['i2c_environment'].update(temperature_high_c=29, humidity_high_rh=65,
            dew_point_limit_c=16, dew_point_margin_c=4, consecutive_unsafe_samples=4,
            missing_samples=6, poll_seconds=35, alert_cooldown_seconds=900,
            missing_alert_cooldown_seconds=7200)
        custom['network'].update(poll_seconds=40, connect_timeout_seconds=4, grace_period_seconds=2000)
        custom['ac_power']['gpio21_repeat_window_seconds'] = 7
        script = r'''
import contextlib, importlib.util, io, json, pathlib, socket, sys, types
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root / 'common'))
import lvhv_protocol
sys.path.remove(str(root / 'common'))  # A preloaded codec must not hide the policy's source fallback.
def forbidden(*a, **kw): raise AssertionError('No network or GPIO calls allowed')
socket.create_connection = forbidden
sys.modules['requests'] = types.ModuleType('requests')
gpio = types.ModuleType('gpiod'); gpio.line = types.ModuleType('gpiod.line')
gpio.line.Bias = gpio.line.Direction = gpio.line.Edge = object()
gpio.request_lines = forbidden
sys.modules.update({'gpiod': gpio, 'gpiod.line': gpio.line})
def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
roc = load('roc_policy_test', 'roc-temperature-monitor/roc_temperature_monitor.py')
env = load('env_policy_test', 'i2c-sensor-alerts/i2c-sensor-alerts.py')
net = load('net_policy_test', 'network-watch/network-watch.py')
ac = load('ac_policy_test', 'pi-health-server/pi-health-server.py')
p = json.loads(pathlib.Path(sys.argv[2]).read_text())
m = roc.Monitor(())
assert (m.threshold, m.count, m.missing_seconds, m.power_cutoff, m.minimum_panels) == (42, 4, 240, 2.5, 3)
m.apply_power([3] * 6, 0); assert not m.alarms(240); assert 'PSU:missing' in m.alarms(241)
m.set_panels(['MN001','MN002']); m.sample('MN001', 20, 242); m.sample('MN002', 20, 242)
m.finish_cycle(242); assert m.last_quorum is None
m.set_panels(['MN001','MN002','MN003']); m.sample('MN003', 20, 242)
m.finish_cycle(242); assert m.last_quorum == 242
with contextlib.redirect_stderr(io.StringIO()):
    try: roc.main(['--threshold', '99'])
    except SystemExit as e: assert e.code == 2
    else: raise AssertionError('Legacy CLI threshold unexpectedly accepted')
assert env.DEFAULT_TEMP_HIGH_C == 29 and env.DEFAULT_HUMID_HIGH_RH == 65
assert env.DEFAULT_DEW_POINT_THRESHOLD_C - env.DEFAULT_DEWPOINT_APPROACH_MARGIN_C == 12
assert (env.DEFAULT_PERIOD_S, env.DEFAULT_CONDITION_STREAK_TRIGGER, env.DEFAULT_NO_DATA_STREAK_TRIGGER,
        env.DEFAULT_ALERT_COOLDOWN_S, env.DEFAULT_NO_DATA_ALERT_COOLDOWN_S) == (35, 4, 6, 900, 7200)
assert (net.DEFAULT_PERIOD_S, net.DEFAULT_CONNECT_TIMEOUT_S, net.DEFAULT_GRACE_PERIOD_S) == (40, 4, 2000)
config = ac.load_action_config(pathlib.Path(sys.argv[3]))
assert config.gpio21_repeat_window_seconds == 7
print('All four monitors use the shared policy; no IO performed')
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            path.write_text(json.dumps(custom))
            ini = Path(directory) / 'actions.ini'
            ini.write_text('[power_actions]\ngpio21_repeat_window_seconds=999\n')
            result = subprocess.run([sys.executable, '-c', script, str(ROOT), str(path), str(ini)],
                env=dict(os.environ, LVHV_ALARM_POLICY=str(path),
                    I2C_SENSOR_ALERTS_TEMP_HIGH_C='999', NETWORK_WATCH_GRACE_PERIOD_S='999',
                    PI_HEALTH_GPIO21_REPEAT_WINDOW_SECONDS='999'),
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('All four monitors use the shared policy', result.stdout)


if __name__ == '__main__':
    unittest.main()
