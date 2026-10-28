"""Strict, hardware-free loader for the single nonsecret alarm policy file."""
import argparse
import json
import math
import os
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'config' / 'alarm-policy.json'
# Validation rules only: all operational values live in the JSON file.
RULES = {
    'roc_temperature': {
        'high_c': ('number', None, None),
        'consecutive_high_samples': ('int', 1, None),
        'missing_seconds': ('positive', None, None),
        'poll_seconds': ('number', 20, None),
        'power_on_min_v': ('positive', None, None),
        'minimum_temperature_panels': ('int', 1, 512),
    },
    'i2c_environment': {
        'temperature_high_c': ('number', None, None),
        'humidity_high_rh': ('number', 0, 100),
        'dew_point_limit_c': ('number', None, None),
        'dew_point_margin_c': ('number', 0, None),
        'consecutive_unsafe_samples': ('int', 1, None),
        'missing_samples': ('int', 1, None),
        'poll_seconds': ('positive', None, None),
        'alert_cooldown_seconds': ('number', 0, None),
        'missing_alert_cooldown_seconds': ('number', 0, None),
    },
    'network': {
        'poll_seconds': ('positive', None, None),
        'connect_timeout_seconds': ('positive', None, None),
        'grace_period_seconds': ('positive', None, None),
    },
    'ac_power': {'gpio21_repeat_window_seconds': ('positive', None, None)},
}


def _keys(value, expected, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label}: expected an object')
    missing, unknown = set(expected) - value.keys(), value.keys() - set(expected)
    if missing or unknown:
        raise ValueError(f'{label}: missing keys {sorted(missing)}; unknown keys {sorted(unknown)}')


def validate_policy(value):
    _keys(value, {'schema_version', *RULES}, 'alarm policy')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('alarm policy: unsupported schema_version (expected 1)')
    for section, rules in RULES.items():
        _keys(value[section], rules, section)
        for key, (kind, low, high) in rules.items():
            number = value[section][key]
            try:
                finite = type(number) in (int, float) and math.isfinite(number)
            except OverflowError:
                finite = False
            if (not finite
                    or (kind == 'int' and type(number) is not int)
                    or (kind == 'positive' and number <= 0)
                    or (low is not None and number < low)
                    or (high is not None and number > high)):
                raise ValueError(f'{section}.{key}: invalid {kind} value {number!r}')
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'alarm policy: duplicate key {key!r}')
        result[key] = value
    return result


def parse_policy(text):
    return validate_policy(json.loads(text, object_pairs_hook=_unique_pairs))


def load_policy(path=None):
    selected = Path(path if path is not None else os.environ.get('LVHV_ALARM_POLICY', DEFAULT_PATH))
    try:
        return parse_policy(selected.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f'Invalid alarm policy {selected}: {exc}') from exc


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', help='Defaults to LVHV_ALARM_POLICY or checkout config/alarm-policy.json')
    args = parser.parse_args()
    try:
        load_policy(args.path)
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')
    print('Alarm policy valid')
