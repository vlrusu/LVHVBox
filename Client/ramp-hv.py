#!/usr/bin/env python3
# Ed Callaghan
# Test abstracted hv up/down routine
# March 2025

import argparse
import atexit
import fcntl
import json
import os.path
import re
import select
import socket
import subprocess
import time
from PowerSupplyServerConnection import PowerSupplyServerConnection
import threading

TUNNEL_PROCESSES = []
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROL_CENTER_DIR = os.path.abspath(
    os.path.join(SCRIPT_DIR, '..', '..', 'mu2e-tracker-lvhv-control-center')
)
TRACKER_SLOT_TO_PSU = {
    0: 0,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 11,
    10: 14,
    11: 13,
    12: 15,
    13: 9,
    14: 10,
    15: 12,
    16: 17,
    17: 16,
}

def cleanup_tunnels():
    processes = list(TUNNEL_PROCESSES)
    TUNNEL_PROCESSES.clear()
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

atexit.register(cleanup_tunnels)

def set_voltage(supply, channel, voltage):
    tripped = supply.QueryTripStatus(channel)
    if tripped:
        if voltage <= 0:
            print('Channel %d is tripped; setting DAC to 0' % channel)
            supply._set_hv_by_dac(channel, 0)
            return
        print('Skipping channel %d: trip status is set' % channel)
        return
    supply.SetWireVoltage(channel, voltage)

def request_ramp_stop(active_supplies):
    for supply,channel in active_supplies:
        try:
            supply.SetHVLock(channel, True)
        except Exception as e:
            print('warning: failed to set HV lock for channel %d: %s' % (
                channel, str(e)
            ))

def close_supplies(active_supplies):
    seen = set()
    for supply,channel in active_supplies:
        if id(supply) in seen:
            continue
        seen.add(id(supply))
        try:
            supply.close()
        except Exception as e:
            print('warning: failed to close supply for channel %d: %s' % (
                channel, str(e)
            ))

def join_threads(threads, timeout):
    deadline = time.time() + timeout
    while 0 < len(threads):
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        for thread in list(threads):
            thread.join(timeout=min(0.1, remaining))
            if not thread.is_alive():
                threads.remove(thread)
    return threads

def strip_json_comments(text):
    rv = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ''

        if in_string:
            rv.append(c)
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
        elif c == '"':
            in_string = True
            rv.append(c)
            i += 1
        elif c == '#':
            while i < len(text) and text[i] != '\n':
                i += 1
        elif c == '/' and n == '/':
            i += 2
            while i < len(text) and text[i] != '\n':
                i += 1
        elif c == '/' and n == '*':
            i += 2
            while i + 1 < len(text) and not (text[i] == '*' and text[i + 1] == '/'):
                i += 1
            i += 2
        else:
            rv.append(c)
            i += 1

    return ''.join(rv)

def merge_json_value(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        rv = dict(a)
        for key,value in b.items():
            if key in rv:
                rv[key] = merge_json_value(rv[key], value)
            else:
                rv[key] = value
        return rv
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    return b

def additive_json_object(pairs):
    rv = {}
    for key,value in pairs:
        if key in rv:
            rv[key] = merge_json_value(rv[key], value)
        else:
            rv[key] = value
    return rv

def load_json_with_comments(path):
    with open(path, 'r') as f:
        text = f.read()
    return json.loads(strip_json_comments(text),
                      object_pairs_hook=additive_json_object)

def load_hv_defaults(path):
    if path is None or not os.path.exists(path):
        return {}
    return load_json_with_comments(path)

def load_config(path):
    if path is None or not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)

def hv_channels_from(value):
    rv = set()
    if value is None:
        return rv
    if isinstance(value, int):
        value = [value]
    for channel in value:
        try:
            channel = int(channel)
        except Exception:
            continue
        if 0 <= channel < 12:
            rv.add(channel)
    return rv

def psu_host_key(host):
    match = re.search(r'(psu\d+)', host)
    if match:
        return match.group(1)
    return host

class RampLock:
    def __init__(self, file=None, process=None):
        self.file = file
        self.process = process

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None
        if self.process is not None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait()
            self.process = None

def acquire_local_ramp_lock():
    lock = open('/tmp/ramp-hv.lock', 'a+')
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    lock.seek(0)
    lock.truncate()
    lock.write('%d\n' % os.getpid())
    lock.flush()
    return RampLock(file=lock)

def acquire_remote_ramp_lock(host, args):
    ssh_cmd = [
        'ssh',
        '-T',
        '-o',
        'ConnectTimeout=%d' % args.ssh_connect_timeout,
        '-o',
        'ConnectionAttempts=1',
        '%s@%s' % (args.user, normalize_host(host)),
        '-J',
        args.gateway,
        "flock -n /tmp/ramp-hv.lock sh -c 'echo LOCKED; cat >/dev/null'",
    ]
    if args.ssh_batch_mode:
        ssh_cmd[1:1] = ['-o', 'BatchMode=yes']

    process = subprocess.Popen(ssh_cmd, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    ready, _, _ = select.select([process.stdout], [], [],
                                args.ssh_connect_timeout + 2.0)
    if ready and process.stdout.readline().strip() == 'LOCKED':
        return RampLock(process=process)

    if process.poll() is None:
        process.terminate()
    return_code = process.wait()
    if return_code == 1:
        return None
    raise RuntimeError('Failed to acquire ramp lock on %s (ssh exit %d)' % (
        host, return_code
    ))

def acquire_ramp_lock(host, args):
    """Acquire the lock on the PSU so clients on all machines share it."""
    if normalize_host(host) in ('localhost', '127.0.0.1'):
        return acquire_local_ramp_lock()
    return acquire_remote_ramp_lock(host, args)

def subconfig_for_host(host, config):
    key = psu_host_key(host)
    for subconfig in config.get('connections', []):
        if subconfig.get('host') == key:
            return subconfig
    return {'host': key}

def hv_off_channels(subconfig, defaults):
    off = set()
    off |= hv_channels_from(defaults.get('off'))
    off |= hv_channels_from(defaults.get('hosts', {}).get(subconfig.get('host')))
    if 'station' in subconfig:
        off |= hv_channels_from(defaults.get('stations', {}).get(str(subconfig['station'])))
    if 'slot' in subconfig:
        off |= hv_channels_from(defaults.get('slots', {}).get(str(subconfig['slot'])))
    return off

def filtered_channels(channels, subconfig, defaults, ignore_defaults):
    if ignore_defaults:
        return channels
    off = hv_off_channels(subconfig, defaults)
    kept = []
    for channel in channels:
        if channel in off:
            print('Skipping channel %d on %s: listed in HV off defaults' % (
                channel, subconfig.get('host', 'unknown host')
            ))
        else:
            kept.append(channel)
    return kept

def print_masked_channels(subconfig, defaults, ignore_defaults):
    off = sorted(hv_off_channels(subconfig, defaults))
    host = subconfig.get('host', 'unknown host')
    if ignore_defaults:
        print('HV off defaults ignored for %s; masked channels would be: %s' % (
            host, ', '.join(str(channel) for channel in off) if off else 'none'
        ))
    else:
        print('HV off defaults for %s mask channels: %s' % (
            host, ', '.join(str(channel) for channel in off) if off else 'none'
        ))

def slot_to_psu(slot):
    try:
        return 'psu%d' % TRACKER_SLOT_TO_PSU[slot]
    except KeyError:
        raise ValueError('slot%d is not in the cached tracker slot mapping (known slots: 0-17)' % slot)

def expand_host_token(token):
    match = re.fullmatch(r'slot(\d+)', token)
    if match:
        return slot_to_psu(int(match.group(1)))
    return token

def normalize_host(hostname):
    if hostname in ('localhost', '127.0.0.1'):
        return hostname
    if '.' in hostname:
        return hostname
    return 'mu2e-trk-%s.fnal.gov' % hostname

def local_port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False

def find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

def ensure_tunnel(host, args):
    local_port = args.local_port
    if local_port_open(local_port):
        local_port = find_free_port()
        print('Local port in use, using %d instead' % local_port)

    ssh_cmd = [
        'ssh',
        '-KX',
        '-N',
        '-o',
        'ExitOnForwardFailure=yes',
        '-o',
        'ConnectTimeout=%d' % args.ssh_connect_timeout,
        '-o',
        'ConnectionAttempts=1',
        '-L',
        '%d:localhost:%d' % (local_port, args.port),
        '%s@%s' % (args.user, host),
        '-J',
        args.gateway,
    ]
    if args.ssh_batch_mode:
        ssh_cmd[1:1] = ['-o', 'BatchMode=yes']

    process = subprocess.Popen(ssh_cmd)
    TUNNEL_PROCESSES.append(process)
    for i in range(75):
        if process.poll() is not None:
            TUNNEL_PROCESSES.remove(process)
            raise RuntimeError('Failed to establish SSH tunnel')
        if local_port_open(local_port):
            return local_port
        time.sleep(0.2)

    cleanup_tunnels()
    raise RuntimeError('SSH tunnel did not become ready')

def connection_target(args):
    if args.psu is not None:
        host = 'psu%d' % args.psu
    elif args.target_host is not None:
        host = expand_host_token(args.target_host)
    else:
        host = args.host

    host = normalize_host(host)
    if host in ('localhost', '127.0.0.1'):
        return host, args.port

    port = ensure_tunnel(host, args)
    return '127.0.0.1', port

def selected_host(args):
    if args.psu is not None:
        return 'psu%d' % args.psu
    if args.target_host is not None:
        return expand_host_token(args.target_host)
    return args.host

def main(args):
    if len(args.channels) < 1:
        raise Exception('supply channels (-c)')

    config = load_config(args.config)
    defaults = load_hv_defaults(args.hv_defaults)
    subconfig = subconfig_for_host(selected_host(args), config)
    print_masked_channels(subconfig, defaults, args.ignore_hv_off_defaults)
    channels = filtered_channels(args.channels, subconfig, defaults,
                                 args.ignore_hv_off_defaults)
    if len(channels) < 1:
        print('No channels left to ramp after applying HV off defaults')
        return

    target_host = selected_host(args)
    psu_label = psu_host_key(target_host)
    ramp_lock = acquire_ramp_lock(target_host, args)
    if ramp_lock is None:
        print('A ramp-hv process is already running on %s; not starting another' % psu_label)
        return 1

    threads = []
    active_supplies = []
    try:
        connection_host, connection_port = connection_target(args)
        for channel in channels:
            supply = PowerSupplyServerConnection(connection_host, connection_port, args.header,
                                                 psu_label=psu_label)
            active_supplies.append((supply, channel))
            thread = threading.Thread(name='Channel %d' % channel,
                                      daemon=True,
                                      target=set_voltage,
                                      args=(supply,channel,args.voltage),
                                     )
            threads.append(thread)

        for thread in threads:
            thread.start()

        while 0 < len(threads):
            for thread in list(threads):
                thread.join(timeout=0.1)
                if not thread.is_alive():
                    threads.remove(thread)
    except KeyboardInterrupt:
        print('Ctrl-C received; stopping active ramps')
        request_ramp_stop(active_supplies)
        threads = join_threads(threads, 5.0)
        if 0 < len(threads):
            print('warning: %d ramp thread(s) did not stop before connection close' % len(threads))
        raise
    finally:
        close_supplies(active_supplies)
        threads = join_threads(threads, 1.0)
        if 0 < len(threads):
            print('warning: %d ramp thread(s) still alive after cleanup' % len(threads))
        ramp_lock.close()

    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target_host', nargs='?',
                        help='Optional host token like psu16, slot12, localhost, or a full hostname')
    parser.add_argument('-c', type=int, dest='channels', nargs='+', default=[])
    parser.add_argument('-v', type=float, dest='voltage', default=0.0)
    parser.add_argument('--host', type=str, dest='host', default='localhost')
    parser.add_argument('--psu', type=int, dest='psu',
                        help='PSU number, e.g. --psu 16 connects to psu16')
    parser.add_argument('--port', type=int, dest='port', default=12000)
    parser.add_argument('--local-port', type=int, dest='local_port', default=12000,
                        help='Local port to forward to the remote LV/HV server')
    parser.add_argument('--user', default='mu2e',
                        help='SSH username for the remote host')
    parser.add_argument('--gateway', default='mu2egateway01.fnal.gov',
                        help='SSH jump host')
    parser.add_argument('--ssh-connect-timeout', type=int, default=10,
                        help='Seconds to wait for each SSH TCP connection attempt')
    parser.add_argument('--ssh-batch-mode', action='store_true',
                        help='Disable interactive SSH auth prompts during tunnel setup')
    parser.add_argument('--config', type=str, dest='config', required=True,
                        help='Control-center config used to map host to slot/station')
    parser.add_argument('--hv-off-defaults', type=str, dest='hv_defaults',
                        required=True,
                        help='JSON file of HV channels to skip by default')
    parser.add_argument('--ignore-hv-off-defaults', action='store_true',
                        help='Ramp requested channels even if listed in HV off defaults')
    parser.add_argument('--header', type=str, dest='header', default='/etc/mu2e-tracker-lvhv-tools/commands.h')

    args = parser.parse_args()
    try:
        raise SystemExit(main(args))
    except KeyboardInterrupt:
        raise SystemExit(130)
    finally:
        cleanup_tunnels()
