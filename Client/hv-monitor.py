# Ed Callaghan
# Realtime plots of hv currents and voltages
# September, November 2024

import argparse
from collections import deque
import datetime
from functools import partial
import json
from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np
import os.path
import re
import socket
import subprocess
import threading
from time import sleep

from PowerSupplyServerConnection import PowerSupplyServerConnection
from ThreadSafeDict import ThreadSafeDict

def now():
    rv = datetime.datetime.now()
    return rv


def normalize_host(hostname):
    if hostname in ("localhost", "127.0.0.1"):
        return hostname
    if "." in hostname:
        return hostname
    return f"mu2e-trk-{hostname}.fnal.gov"


def local_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def ensure_tunnel(host, user, gateway, local_port, remote_port):
    if local_port_open(local_port):
        local_port = find_free_port()
        print(f"Local port in use, using {local_port} instead")
    ssh_cmd = [
        "ssh",
        "-f",
        "-KX",
        "-N",
        "-L",
        f"{local_port}:localhost:{remote_port}",
        f"{user}@{host}",
        "-J",
        gateway,
    ]
    result = subprocess.run(ssh_cmd)
    if result.returncode != 0:
        raise RuntimeError("Failed to establish SSH tunnel")
    for _ in range(10):
        if local_port_open(local_port):
            return local_port
        sleep(0.2)
    raise RuntimeError("SSH tunnel did not become ready")

class ClockedBuffer(deque):
    def __init__(self, expiration):
        self.expiration = expiration

    def Consume(self, item):
        wrapped = (item, now())
        self.append(wrapped)
        self.Resolve()

    def Resolve(self):
        rn = now()
        while 0 < len(self) and (self.expiration < (rn - self[0][1])):
            self.popleft()

class MonitorSupply:
    def __init__(self, spec, header):
        self.spec = spec
        self.connection = PowerSupplyServerConnection(
            spec['connection_host'], spec['connection_port'], header
        )
        self.lock = threading.Lock()

    def close(self):
        self.connection.close()

    def query_values(self, cmd):
        with self.lock:
            if cmd == 'get_vhv':
                return self.connection.QueryWireVoltages()
            if cmd == 'get_ihv':
                return self.connection.QueryWireCurrents()
            raise ValueError('unsupported monitor command: %s' % cmd)


def query_supply_and_set(supply, cmd, targets, out):
    values = supply.query_values(cmd)
    for target in targets:
        channel = target['channel']
        if channel < len(values):
            out.Assign(target['label'], values[channel])


def threaded_queries(supplies, cmd, targets_by_display, out):
    threads = []
    for display,supply in supplies.items():
        thread = threading.Thread(name=display,
                                  daemon=True,
                                  target=query_supply_and_set,
                                  args=(supply, cmd, targets_by_display[display], out))
        threads.append(thread)

    for thread in threads:
        thread.start()

    while 0 < len(threads):
        for thread in threads:
            thread.join(timeout=1e-6)
            if not thread.is_alive():
                threads.remove(thread)


def subplot_grid(count):
    return count, 1


def timeseries(supplies, targets, targets_by_display, cmd, label, xlim, ylim, yscale, logger, machine_name, value_decimals):
    expire = xlim[1]
    buff = ClockedBuffer(expiration=datetime.timedelta(seconds=expire))

    hosts = []
    for target in targets:
        if target['display'] not in hosts:
            hosts.append(target['display'])

    nrows, ncols = subplot_grid(len(hosts))
    fig_height = max(4.0, min(30.0, 1.7 * len(hosts)))
    fig, axes_grid = plt.subplots(
        nrows,
        ncols,
        squeeze=False,
        sharex=True,
        sharey=True,
        figsize=(10.0, fig_height),
    )
    if fig.canvas.manager is not None:
        fig.canvas.manager.set_window_title(f'hv-monitor - {machine_name}')

    axes = {}
    flat_axes = list(axes_grid.flat)
    for index, (host, ax) in enumerate(zip(hosts, flat_axes)):
        axes[host] = ax
        ax.text(
            0.01,
            0.96,
            host,
            transform=ax.transAxes,
            ha='left',
            va='top',
            fontsize='small',
            bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='0.8', alpha=0.75),
        )
        ax.set_xlabel('Time ago [s]' if index == len(hosts) - 1 else '')
        ax.set_ylabel(label if index == 0 else '')
    for ax in flat_axes[len(hosts):]:
        ax.set_visible(False)

    lines = {}
    line_labels = {}
    line_keys = {}
    for target in targets:
        target_label = target['label']
        channel_label = str(target['channel'])
        line_labels[target_label] = channel_label
        lines[target_label], *rest = axes[target['display']].plot(
            [], [], '-', label=channel_label, picker=5
        )
        line_keys[lines[target_label]] = target_label

    legends = {}
    legend_ncols = min(6, max(1, len({target['channel'] for target in targets})))

    def make_legend(ax):
        return ax.legend(
            ncols=legend_ncols,
            loc='upper right',
            fontsize='xx-small',
            framealpha=0.75,
            borderpad=0.2,
            labelspacing=0.2,
            handlelength=1.0,
            handletextpad=0.3,
            columnspacing=0.6,
        )

    annotations = {}
    for host, ax in axes.items():
        annotations[ax] = ax.annotate(
            '',
            xy=(0, 0),
            xytext=(12, 12),
            textcoords='offset points',
            bbox=dict(boxstyle='round', fc='white', ec='0.5', alpha=0.9),
            arrowprops=dict(arrowstyle='->'),
        )
        annotations[ax].set_visible(False)

    def hide_annotations():
        changed = False
        for annotation in annotations.values():
            if annotation.get_visible():
                annotation.set_visible(False)
                changed = True
        return changed

    def on_hover(event):
        if event.inaxes not in axes.values():
            if hide_annotations():
                fig.canvas.draw_idle()
            return

        for line, target_label in line_keys.items():
            if line.axes is not event.inaxes:
                continue
            contains, details = line.contains(event)
            if not contains:
                continue

            indices = details.get('ind', [])
            if len(indices) == 0:
                continue

            index = indices[0]
            xdata = line.get_xdata()
            ydata = line.get_ydata()
            if len(xdata) <= index or len(ydata) <= index:
                continue

            annotation = annotations[line.axes]
            annotation.xy = (xdata[index], ydata[index])
            annotation.set_text(
                f"{line_labels[target_label]}/{ydata[index]:.{value_decimals}f}\n"
                f"{xdata[index]:.1f}s ago"
            )
            hide_annotations()
            annotation.set_visible(True)
            fig.canvas.draw_idle()
            return

        if hide_annotations():
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect('motion_notify_event', on_hover)

    def init():
        nonlocal legends
        for host, ax in axes.items():
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            ax.set_yscale(yscale)
            legends[host] = make_legend(ax)
            ax.invert_xaxis()
        fig.subplots_adjust(hspace=0.0, top=0.99, bottom=0.06, left=0.08, right=0.99)
        return list(lines.values())

    def update(frame, lines, buff):
        nonlocal legends
        buff.Consume(frame)
        rn = now()
        latest_values = {}
        for k in lines.keys():
            pairs = [pair for pair in buff if k in pair[0]]
            if 0 < len(pairs):
                xx = [(rn - pair[1]).total_seconds() for pair in pairs]
                yy = [pair[0][k] for pair in pairs]
                lines[k].set_data(xx, yy)
                if 0 < len(yy):
                    latest_values[k] = yy[-1]

        for k in lines.keys():
            if k in latest_values:
                lines[k].set_label(f'{line_labels[k]}/{latest_values[k]:.{value_decimals}f}')
            else:
                lines[k].set_label(line_labels[k])

        for host, legend in legends.items():
            if legend is not None:
                legend.remove()
            legends[host] = make_legend(axes[host])
        return lines.values()

    def queries(cmd):
        while True:
            sleep(0.01)
            rv = ThreadSafeDict()
            threaded_queries(supplies, cmd, targets_by_display, rv)
            rv = rv.AsDict()
            logger(rv)
            yield rv

    animation = FuncAnimation(fig, partial(update, lines=lines, buff=buff),
                              frames=queries(cmd),
                              init_func=init,
                              repeat=False,
                              interval=0,
                              blit=False)
    return animation


def make_logger(logfile_path, targets, cmd_label):
    if logfile_path is None:
        return lambda *_: None  # no-op
    f = open(logfile_path, 'w')
    labels = [target['label'] for target in targets]
    header = 'timestamp,' + ','.join(f'{cmd_label}_{label}' for label in labels)
    print(header, file=f)

    def logger(measurements):
        ts = now().isoformat()
        line = ts + ',' + ','.join(f"{measurements.get(label, ''):.3f}" if label in measurements else '' for label in labels)
#        line = ts + ',' + ','.join(str(measurements.get(label, '')) for label in labels)
        print(line, file=f, flush=True)

    return logger


def display_host(host):
    short = host.split('.')[0]
    if short.startswith('mu2e-trk-'):
        return short[len('mu2e-trk-'):]
    return short


def expand_host_token(token):
    match = re.fullmatch(r'([A-Za-z_-]+)(\d+)-(\d+)', token)
    if match is None:
        return [token]

    prefix = match.group(1)
    start = int(match.group(2))
    stop = int(match.group(3))
    step = 1 if start <= stop else -1
    return [f'{prefix}{index}' for index in range(start, stop + step, step)]


def expand_hosts(hosts):
    expanded = []
    for host in hosts:
        expanded.extend(expand_host_token(host))
    return expanded


def make_connection_specs(hosts, args):
    specs = []
    for raw_host in expand_hosts(hosts):
        host = normalize_host(raw_host)
        if host in ("localhost", "127.0.0.1"):
            connection_host = host
            connection_port = args.remote_port
        else:
            connection_host = "127.0.0.1"
            connection_port = ensure_tunnel(
                host, args.user, args.gateway, args.local_port, args.remote_port
            )
        specs.append({
            'raw_host': raw_host,
            'host': host,
            'display': display_host(raw_host),
            'connection_host': connection_host,
            'connection_port': connection_port,
        })
    return specs


def make_targets(connection_specs, channels):
    targets = []
    include_host = 1 < len(connection_specs)
    for spec in connection_specs:
        for channel in channels:
            channel_label = f'ch{channel}'
            label = f"{spec['display']}_{channel_label}" if include_host else channel_label
            targets.append({
                **spec,
                'channel': channel,
                'label': label,
            })
    return targets


def group_targets_by_display(targets):
    rv = {}
    for target in targets:
        rv.setdefault(target['display'], []).append(target)
    return rv


def make_supplies(connection_specs, header):
    return {
        spec['display']: MonitorSupply(spec, header)
        for spec in connection_specs
    }


def close_supplies(supplies):
    for supply in supplies.values():
        try:
            supply.close()
        except Exception as e:
            print('warning: failed to close monitor supply: %s' % str(e))


def main(args):
    header = args.header
    if header is None:
        this = os.path.abspath(__file__)
        this = os.path.dirname(this)
        this = os.path.dirname(this)
        header = os.path.join(this, 'commands.h')

    channels = args.channels
    connection_specs = make_connection_specs(args.hosts, args)
    targets = make_targets(connection_specs, channels)
    targets_by_display = group_targets_by_display(targets)
    supplies = make_supplies(connection_specs, header)
    machine_name = ', '.join(spec['display'] for spec in connection_specs)
    print(f"Monitoring PSUs: {machine_name}")
    print(f"Monitoring channels: {', '.join(str(ch) for ch in channels)}")
    print(f"Opened {len(supplies)} LV/HV connection(s)")

    if args.logfile is None:
        log_prefix = None  # No logging
    elif args.logfile == '':
        log_prefix = now().strftime('hvlog_%Y%m%d_%H%M%S')  # Timestamp-based name
    else:
        log_prefix = args.logfile  # Use the provided name
    
    log_prefix = args.logfile or now().strftime('hvlog_%Y%m%d_%H%M%S')
    voltage_log = f'{log_prefix}_voltage.csv'
    current_log = f'{log_prefix}_current.csv'

    volt_logger = make_logger(f'{log_prefix}_voltage.csv' if log_prefix else None, targets, 'voltage')
    curr_logger = make_logger(f'{log_prefix}_current.csv' if log_prefix else None, targets, 'current')

    try:
        if args.no_plots:
            # If no plots, just run the loggers in background forever
            def run_query_loop(cmd, logger):
                while True:
                    rv = ThreadSafeDict()
                    threaded_queries(supplies, cmd, targets_by_display, rv)
                    logger(rv.AsDict())
                    sleep(0.1)

            t1 = threading.Thread(target=run_query_loop, args=('get_vhv', volt_logger), daemon=True)
            t2 = threading.Thread(target=run_query_loop, args=('get_ihv', curr_logger), daemon=True)
            t1.start()
            t2.start()
            try:
                while True:
                    sleep(1)
            except KeyboardInterrupt:
                print("Logging interrupted.")
        else:
            voltages = timeseries(supplies, targets, targets_by_display,
                                  'get_vhv', 'Voltage [V]',
                                  (0.0, 300.0), (0.0, 1900.0),
                                  'linear',
                                  volt_logger,
                                  machine_name,
                                  0,
                                 )
            currents = timeseries(supplies, targets, targets_by_display,
                                  'get_ihv', 'Current [uA]',
                                  (0.0, 300.0), (0.0, 30.0),
                                  'linear',
                                  curr_logger,
                                  machine_name,
                                  1,
                                 )
            #pcbtemp = timeseries(mksupplies(channels), channels,
            #                      'pcb_temp', 'PCB Temperature [degC]',
            #                      (0.0, 300.0), (25.0, 35.0),
            #                      'linear',
            #                      lambda *args: None,
            #                     )
            plt.show()
    finally:
        close_supplies(supplies)

    
 

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c',
        type=int,
        dest='channels',
        nargs='+',
        default=list(range(12)),
        help='HV channels to monitor; defaults to all 12 channels',
    )
    parser.add_argument(
        'hosts',
        nargs='*',
        default=['localhost'],
        help='Hostnames like psu13 psu14, psu0-17, or fully-qualified mu2e-trk-psu13.fnal.gov',
    )
    parser.add_argument('--user', default='mu2e', help='SSH username for the remote host')
    parser.add_argument('--gateway', default='mu2egateway01.fnal.gov', help='SSH jump host')
    parser.add_argument('--local-port', type=int, default=12000, help='Local port to forward to the remote server')
    parser.add_argument('--remote-port', type=int, default=12000, help='Remote server port to forward')
    parser.add_argument('--header', type=str, dest='header', default=None)
    parser.add_argument('--no-plots', action='store_true', help='Disable real-time plotting')
    parser.add_argument('--logfile', nargs='?', const='', default=None)
    
    args = parser.parse_args()
    main(args)
