#!/usr/bin/env python3
"""Per-PSU ROC temperature monitoring. Power-off is opt-in; alerts are real."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import logging
import math
import os
import sys
from pathlib import Path

try:
    import lvhv_protocol as protocol
except ModuleNotFoundError as error:
    if error.name != 'lvhv_protocol':
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Client'))
    import lvhv_protocol as protocol
import signal
import socket
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOG = logging.getLogger('roc-temperature-monitor')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class LVHVClient:
    """Bounded, fresh connections using the existing LVHV binary protocol."""
    def __init__(self, commands, host='127.0.0.1', port=12000, timeout=5):
        self.host, self.port, self.timeout = host, port, timeout
        self.codes = {}
        for line in Path(commands).read_text().splitlines():
            words = line.split('//')[0].split()
            if len(words) >= 3 and words[0] == '#define':
                self.codes[words[1]] = int(words[2], 0)
        for key in ('TYPE_lv', 'COMMAND_readMonV6', 'COMMAND_powerOff'):
            if key not in self.codes:
                raise ValueError('Missing command: ' + key)

    @staticmethod
    def block(kind, values):
        return protocol.encode_block(kind, values)

    def request(self, command):
        with socket.create_connection((self.host, self.port), self.timeout) as sock:
            reply = protocol.request_reply(sock, self.codes['COMMAND_' + command],
                self.codes['TYPE_lv'], 6, timeout=self.timeout, max_blocks=8, max_elements=64)
        if len(reply) != 1:
            raise ValueError('Invalid LVHV reply header/payload')
        kind, values = reply[0]
        return kind.encode('ascii'), values

    def voltages(self):
        kind, values = self.request('readMonV6')
        # The ADC has a small signed offset around zero (observed on powered-off
        # PSU13). The server returns -1 for an ADC failure, not for negative noise.
        if kind != b'F' or len(values) != 6 or any(not finite(v) or v <= -1 for v in values):
            raise ValueError('Invalid LVHV 6 V readings (power state unknown)')
        return values

    def power_off(self):
        kind, values = self.request('powerOff')
        if kind != b'I' or values != (0,):
            raise RuntimeError('LVHV powerOff did not return success')


class TemperatureClient:
    def __init__(self, host='127.0.0.1', port=12004, timeout=30):
        self.base = f'http://{host}:{port}'
        self.timeout = timeout

    def panels(self):
        # Cached server discovery only; never initiate a UART address scan here.
        with urlopen(self.base + '/panels', timeout=min(8, self.timeout)) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get('scanned') is not True:
            raise ValueError('RS485 discovery has not completed')
        addresses = result.get('addresses')
        if (not isinstance(addresses, list) or len(addresses) > 512 or
                any(type(a) is not int or not 0 <= a <= 511 for a in addresses) or
                len(set(addresses)) != len(addresses)):
            raise ValueError('Invalid RS485 discovery addresses')
        return tuple(f'MN{a:03d}' for a in sorted(addresses))

    def read(self, panel, deadline, stop):
        # Only retry HTTP 409: the server explicitly says no UART request was sent.
        url = self.base + '/direct-read?' + urlencode({'address': int(panel[2:]), 'name': 'ROC_TEMP'})
        busy_until = min(deadline, time.monotonic() + 2)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or stop.is_set():
                raise TimeoutError('Read cycle budget exhausted')
            timeout = min(self.timeout, remaining)
            if timeout <= 0.5:
                raise TimeoutError('Read cycle budget exhausted')
            request = Request(url, headers={'X-RS485-Client': 'temperature-monitor',
                                           'X-RS485-Timeout': str(min(120, timeout - 0.5))})
            try:
                with urlopen(request, timeout=timeout) as response:
                    result = json.load(response)
                if (result.get('panel') != panel or result.get('name') != 'ROC_TEMP'
                        or result.get('source') != 'FPGA TVS' or not finite(result.get('value'))):
                    raise ValueError('Invalid direct ROC_TEMP response')
                return result['value']
            except HTTPError as exc:
                code = exc.code
                exc.close()
                if code != 409 or time.monotonic() >= busy_until:
                    raise RuntimeError(f'RS485 HTTP {code}') from None
                stop.wait(0.2)


class Pushover:
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


@dataclass
class PanelState:
    powered_since: float | None = None
    last_good: float | None = None
    high_count: int = 0
    temperature: float | None = None


class Monitor:
    def __init__(self, panels, threshold=36, count=3, missing_seconds=180, power_cutoff=2):
        self.panels = tuple(sorted(panels))
        self.threshold, self.count = threshold, count
        self.missing_seconds, self.power_cutoff = missing_seconds, power_cutoff
        self.states = {name: PanelState() for name in panels}
        self.delivered = {}  # alarm key -> recipient hashes; never persist credentials
        self.powered_since = None
        self.last_quorum = None
        self.cycle_good = set()

    def set_panels(self, panels):
        panels = tuple(sorted(panels))
        if panels != self.panels:
            LOG.info('Discovered panels updated: %s', list(panels))
        self.panels = panels
        self.states = {name: self.states.get(name, PanelState()) for name in panels}
        self.delivered = {key: recipients for key, recipients in self.delivered.items()
                          if key == 'PSU:missing' or key.rsplit(':', 1)[0] in self.states}

    def apply_power(self, volts, now):
        active = []
        powered = any(v >= self.power_cutoff for v in volts)
        if powered:
            if self.powered_since is None:
                self.powered_since = now
        else:
            self.powered_since = self.last_quorum = None
            self.cycle_good.clear()
            self.delivered.pop('PSU:missing', None)
        for name in self.panels:
            state = self.states[name]
            if powered:
                if state.powered_since is None:
                    state.powered_since = now
                active.append(name)
            else:
                self.states[name] = PanelState()
                for kind in ('hot', 'missing'):
                    self.delivered.pop(name + ':' + kind, None)
        return active

    def sample(self, name, value, now):
        state = self.states[name]
        if value is None:
            state.high_count = 0  # failed samples break consecutive-high streaks
            return
        self.cycle_good.add(name)
        state.last_good, state.temperature = now, value
        state.high_count = state.high_count + 1 if value > self.threshold else 0
        self.delivered.pop(name + ':missing', None)
        if value <= self.threshold:
            self.delivered.pop(name + ':hot', None)

    def finish_cycle(self, now):
        if len(self.cycle_good) >= 2:
            self.last_quorum = now
            self.delivered.pop('PSU:missing', None)

    def alarms(self, now):
        alarms = {}
        for name, state in self.states.items():
            if state.powered_since is None:
                continue
            if state.high_count >= self.count:
                alarms[name + ':hot'] = f'{name}: {state.temperature:.2f} C > {self.threshold:g} C for {state.high_count} consecutive readings'
        since = self.last_quorum if self.last_quorum is not None else self.powered_since
        if since is not None and now - since > self.missing_seconds:
            alarms['PSU:missing'] = (f'Fewer than 2 panels returned valid ROC_TEMP for '
                                     f'{now - since:.0f} s; latest cycle: '
                                     f'{len(self.cycle_good)}/{len(self.panels)} panels')
        # A failed sample interrupts the hot streak but does not rearm a hot
        # notification; only a cool reading or power-off does that.
        return alarms


def recipient_id(user):
    return hashlib.sha256(user.encode()).hexdigest()


def notify(monitor, alarms, notifier, label, action):
    for user in notifier.users:
        rid = recipient_id(user)
        pending = {key: text for key, text in alarms.items() if rid not in monitor.delivered.get(key, [])}
        # Group simultaneous panel failures to avoid twelve messages when a
        # whole bus goes missing. Retry only chunks/recipients that failed.
        batches = []
        batch = {}
        for key, reason in pending.items():
            if batch and len('\n'.join([*batch.values(), reason])) + len(action) + 2 > 1000:
                batches.append(batch)
                batch = {}
            batch[key] = reason
        if batch:
            batches.append(batch)
        for batch in batches:
            reason = '\n'.join(batch.values())
            try:
                notifier.send(user, f'{label}: ROC protection', f'{reason}\n{action}')
            except Exception:
                LOG.error('Pushover delivery failed for %s; retry next cycle', ', '.join(batch))
            else:
                for key in batch:
                    monitor.delivered.setdefault(key, []).append(rid)
                LOG.warning('Pushover delivered: %s; %s', reason, action)


def cycle(monitor, power, temperatures, notifier, label, stop, dry_run=True,
          budget=45, offset=0, clock=time.monotonic):
    monitor.cycle_good.clear()
    try:
        volts = power.voltages()
    except Exception as exc:
        # An unavailable LVHV server is UNKNOWN, never assumed OFF. Retain
        # missing-data timers, but suppress decisions until power is verified.
        for state in monitor.states.values():
            state.high_count = 0
        LOG.error('Cannot verify power state; monitoring unavailable: %s', exc)
        return
    try:
        monitor.set_panels(temperatures.panels())
    except Exception as exc:
        # A failed HTTP query is not an empty discovery. Keep only the last
        # successfully discovered set so server outages still age its timers.
        LOG.error('Cannot refresh discovery; retaining %d previously discovered panels: %s',
                  len(monitor.panels), exc)
    active = monitor.apply_power(volts, clock())
    LOG.info('6 V readings=%s; powered panels=%d/%d', [round(v, 3) for v in volts], len(active), len(monitor.panels))
    if monitor.powered_since is None:
        return
    if active:
        active = active[offset % len(active):] + active[:offset % len(active)]
    deadline = clock() + budget
    for name in active:
        if stop.is_set():
            return
        try:
            if clock() >= deadline:
                raise TimeoutError('Cycle budget exhausted; panel deferred')
            value = temperatures.read(name, deadline, stop)
            LOG.info('%s ROC_TEMP=%.3f C', name, value)
        except Exception as exc:
            value = None
            LOG.warning('%s ROC_TEMP failed: %s', name, exc)
        monitor.sample(name, value, clock())
    monitor.finish_cycle(clock())
    LOG.info('Temperature coverage: %d/%d panels (minimum 2)', len(monitor.cycle_good), len(monitor.panels))
    alarms = monitor.alarms(clock())
    if not alarms or stop.is_set():
        return
    # Recheck immediately before acting so a manual power-off during the read
    # cycle clears the affected alarms and suppresses notifications.
    try:
        monitor.apply_power(power.voltages(), clock())
    except Exception as exc:
        LOG.error('Cannot recheck power before alert/action: %s', exc)
        return
    alarms = monitor.alarms(clock())
    if not alarms:
        return
    action = 'DRY RUN: would turn off all local LV outputs; no power command sent.'
    if not dry_run:
        try:
            power.power_off()
            action = 'Local LV powerOff(channel 6) sent.'
            if any(v >= monitor.power_cutoff for v in power.voltages()):
                action += ' WARNING: voltage still present; will retry next cycle.'
            else:
                action += ' All six measured 6 V outputs are off.'
        except Exception as exc:
            LOG.error('Local power-off failed: %s', exc)
            action = 'Local LV power-off failed or could not be verified; will retry next cycle.'
    for key, reason in alarms.items():
        LOG.warning('ALARM %s: %s; %s', key, reason, action)
    notify(monitor, alarms, notifier, label, action)


def state_identity(args):
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    # Version separates discovery-derived state from the old configured roster.
    policy = ('discovery-two-temperature-v2', args.threshold, args.high_count,
              args.missing_seconds, args.power_cutoff)
    return boot + ':' + hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def restore(path, identity, monitor, now, dry_run=True):
    try:
        data = json.loads(path.read_text())
        if data['identity'] != identity or not 0 <= data['saved_at'] <= now:
            return
        saved = data['states']
        if not isinstance(saved, dict) or any(
                not isinstance(name, str) or len(name) != 5 or not name.startswith('MN')
                or not name[2:].isdigit() or not 0 <= int(name[2:]) <= 511 for name in saved):
            raise ValueError('Invalid saved discovery panel names')
        states = {name: PanelState(**state) for name, state in saved.items()}
        for state in states.values():
            for stamp in (state.powered_since, state.last_good):
                if stamp is not None and (not finite(stamp) or not 0 <= stamp <= now):
                    raise ValueError('Invalid saved timer')
            if type(state.high_count) is not int or state.high_count < 0:
                raise ValueError('Invalid saved streak')
            if state.temperature is not None and not finite(state.temperature):
                raise ValueError('Invalid saved temperature')
            if state.high_count and state.temperature is None:
                raise ValueError('Saved streak without temperature')
            if now - data['saved_at'] > 90:
                state.high_count = 0
        delivered = data['delivered']
        if not isinstance(delivered, dict) or any(
                not isinstance(v, list) or any(not isinstance(rid, str) or len(rid) != 64 for rid in v)
                for v in delivered.values()):
            raise ValueError('Invalid saved alert state')
        for key in ('powered_since', 'last_quorum'):
            stamp = data[key]
            if stamp is not None and (not finite(stamp) or not 0 <= stamp <= now):
                raise ValueError('Invalid saved PSU timer')
        monitor.powered_since, monitor.last_quorum = data['powered_since'], data['last_quorum']
        monitor.states, monitor.delivered = states, delivered
        # Older state was written in dry-run mode. Preserve observations across
        # a mode change, but notify again when the action changes to real off.
        if data.get('dry_run', True) != dry_run:
            monitor.delivered = {}
        monitor.set_panels(states)
    except FileNotFoundError:
        pass
    except (ValueError, KeyError, TypeError):
        LOG.error('Invalid saved state; starting new observation window')


def save(path, identity, monitor, dry_run=True):
    data = {'identity': identity, 'saved_at': time.monotonic(),
            'states': {name: asdict(state) for name, state in monitor.states.items()},
            'delivered': monitor.delivered, 'dry_run': dry_run,
            'powered_since': monitor.powered_since, 'last_quorum': monitor.last_quorum}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data))
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default='/var/lib/roc-temperature-monitor/state.json')
    parser.add_argument('--commands', default='/etc/mu2e-tracker-lvhv-tools/commands.h')
    parser.add_argument('--threshold', type=float, default=36)
    parser.add_argument('--high-count', type=int, default=3)
    parser.add_argument('--missing-seconds', type=float, default=180)
    parser.add_argument('--interval', type=float, default=60)
    parser.add_argument('--power-cutoff', type=float, default=2,
                        help='V6 below this voltage means OFF; at or above means ON')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', dest='dry_run', action='store_true', default=True,
                      help='Send real notifications, never send powerOff (default)')
    mode.add_argument('--enable-power-off', dest='dry_run', action='store_false',
                      help='Permit local LV powerOff; hardware-affecting opt-in')
    parser.add_argument('--check-config', action='store_true')
    args = parser.parse_args(argv)
    for value in (args.threshold, args.missing_seconds, args.interval, args.power_cutoff):
        if not finite(value):
            parser.error('Settings must be finite')
    if min(args.missing_seconds, args.power_cutoff) <= 0 or args.high_count < 1 or args.interval < 20:
        parser.error('Invalid timing/count/power cutoff')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    label = socket.gethostname()
    power = LVHVClient(args.commands)
    notifier = Pushover()
    if args.check_config:
        print(json.dumps({'hostname': label, 'panel_source': 'RS485 cached /panels discovery',
                          'minimum_temperature_panels': 2,
                          'dry_run': args.dry_run, 'recipients': len(notifier.users),
                          'power_cutoff': args.power_cutoff, 'power_policy': 'any V6 >= cutoff'}))
        return 0
    monitor = Monitor((), args.threshold, args.high_count, args.missing_seconds, args.power_cutoff)
    path = Path(args.state)
    identity = state_identity(args)
    restore(path, identity, monitor, time.monotonic(), args.dry_run)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    LOG.warning('Starting %s: panels=RS485 discovery only; minimum_temperature_panels=2; threshold=%g C count=%d missing>%g s interval=%g s PSU on=any V6>=%g V powerOff=%s',
                label, args.threshold, args.high_count, args.missing_seconds, args.interval, args.power_cutoff,
                'DISABLED (dry run); real alerts enabled' if args.dry_run else 'ENABLED')
    temperatures = TemperatureClient()
    offset = 0
    while not stop.is_set():
        began = time.monotonic()
        cycle(monitor, power, temperatures, notifier, label, stop, args.dry_run,
              budget=args.interval - 15, offset=offset)
        save(path, identity, monitor, args.dry_run)
        offset += 1  # fair service if an extended outage consumes the read budget
        elapsed = time.monotonic() - began
        if elapsed > args.interval:
            LOG.warning('Cycle overrun %.1f s (including alerts); no catch-up burst', elapsed)
        stop.wait(max(1, args.interval - elapsed))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
