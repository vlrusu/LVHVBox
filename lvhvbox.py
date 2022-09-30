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

import cmd2
from commands import *

def loglvdata():

    # this has to use the commands in commands.py to read: voltages, currents, temps and whatever else we put in GUI
    lvlog.write("1 2 3\n")


def process_command(command):
    app.async_alert ("Processing command ")
    app.async_alert(' '.join(str(e) for e in command))
#    func = getattr(commands,command[0])
#    ret = func(command[1:])

#this would be better as a real module, avoid global
    ret = globals()[command[0]](command[1:])

    app.async_alert(' '.join(str(e) for e in ret))
    return 0

def lvloop():

    while (1):

        try:
            lvdata = lvqueue.get(block=False)
            app.async_alert("I got a command")
            retc = process_command(lvdata)
        
        except queue.Empty:
            loglvdata()
            time.sleep(1)




class CmdLoop(cmd2.Cmd):
    """Example cmd2 application where we create commands that just print the arguments they are called with."""

    def __init__(self):
        # Create command shortcuts which are typically 1 character abbreviations which can be used in place of a command. Leave as is
        shortcuts = dict(cmd2.DEFAULT_SHORTCUTS)
        shortcuts.update({'$': 'readvoltage', '%': 'readcurrent'})
        super().__init__(shortcuts=shortcuts)




#there has to bbe a command for every interaction we need. So, readvoltage, readcurrents, readtemps, etc. Each one has to have its counterpart in commands.py
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readvoltage(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])



    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_test(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])
        

      

if __name__ == '__main__':



    
    history_file = os.path.expanduser('.lvhv_history')
    if not os.path.exists(history_file):
        with open(history_file, "w") as fobj:
            fobj.write("")
    readline.read_history_file(history_file)
    atexit.register(readline.write_history_file, history_file)
    
    topdir = os.path.dirname(os.path.realpath(__file__))


    lvqueue = queue.Queue()


    lvlogname = "lvdata.log"

    lvlog = open(os.path.join(topdir,lvlogname),"w")

    lvThrd = threading.Thread(target=lvloop, daemon = True)
    lvThrd.start()
    
    app = CmdLoop()
    app.cmdloop()
    lvlog.close()
    sys.exit()

    
    
