"""Persist completed RS485 discovery and deliver notification-only startup and power-on changes."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

try:
    import lvhv_protocol as protocol
except ModuleNotFoundError as error:
    if error.name != 'lvhv_protocol':
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
    import lvhv_protocol as protocol

LOG = logging.getLogger('rs485-discovery')

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

class PowerReader:
    """Bounded, fresh connections using the existing LVHV binary protocol."""
    def __init__(self, commands, host='127.0.0.1', port=12000, timeout=5):
        self.host, self.port, self.timeout = host, port, timeout
        self.codes = {}
        for line in Path(commands).read_text().splitlines():
            words = line.split('//')[0].split()
            if len(words) >= 3 and words[0] == '#define':
                self.codes[words[1]] = int(words[2], 0)
        for key in ('TYPE_lv', 'COMMAND_readMonV6'):
            if key not in self.codes:
                raise ValueError('Missing command: ' + key)

    def request(self):
        # Channel 6 means all six LV outputs in the existing protocol.
        deadline = time.monotonic() + self.timeout
        with socket.create_connection((self.host, self.port), self.timeout) as sock:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('LVHV response deadline exceeded')
            try:
                result = protocol.request_reply(
                    sock, self.codes['COMMAND_readMonV6'], self.codes['TYPE_lv'], 6,
                    timeout=remaining, max_blocks=8, max_elements=64,
                )
            except EOFError as exc:
                # Existing discovery callers treat OSError/ConnectionError as
                # unknown power and preserve their last successful inventory.
                raise ConnectionError('LVHV closed connection') from exc
            if len(result) != 1:
                raise ValueError('Invalid LVHV reply header/payload')
            kind, values = result[0]
            return kind.encode('ascii'), values

    def voltages(self):
        kind, values = self.request()
        # The ADC has a small signed offset around zero (observed on powered-off
        # PSU13). The server returns -1 for an ADC failure, not for negative noise.
        if kind != b'F' or len(values) != 6 or any(not finite(v) or v <= -1 for v in values):
            raise ValueError('Invalid LVHV 6 V readings (power state unknown)')
        return values


class DiscoveryNotifier:
    def __init__(self):
        # Compatible with the existing PSU13 alert service's environment file.
        self.token = os.getenv('ROC_MONITOR_PUSHOVER_API_TOKEN') or os.getenv('I2C_SENSOR_ALERTS_PUSHOVER_API_TOKEN', '')
        keys = os.getenv('ROC_MONITOR_PUSHOVER_USER_KEY') or os.getenv('I2C_SENSOR_ALERTS_PUSHOVER_USER_KEY', '')
        self.users = list(dict.fromkeys(key.strip() for key in keys.split(',') if key.strip()))
        if not self.token or not self.users:
            raise ValueError('Pushover credentials are required; configure the protected environment file')

    def send(self, recipient, title, message):
        body = urlencode({'token': self.token, 'user': recipient, 'title': title,
                          'message': message, 'priority': 1}).encode()
        request = Request('https://api.pushover.net/1/messages.json', data=body)
        # Never log exception text or response bodies from the credential-bearing request.
        try:
            with urlopen(request, timeout=10) as response:
                result = json.load(response)
            if result.get('status') != 1:
                raise RuntimeError('Pushover rejected notification')
        except Exception:
            raise RuntimeError('Pushover delivery failed (details suppressed to protect credentials)') from None


class DiscoveryHistory:
    def __init__(self, path, hostname=None):
        self.path = Path(path)
        self.hostname = hostname or socket.gethostname()
        self.lock = threading.RLock()
        self.data = {'version': 1, 'last_discovered': [], 'last_scan': None, 'pending': []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if not isinstance(self.data, dict) or self.data.get('version') != 1:
                raise ValueError('Unsupported discovery history')
            self.addresses(self.data['last_discovered'])
            if not isinstance(self.data.get('pending'), list):
                raise ValueError('Invalid discovery notification queue')
            for event in self.data['pending']:
                self.addresses(event['missing'])
                if (not isinstance(event['id'], str) or not isinstance(event['delivered'], list)
                        or any(not isinstance(x, str) or len(x) != 64 for x in event['delivered'])):
                    raise ValueError('Invalid saved notification')

    @staticmethod
    def addresses(values):
        if (not isinstance(values, list) or len(values) > 512 or
                any(type(a) is not int or not 0 <= a <= 511 for a in values) or
                len(set(values)) != len(values)):
            raise ValueError('Invalid discovery addresses')
        return sorted(values)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data))
        temporary.replace(self.path)

    def record(self, inventory, powered, *, startup=False, power_on=False):
        if inventory.get('scanned') is not True:
            raise ValueError('Cannot persist an incomplete discovery')
        found = self.addresses(inventory['addresses'])
        start, end = inventory['start'], inventory['end']
        if (type(start) is not int or type(end) is not int or not 0 <= start <= end <= 511
                or any(not start <= a <= end for a in found)):
            raise ValueError('Invalid discovery range')
        with self.lock:
            previous = self.data['last_discovered']
            missing = sorted(a for a in previous if start <= a <= end and a not in found)
            stamp = inventory.get('timestamp_utc') or datetime.now(timezone.utc).isoformat()
            # OFF/unknown scans must not erase a known list or generate nuisance
            # warnings. Powered scans only add to the expected inventory.
            if powered is True:
                self.data['last_discovered'] = sorted(set(previous) | set(found))
                if startup or power_on:
                    for offset in range(0, len(missing), 100):
                        self.data['pending'].append({'id': uuid4().hex, 'timestamp_utc': stamp,
                                                     'missing': missing[offset:offset+100], 'delivered': [],
                                                     'reason': 'power-on' if power_on else 'startup'})
            self.data['last_scan'] = {'timestamp_utc': stamp, 'startup': startup,
                                      'power_on': power_on, 'powered': powered, 'addresses': found, 'missing': missing}
            self._save()
            return self.status()

    def status(self):
        with self.lock:
            return copy.deepcopy({'last_discovered': self.data['last_discovered'],
                                  'last_scan': self.data['last_scan'],
                                  'pending_notifications': len(self.data['pending'])})

    def deliver(self, notifier, power_reader=None):
        with self.lock:
            pending = copy.deepcopy(self.data['pending'])
        for event in pending:
            reason = 'power-on' if event.get('reason') == 'power-on' else 'startup'
            panels = ', '.join(f'MN{a:03d}' for a in event['missing'])
            for user in notifier.users:
                rid = hashlib.sha256(user.encode()).hexdigest()
                if rid in event['delivered']:
                    continue
                if power_reader is not None and not any(v >= 2 for v in power_reader.voltages()):
                    return  # retain pending warning until PSU power is verified ON
                try:
                    notifier.send(user, f'{self.hostname}: RS485 {reason} discovery',
                                  f'Expected panels missing at {reason}: {panels}.\n'
                                  f"Scan: {event['timestamp_utc']}\n"
                                  'Notification only: this discovery warning never requests power-off.')
                except Exception:
                    LOG.error('Discovery notification failed; retry pending recipient')
                    continue
                with self.lock:
                    current = next((x for x in self.data['pending'] if x['id'] == event['id']), None)
                    if current is not None and rid not in current['delivered']:
                        current['delivered'].append(rid)
                        self._save()
                LOG.warning('Discovery notification delivered: %s (notification only)', panels)
            wanted = {hashlib.sha256(user.encode()).hexdigest() for user in notifier.users}
            with self.lock:
                self.data['pending'] = [x for x in self.data['pending']
                                       if x['id'] != event['id'] or not wanted.issubset(x['delivered'])]
                self._save()

    def notification_loop(self, notifier, stop, power_reader):
        while not stop.is_set():
            try:
                if power_reader is not None and self.status()['pending_notifications']:
                    self.deliver(notifier, power_reader)
            except Exception:
                LOG.error('Discovery notification failed; will retry (credential details suppressed)')
            stop.wait(30)
