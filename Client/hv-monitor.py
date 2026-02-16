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
import threading
from time import sleep

from PowerSupplyServerConnection import PowerSupplyServerConnection
from ThreadSafeDict import ThreadSafeDict

def now():
    rv = datetime.datetime.now()
    return rv

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

def timeseries(supplies, channels, cmd, label, xlim, ylim, yscale, logger):
    expire = xlim[1]
    buff = ClockedBuffer(expiration=datetime.timedelta(seconds=expire))

    fig = plt.figure()
    plt.xlabel('Time ago [s]')
    plt.ylabel(label)
    ax = plt.gca()
    lines = {}
    for channel in channels:
        label = 'Channel %d' % channel
        lines[channel], *rest = ax.plot([], [], '-', label=label)

    def init():
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_yscale(yscale)
        ax.legend(ncols=3)
        ax.invert_xaxis()
        return lines.values()

    def update(frame, lines, buff):
        buff.Consume(frame)
        rn = now()
        for k in lines.keys():
            # TODO this loop structure assumes the timeseries are aligned
            # which is not guaranteed
            if k in buff[0][0].keys():
                xx = [(rn - pair[1]).total_seconds() for pair in buff]
                yy = [pair[0][k] for pair in buff]
                lines[k].set_data(xx, yy)
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
                              blit=True)
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

    mksupply = lambda: PowerSupplyServerConnection('localhost', 12000, header)
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
                              lambda *args: None,
                             )
        currents = timeseries(mksupplies(channels), channels,
                              'get_ihv', 'Current [uA]',
                              (0.0, 300.0), (1.0, 300.0),
                              'linear',
                              lambda *args: None,
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
    parser.add_argument('--header', type=str, dest='header', default=None)
    parser.add_argument('--no-plots', action='store_true', help='Disable real-time plotting')
    parser.add_argument('--logfile', nargs='?', const='', default=None)
    
    args = parser.parse_args()
    main(args)
