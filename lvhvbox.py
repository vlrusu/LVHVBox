import sys
import glob
import os
import json
import struct
import time
import threading
import queue
import readline
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import math
import rlcompleter
from pprint import pprint
import atexit
import serial

import cmd2
from  commands import *

from datetime import datetime

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


    
def loglvdata():

    # this has to use the commands in commands.py to read: voltages, currents, temps and whatever else we put in GUI
    lvlog.write("1 2 3\n")
#    voltages = readvoltage()
#    lvlog.write(voltages)
    
def process_command(command):

    app.async_alert ("Processing command ")
    app.async_alert(' '.join(str(e) for e in command))
    func = getattr(lvhvbox,command[0])
    ret = func(command[1:])

#this would be better as a real module, avoid global
#    ret = globals()[command[0]](command[1:])

    app.async_alert(' '.join(str(e) for e in ret))

    return 0

def lvloop():

    while (1):

        try:
            lvdata = lvqueue.get(block=False)
            app.async_alert("I got a command")
            retc = process_command(lvdata)
        
        except queue.Empty:
            lvhvbox.loghvdata()
            loglvdata()
            time.sleep(1)




class CmdLoop(cmd2.Cmd):
    """Example cmd2 application where we create commands that just print the arguments they are called with."""

    def __init__(self):
        # Create command shortcuts which are typically 1 character abbreviations which can be used in place of a command. Leave as is
        shortcuts = dict(cmd2.DEFAULT_SHORTCUTS)
        shortcuts.update({'$': 'readvoltage', '%': 'readcurrent'})
        super().__init__(shortcuts=shortcuts)




#there has to be a command for every interaction we need. So, readvoltage, readcurrents, readtemps, etc. Each one has to have its counterpart in commands.py
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readvoltage(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])



    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    pprint_parser.add_argument('-u', '--rampup', action='store_true', help='Ramp up')
    @cmd2.with_argparser(pprint_parser)
    def do_test(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel, args.rampup])

    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOn(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOff(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

 
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    pprint_parser.add_argument('-u', '--rampup', action ='store_true', help='Rampup')
    @cmd2.with_argparser(pprint_parser)
    def do_ramp(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel, args.rampup])
       

    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_resetHV(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    pprint_parser.add_argument('-T', '--trippoint', type=int, help='Trip point in nA')
    @cmd2.with_argparser(pprint_parser)
    def do_setHVtrip(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel, args.trippoint])
        
      

if __name__ == '__main__':



    
    history_file = os.path.expanduser('.lvhv_history')
    if not os.path.exists(history_file):
        with open(history_file, "w") as fobj:
            fobj.write("")
    readline.read_history_file(history_file)
    atexit.register(readline.write_history_file, history_file)
    
    topdir = os.path.dirname(os.path.realpath(__file__))


    lvqueue = queue.Queue()
    hvqueue = queue.Queue()

    sertmp1 = serial.Serial('/dev/ttyACM0', 115200, timeout=0.1,write_timeout = 1)
    sertmp2 = serial.Serial('/dev/ttyACM1', 115200, timeout=0.1,write_timeout = 1)
    
    #decide which on the 1 and which is 2
    sertmp1.timeout = None
    line = sertmp1.readline().decode('ascii')
    whichone = line.split("|")[3][1]
    print("ser1 is " + str(whichone))    

    if whichone == 1:
        ser1=sertmp1
        ser2=sertmp2
    else:
        ser1 = sertmp2
        ser2 = sertmp1

    sertmp2.timeout = None    
    line = sertmp2.readline().decode('ascii')
    whichone = line.split("|")[3][1]
    print("ser2 is " + str(whichone))    


    lvlogname = "lvdata.log"
    lvlog = open(os.path.join(topdir,lvlogname),"w")
    hvlogname = "hvdata.log"
    hvlog = open(os.path.join(topdir,hvlogname),"w")


    
    app = CmdLoop()
    lvhvbox = LVHVBox(app,ser1,ser2,hvlog)

    
    

    lvThrd = threading.Thread(target=lvloop, daemon = True)
    lvThrd.start()
 

    

    
    app.cmdloop()
    lvlog.close()
    hvlog.close()
    sys.exit()

    
    
