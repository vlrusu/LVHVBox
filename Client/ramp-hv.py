# Ed Callaghan
# Test abstracted hv up/down routine
# March 2025

import argparse
import sys
from PowerSupplyServerConnection import PowerSupplyServerConnection
import threading

def set_voltage(supply, channel, voltage):
    supply.SetWireVoltage(channel, voltage)

def main(args):
    if len(args.channels) < 1:
        raise Exception('supply channels (-c)')

    threads = []
    for channel in args.channels:
        supply = PowerSupplyServerConnection('localhost', 12000,
                                             '/home/mu2e/LVHVBox/commands.h')
        thread = threading.Thread(name='Channel %d' % channel,
                                  daemon=True,
                                  target=set_voltage,
                                  args=(supply,channel,args.voltage),
                                 )
        threads.append(thread)

    for thread in threads:
        thread.start()

    done = False
    while not done and 0 < len(threads):
        for thread in threads:
            thread.join(timeout=0.1)
            if thread.is_alive():
                done &= False
            else:
                done &= True
                threads.remove(thread)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', type=int, dest='channels', nargs='+', default=[])
    parser.add_argument('-v', type=float, dest='voltage', default=0.0)

    args = parser.parse_args()
    main(args)
