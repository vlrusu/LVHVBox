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

def query_and_set(supply, cmd, channel, out):
    rv = supply.WriteRead(cmd, channel)
    rv = rv[0][0]
    out.Assign(channel, rv)

def threaded_queries(supplies, cmd, channels, out):
    threads = []
    for supply,channel in zip(supplies,channels):
        thread = threading.Thread(name='Channel %d' % channel,
                                  daemon=True,
                                  target=query_and_set,
                                  args=(supply,cmd,channel,out))
        threads.append(thread)

    for thread in threads:
        thread.start()

    while 0 < len(threads):
        for thread in threads:
            thread.join(timeout=1e-6)
            if not thread.is_alive():
                threads.remove(thread)

def timeseries(supplies, channels, cmd, label, xlim, ylim, yscale, logger, machine_name):
    expire = xlim[1]
    buff = ClockedBuffer(expiration=datetime.timedelta(seconds=expire))

    fig = plt.figure()
    fig.suptitle(f'{label} - {machine_name}')
    if fig.canvas.manager is not None:
        fig.canvas.manager.set_window_title(f'hv-monitor - {machine_name}')
    plt.xlabel('Time ago [s]')
    plt.ylabel(label)
    ax = plt.gca()
    lines = {}
    for channel in channels:
        label = 'Channel %d' % channel
        lines[channel], *rest = ax.plot([], [], '-', label=label)

    legend = None

    def init():
        nonlocal legend
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_yscale(yscale)
        legend = ax.legend(ncols=3)
        ax.invert_xaxis()
        return list(lines.values())

    def update(frame, lines, buff):
        nonlocal legend
        buff.Consume(frame)
        rn = now()
        latest_values = {}
        for k in lines.keys():
            # TODO this loop structure assumes the timeseries are aligned
            # which is not guaranteed
            if k in buff[0][0].keys():
                xx = [(rn - pair[1]).total_seconds() for pair in buff]
                yy = [pair[0][k] for pair in buff]
                lines[k].set_data(xx, yy)
                if 0 < len(yy):
                    latest_values[k] = yy[-1]

        for k in channels:
            if k in latest_values:
                lines[k].set_label(f'{latest_values[k]:.3f}\nChannel {k}')
            else:
                lines[k].set_label(f'Channel {k}')

        if legend is not None:
            legend.remove()
        legend = ax.legend(ncols=3)
        return lines.values()

    def queries(cmd):
        while True:
            sleep(0.01)
            rv = ThreadSafeDict()
            threaded_queries(supplies, cmd, channels, rv)
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


def make_logger(logfile_path, channels, cmd_label):
    if logfile_path is None:
        return lambda *_: None  # no-op
    f = open(logfile_path, 'w')
    header = 'timestamp,' + ','.join(f'{cmd_label}_ch{ch}' for ch in channels)
    print(header, file=f)

    def logger(measurements):
        ts = now().isoformat()
        line = ts + ',' + ','.join(f"{measurements.get(ch, ''):.3f}" if ch in measurements else '' for ch in channels)
#        line = ts + ',' + ','.join(str(measurements.get(ch, '')) for ch in channels)
        print(line, file=f, flush=True)

    return logger


def main(args):
    header = args.header
    if header is None:
        this = os.path.abspath(__file__)
        this = os.path.dirname(this)
        this = os.path.dirname(this)
        header = os.path.join(this, 'commands.h')

    host = normalize_host(args.host)
    machine_name = args.host
    if host in ("localhost", "127.0.0.1"):
        connection_host = host
        connection_port = args.remote_port
    else:
        connection_host = "127.0.0.1"
        connection_port = ensure_tunnel(
            host, args.user, args.gateway, args.local_port, args.remote_port
        )
    mksupply = lambda: PowerSupplyServerConnection(connection_host, connection_port, header)
    mksupplies = lambda chs: [mksupply() for ch in chs]
    channels = args.channels

    if args.logfile is None:
        log_prefix = None  # No logging
    elif args.logfile == '':
        log_prefix = now().strftime('hvlog_%Y%m%d_%H%M%S')  # Timestamp-based name
    else:
        log_prefix = args.logfile  # Use the provided name
    
    log_prefix = args.logfile or now().strftime('hvlog_%Y%m%d_%H%M%S')
    voltage_log = f'{log_prefix}_voltage.csv'
    current_log = f'{log_prefix}_current.csv'

    volt_logger = make_logger(f'{log_prefix}_voltage.csv' if log_prefix else None, channels, 'voltage')
    curr_logger = make_logger(f'{log_prefix}_current.csv' if log_prefix else None, channels, 'current')

    if args.no_plots:
        # If no plots, just run the loggers in background forever
        supplies_v = mksupplies(channels)
        supplies_i = mksupplies(channels)

        def run_query_loop(cmd, supplies, logger):
            while True:
                rv = ThreadSafeDict()
                threaded_queries(supplies, cmd, channels, rv)
                logger(rv.AsDict())
                sleep(0.1)

        t1 = threading.Thread(target=run_query_loop, args=('get_vhv', supplies_v, volt_logger), daemon=True)
        t2 = threading.Thread(target=run_query_loop, args=('get_ihv', supplies_i, curr_logger), daemon=True)
        t1.start()
        t2.start()
        try:
            while True:
                sleep(1)
        except KeyboardInterrupt:
            print("Logging interrupted.")
    else:
        voltages = timeseries(mksupplies(channels), channels,
                              'get_vhv', 'Voltage [V]',
                              (0.0, 300.0), (1.0, 3e3),
                              'linear',
                              volt_logger,
                              machine_name,
                             )
        currents = timeseries(mksupplies(channels), channels,
                              'get_ihv', 'Current [uA]',
                              (0.0, 300.0), (1.0, 30.0),
                              'linear',
                              curr_logger,
                              machine_name,
                             )
        #pcbtemp = timeseries(mksupplies(channels), channels,
        #                      'pcb_temp', 'PCB Temperature [degC]',
        #                      (0.0, 300.0), (25.0, 35.0),
        #                      'linear',
        #                      lambda *args: None,
        #                     )
        plt.show()

    
 

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', type=int, dest='channels', nargs='+', default=[])
    parser.add_argument(
        'host',
        nargs='?',
        default='localhost',
        help='Hostname like psu13 or fully-qualified mu2e-trk-psu13.fnal.gov',
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
