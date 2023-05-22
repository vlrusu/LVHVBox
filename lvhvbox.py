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

import logging

import cmd2
from commands import *

from datetime import datetime

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS



## ===========================================
## Process command
## ===========================================

def process_command(command):

    app.async_alert ("Processing command ")
    app.async_alert(' '.join(str(e) for e in command))
    func = getattr(lvhvbox,command[0])
    ret = func(command[1:])

    # This would be better as a real module, avoid global
    #ret = globals()[command[0]](command[1:])

    app.async_alert(' '.join(str(e) for e in ret))
    return 0



## ===========================================
## Store LV data in loop
## ===========================================

def lvloop():

    while (1):
        try:
            lvdata = lvqueue.get(block=False)
            app.async_alert("I got a LV command")
            retc = process_command(lvdata)
        
        except queue.Empty:
            lvhvbox.loglvdata()
            time.sleep(1)



## ===========================================
## Store HV data in loop
## ===========================================

# HV channels 0 to 5
# ==================
def hvloop1():

    while (1):
        try:
            hvdata = hvqueue1.get(block=False)
            app.async_alert("I got a HV command")
            retc = process_command(hvdata)
        
        except queue.Empty:
            lvhvbox.loghvdata1()
            time.sleep(0.1)


# HV channels 6 to 11
# ===================
def hvloop2():

    while (1):
        try:
            hvdata = hvqueue2.get(block=False)
            app.async_alert("I got a HV command")
            retc = process_command(hvdata)
        
        except queue.Empty:
            lvhvbox.loghvdata2()
            time.sleep(0.1)
            


## ===========================================
## Execute commands
## ===========================================

class CmdLoop(cmd2.Cmd):
    """Example cmd2 application where we create commands that just print the arguments they are called with."""

    # Are this shortcuts necessary?
    def __init__(self):
        # Create command shortcuts which are typically 1 character abbreviations which can be used in place of a command. Leave as is
        shortcuts = dict(cmd2.DEFAULT_SHORTCUTS)
        shortcuts.update({'$': 'readvoltage', '%': 'readcurrent'})
        super().__init__(shortcuts=shortcuts)


    # There has to be a command for every interaction we need. So, readvoltage, readcurrents, readtemps, etc.
    # Each one has to have its counterpart in commands.py


    # LV commands
    # ===========

    # powerOn()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOn(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # powerOff()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOff(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # readvoltage()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readvoltage(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # readcurrent()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readcurrent(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # readtemp()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readtemp(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # test()
    #pprint_parser = cmd2.Cmd2ArgumentParser()
    #pprint_parser.add_argument('-v', '--voltage', type=float, help='Volatge to ramp to')
    #pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    #@cmd2.with_argparser(pprint_parser)
    #def do_test(self, args):
    #    """Print the options and argument list this options command was called with."""
    #    lvqueue.put([args.cmd2_statement.get().command, args.channel, args.voltage])


    # HV commands
    # ===========
            
    # rampHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int,   help='HV channel number')
    pprint_parser.add_argument('-v', '--voltage', type=float, help='Voltage to ramp up to')    
    @cmd2.with_argparser(pprint_parser)
    def do_rampHV(self, args):
        """Print the options and argument list this options command was called with."""
        if (args.channel < 6):
            hvqueue1.put([args.cmd2_statement.get().command, args.channel, args.voltage])
        else:
            hvqueue2.put([args.cmd2_statement.get().command, args.channel, args.voltage])

    # downHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='HV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_downHV(self, args):
        """Print the options and argument list this options command was called with."""
        if (args.channel < 6):
            hvqueue1.put([args.cmd2_statement.get().command, args.channel])
        else:
            hvqueue2.put([args.cmd2_statement.get().command, args.channel])


    # setHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int,   help='HV channel number')
    pprint_parser.add_argument('-v', '--voltage', type=float, help='Voltage to set')    
    @cmd2.with_argparser(pprint_parser)
    def do_setHV(self, args):
        """Print the options and argument list this options command was called with."""
        if (args.channel < 6):
            hvqueue1.put([args.cmd2_statement.get().command, args.channel, args.voltage])
        else:
            hvqueue2.put([args.cmd2_statement.get().command, args.channel, args.voltage])


# these next two commands refer to channel as pico channel not HV channel (so 0 or 1).
# As it is written now, the argument is though still the HV channel
    # resetHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='HV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_resetHV(self, args):
        """Print the options and argument list this options command was called with."""
        if (args.channel < 6):
            hvqueue1.put([args.cmd2_statement.get().command, 0])
        else:
            hvqueue2.put([args.cmd2_statement.get().command, 1])
        



    # setHVtrip()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel',   type=int, help='HV channel number')
    pprint_parser.add_argument('-T', '--trippoint', type=int, help='Trip point in nA')
    @cmd2.with_argparser(pprint_parser)
    def do_setHVtrip(self, args):
        """Print the options and argument list this options command was called with."""
        if (args.channel < 6):
            hvqueue1.put([args.cmd2_statement.get().command, 0, args.trippoint])
        else:
            hvqueue2.put([args.cmd2_statement.get().command, 1, args.trippoint])





    # get vhv1
    pprint_parser = cmd2.Cmd2ArgumentParser()
    @cmd2.with_argparser(pprint_parser)
    def do_get_vhv1(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

        
      

## ==========================================================================================
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
##  MAIN FUNCTION
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
## ==========================================================================================

if __name__ == '__main__':

    history_file = os.path.expanduser('.lvhv_history')
    if not os.path.exists(history_file):
        with open(history_file, "w") as fobj:
            fobj.write("")
    
    readline.read_history_file(history_file)
    atexit.register(readline.write_history_file, history_file)
    
    topdir = os.path.dirname(os.path.realpath(__file__))


    # Queue hacks
    lvqueue = queue.Queue()
    hvqueue1 = queue.Queue()
    hvqueue2 = queue.Queue() # this is such a hack!!!!

    logging.basicConfig(filename='lvhvbox.log', format='%(asctime)s:%(levelname)s:%(message)s', encoding='utf-8', level=logging.DEBUG)


    # Decide which serial is 1 and which is 2
    sertmp1 = serial.Serial('/dev/ttyACM0', 115200, timeout=10,write_timeout = 1)
    sertmp2 = serial.Serial('/dev/ttyACM1', 115200, timeout=10,write_timeout = 1)

    sertmp1.timeout = None
    line = ""
    while(len(line)) < 30:
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
    line = ""
    while(len(line)) < 30:
        line = sertmp2.readline().decode('ascii')
    whichone = line.split("|")[3][1]
    print("ser2 is " + str(whichone))


    # Log files
    lvlogname = "lvdata.log"
    lvlog = open(os.path.join(topdir,lvlogname),"w")
    hvlogname0 = "hvdata0.log"
    hvlog0 = open(os.path.join(topdir,hvlogname0),"w")
    hvlogname1 = "hvdata1.log"
    hvlog1 = open(os.path.join(topdir,hvlogname1),"w")
    

    # Run CMD
    app = CmdLoop()
    lvhvbox = LVHVBox(app,ser1,ser2,hvlog0, hvlog1,lvlog)

    lvThrd = threading.Thread(target=lvloop, daemon = True)
    lvThrd.start()
    hvThrd1 = threading.Thread(target=hvloop1, daemon = True)
    hvThrd1.start()
    hvThrd2 = threading.Thread(target=hvloop2, daemon = True)
    hvThrd2.start()
    
    app.cmdloop()
    sys.exit()

