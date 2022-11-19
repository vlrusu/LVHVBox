# GUI/Monitoring Software for the LVHV Boxes
# Coded by Isaiah Wardlaw
'''
import sys
import glob
import os
import json
import struct
import time
import threading
import readline
import asyncio
import commands
import numpy

import matplotlib
'''

import os
import readline
import atexit
import queue
import logging
import serial
import matplotlib
import sys
from commands import *
import cmd2


from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QWidget,
    QTabWidget,
    QGridLayout,
    QTableWidget,
    QLabel,
    QMainWindow,
)
from PyQt5 import QtCore

matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

os.environ["DISPLAY"] = ':0'
background_color='background-color: white;'
button_color='background-color: white;'


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
            app.async_alert("I got a LV command")
            retc = process_command(lvdata)

        except queue.Empty:
            lvhvbox.loglvdata()
            time.sleep(0.1)

def hvloop1():

    while (1):
        try:
            hvdata = hvqueue1.get(block=False)
            app.async_alert("I got a HV command")
            retc = process_command(hvdata)

        except queue.Empty:
            lvhvbox.loghvdata1()
            time.sleep(0.1)


def hvloop2():

    while (1):
        try:
            hvdata = hvqueue2.get(block=False)
            app.async_alert("I got a HV command")
            retc = process_command(hvdata)

        except queue.Empty:
            lvhvbox.loghvdata2()
            time.sleep(0.1)


class CmdLoop(cmd2.Cmd):
    """Example cmd2 application where we create commands that just print the arguments they are called with."""

    def __init__(self):
        # Create command shortcuts which are typically 1 character abbreviations which can be used in place of a command. Leave as is
        shortcuts = dict(cmd2.DEFAULT_SHORTCUTS)
        shortcuts.update({'$': 'readvoltage', '%': 'readcurrent'})
        super().__init__(shortcuts=shortcuts)


    # There has to be a command for every interaction we need. So, readvoltage, readcurrents, readtemps, etc.
    # Each one has to have its counterpart in commands.py

    # readvoltage()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readvoltage(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

    # readcurrent()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readcurrent(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

    # readtemp()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readtemp(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

    # test()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-v', '--voltage', type=float, help='Volatge to ramp to')
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')

    @cmd2.with_argparser(pprint_parser)
    def do_test(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel, args.voltage])


    # powerOn()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOn(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

    # powerOff()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOff(self, args):
        """Print the options and argument list this options command was called with."""
        lvqueue.put([args.cmd2_statement.get().command, args.channel])

    # ramp()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    pprint_parser.add_argument('-v', '--voltage', type=int, help='Volatge to ramp to')

    @cmd2.with_argparser(pprint_parser)
    def do_ramp(self, args):
        """Print the options and argument list this options command was called with."""
        hvqueue1.put([args.cmd2_statement.get().command, args.channel, args.voltage])
    # down()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')

    @cmd2.with_argparser(pprint_parser)
    def do_down(self, args):
        """Print the options and argument list this options command was called with."""
        hvqueue1.put([args.cmd2_statement.get().command, args.channel])

    # resetHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_resetHV(self, args):
        """Print the options and argument list this options command was called with."""
        hvqueue1.put([args.cmd2_statement.get().command, args.channel])

    # setHVtrip()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    pprint_parser.add_argument('-T', '--trippoint', type=int, help='Trip point in nA')
    @cmd2.with_argparser(pprint_parser)
    def do_setHVtrip(self, args):
        """Print the options and argument list this options command was called with."""
        hvqueue1.put([args.cmd2_statement.get().command, args.channel, args.trippoint])


class Window(QMainWindow):
    def __init__(self,test,v48,i48,T48,hv_v,hv_i,hvpcbtemp,i12V):
        super(Window,self).__init__()

        self.test=test
        self.v48=v48
        self.i48=i48
        self.T48=T48
        self.hv_v=hv_v
        self.hv_i=hv_i
        self.hvpcbtemp=hvpcbtemp
        self.i12V=i12V



        #window.setCursor(PyQt5.BlankCursor)
        self.setWindowTitle("LVHV GUI")
        self.setStyleSheet(background_color)

        self.initialize_data()
        self.tabs()



        self.showFullScreen()

    # calls all of the tab initialization functions
    def tabs(self):
        self.tabs=QTabWidget()

        self.plotting=QWidget()
        self.plotting.layout=QGridLayout()
        self.plotting_tabs=QTabWidget()

        # initialize tables
        self.controls_setup()


        # initialize hv controls
        self.lv_controls_setup()


        # initialize hv controls setup
        self.hv_controls_setup()

        '''
        # initialize misc tab
        #self.misc_setup()
        '''

        # initialize blade plotting Window
        self.blade_plotting_setup()

        # initialize board plotting Window
        self.board_plotting_setup()

        # initialize hv plotting Window
        self.hv_plotting_setup()

        '''

        # initialize stability blade plotting Window
        self.stability_blade_plotting_setup()

        # initialize stabiility board plotting Window
        self.stability_board_plotting_setup()

        # initialize stability hv plotting Window
        self.stability_hv_plotting_setup()
        '''


        # adds tabs to the overall GUI
        self.tabs.addTab(self.tab1,"Tables")

        self.tabs.addTab(self.tab2,"LV Actuation")


        self.tabs.addTab(self.tab3,"HV Actuation")

        self.tabs.addTab(self.plotting,"Plots")

        #self.tabs.addTab(self.misc_functions,"Misc")

        self.plotting_tabs.addTab(self.tab4,"Blade Plots")
        self.plotting_tabs.addTab(self.tab5,"Board Plots")
        self.plotting_tabs.addTab(self.tab6,"HV Plots")

        '''
        self.plotting_tabs.addTab(self.tab7,"Blade Stability")
        self.plotting_tabs.addTab(self.tab8,"Board Stability")
        self.plotting_tabs.addTab(self.tab9,"HV Stability")
        '''
        self.plotting.layout.addWidget(self.plotting_tabs)
        self.plotting.setLayout(self.plotting.layout)


        # set title and place tab widget for pyqt
        self.setWindowTitle("LVHV GUI")
        self.setCentralWidget(self.tabs)

        self.show()



     # sets up initial tables with "N/A" values
    def controls_setup(self):
        self.tab1=QWidget()
        self.tab1.layout=QGridLayout()
        self.tab1.layout.setContentsMargins(20,20,20,20)

        # setup blade table
        self.blade_control_table=QTableWidget()
        self.blade_control_table.setRowCount(6)
        self.blade_control_table.setColumnCount(5)
        self.blade_control_table.setFixedWidth(550)
        self.blade_control_table.setDisabled(True)

        self.blade_control_table.setHorizontalHeaderLabels(["Voltage (V)","current (A)","Temp (C)","HV PCB Temp","Board Current"])
        self.blade_control_table.setVerticalHeaderLabels(["Ch 0","Ch 1","Ch 2","Ch 3","Ch 4","Ch 5"])
        #self.blade_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

        '''
        # setup board table
        self.board_control_table=QTableWidget()
        self.board_control_table.setRowCount(6)
        self.board_control_table.setColumnCount(4)
        self.board_control_table.setFixedWidth(550)
        self.board_control_table.setDisabled(True)

        self.board_control_table.setHorizontalHeaderLabels(["5V Voltage (V)","5V Current (A)","Cond Voltage (V)","Cond Current (A)"])
        self.board_control_table.setVerticalHeaderLabels(["Ch 0","Ch 1","Ch 2","Ch 3","Ch 4","Ch 5"])
        #self.board_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        '''

        # setup hv table
        self.hv_control_table=QTableWidget()
        self.hv_control_table.setRowCount(12)
        self.hv_control_table.setColumnCount(2)
        self.hv_control_table.setFixedWidth(550)
        self.hv_control_table.setDisabled(True)
        for i in range(0,12):
            self.hv_control_table.setRowHeight(i,24)

        self.hv_control_table.setVerticalHeaderLabels(["Ch 0","Ch 1","Ch 2","Ch 3","Ch 4","Ch 5","Ch 6","Ch 7","Ch 8","Ch 9","Ch 10","Ch 11"])
        self.hv_control_table.setHorizontalHeaderLabels(["Voltage (V)","Current (A)"])

        # set up tabs to select whether to view blade data or board data
        self.table_tabs=QTabWidget()
        self.table_tab1=QWidget()
        self.table_tab1.layout=QGridLayout()
        self.table_tab2=QWidget()
        self.table_tab2.layout=QGridLayout()
        self.table_tab3=QWidget()
        self.table_tab3.layout=QGridLayout()
        self.table_tabs.addTab(self.table_tab1,"Blade Data")
        self.table_tabs.addTab(self.table_tab2,"Board Data")
        self.table_tabs.addTab(self.table_tab3,"HV Data")

        # add table widgets to tab container
        self.table_tab1.layout.addWidget(self.blade_control_table,0,0)
        self.table_tab1.setLayout(self.table_tab1.layout)
        '''
        self.table_tab2.layout.addWidget(self.board_control_table,0,0)
        self.table_tab2.setLayout(self.table_tab2.layout)
        '''
        self.table_tab3.layout.addWidget(self.hv_control_table,0,0)
        self.table_tab3.setLayout(self.table_tab3.layout)

        for i in range(6):
            # fill with blade voltage entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.blade_voltage_entries.append(current_entry)
            self.blade_control_table.setCellWidget(i,0,current_entry)

            # fill with blade current entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.blade_current_entries.append(current_entry)
            self.blade_control_table.setCellWidget(i,1,current_entry)

            # fill with blade temperature entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.blade_temperature_entries.append(current_entry)
            self.blade_control_table.setCellWidget(i,2,current_entry)
        # add pcb temp
        pcbtempentry=QLabel("N/A")
        pcbtempentry.setAlignment(Qt.AlignCenter)
        pcbtempentry.setStyleSheet(button_color)
        self.pcbtempentry=pcbtempentry
        self.blade_control_table.setCellWidget(0,3,pcbtempentry)

        # add 12V board current
        i12Ventry=QLabel("N/A")
        i12Ventry.setAlignment(Qt.AlignCenter)
        i12Ventry.setStyleSheet(button_color)
        self.i12Ventry=i12Ventry
        self.blade_control_table.setCellWidget(0,4,i12V)

        # fill board table with entries and set background color
        self.board_5v_voltage_entries=[]
        self.board_5v_current_entries=[]
        self.board_cond_voltage_entries=[]
        self.board_cond_current_entries=[]

        for i in range(6):
            # fill with board 5v voltage entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.board_5v_voltage_entries.append(current_entry)
            self.board_control_table.setCellWidget(i,0,current_entry)

            # fill with board 5v current entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.board_5v_current_entries.append(current_entry)
            self.board_control_table.setCellWidget(i,1,current_entry)

            # fill with board conditioned voltage entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.board_cond_voltage_entries.append(current_entry)
            self.board_control_table.setCellWidget(i,2,current_entry)

            # fill with board conditioned current entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.board_cond_current_entries.append(current_entry)
            self.board_control_table.setCellWidget(i,3,current_entry)

        # fill board table with entries and set background color
        self.hv_voltage_entries=[]
        self.hv_current_entries=[]

        for i in range(12):
            # fill with hv voltage entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.hv_voltage_entries.append(current_entry)
            self.hv_control_table.setCellWidget(i,0,current_entry)

            # fill with hv current entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.hv_current_entries.append(current_entry)
            self.hv_control_table.setCellWidget(i,1,current_entry)

        # add tab container to table_box
        self.table_box=QWidget()
        self.table_box.layout=QGridLayout()
        self.table_box.layout.addWidget(self.table_tabs,0,1)
        self.table_box.setLayout(self.table_box.layout)

        self.tab1.layout.addWidget(self.table_box,0,0)

        self.tab1.setLayout(self.tab1.layout)


    # sets up the lv control tab for the GUI
    def lv_controls_setup(self):
        self.tab2=QWidget()
        self.tab2.layout=QGridLayout()

        # initialize lv control buttons and indicators
        self.lv_power_button_1=QPushButton("LV 0")
        self.lv_power_button_1.setFixedSize(QSize(210, 130))
        self.lv_power_button_1.setStyleSheet('background-color: red')
        self.lv_power_button_1.setFont(QFont("Arial", 45))

        self.lv_power_button_2=QPushButton("LV 1")
        self.lv_power_button_2.setFixedSize(QSize(210, 130))
        self.lv_power_button_2.setStyleSheet('background-color: red')
        self.lv_power_button_2.setFont(QFont("Arial", 45))

        self.lv_power_button_3=QPushButton("LV 2")
        self.lv_power_button_3.setFixedSize(QSize(210, 130))
        self.lv_power_button_3.setStyleSheet('background-color: red')
        self.lv_power_button_3.setFont(QFont("Arial", 45))

        self.lv_power_button_4=QPushButton("LV 3")
        self.lv_power_button_4.setFixedSize(QSize(210, 130))
        self.lv_power_button_4.setStyleSheet('background-color: red')
        self.lv_power_button_4.setFont(QFont("Arial", 45))

        self.lv_power_button_5=QPushButton("LV 4")
        self.lv_power_button_5.setFixedSize(QSize(210, 130))
        self.lv_power_button_5.setStyleSheet('background-color: red')
        self.lv_power_button_5.setFont(QFont("Arial", 45))

        self.lv_power_button_6=QPushButton("LV 5")
        self.lv_power_button_6.setFixedSize(QSize(210, 130))
        self.lv_power_button_6.setStyleSheet('background-color: red')
        self.lv_power_button_6.setFont(QFont("Arial", 45))

        # add lv power buttons to layout
        self.tab2.layout.addWidget(self.lv_power_button_1,0,0)
        self.tab2.layout.addWidget(self.lv_power_button_2,0,1)
        self.tab2.layout.addWidget(self.lv_power_button_3,0,2)
        self.tab2.layout.addWidget(self.lv_power_button_4,1,0)
        self.tab2.layout.addWidget(self.lv_power_button_5,1,1)
        self.tab2.layout.addWidget(self.lv_power_button_6,1,2)

        # connect lv power buttons to actuate_lv_power()
        self.lv_power_button_1.clicked.connect(lambda: self.actuate_lv_power(0))
        self.lv_power_button_2.clicked.connect(lambda: self.actuate_lv_power(1))
        self.lv_power_button_3.clicked.connect(lambda: self.actuate_lv_power(2))
        self.lv_power_button_4.clicked.connect(lambda: self.actuate_lv_power(3))
        self.lv_power_button_5.clicked.connect(lambda: self.actuate_lv_power(4))
        self.lv_power_button_6.clicked.connect(lambda: self.actuate_lv_power(5))

        self.tab2.setLayout(self.tab2.layout)


    # called when one of the lv power buttons is pressed
    def actuate_lv_power(self,number):
        indicators=[self.lv_power_button_1,self.lv_power_button_2,self.lv_power_button_3,self.lv_power_button_4,
        self.lv_power_button_5,self.lv_power_button_6]

        if self.blade_power[number]==True:
            indicators[number].setStyleSheet('background-color: red')
            self.blade_power[number]=False
            #self.power_off(number)
        else:
            indicators[number].setStyleSheet('background-color: green')
            self.blade_power[number]=True
            #self.power_on(number)



    # called when one of the hv power buttons is pressed
    def actuate_hv_power(self,number):
        indicators=[self.hv_power_button_1,self.hv_power_button_2,self.hv_power_button_3,
        self.hv_power_button_4,self.hv_power_button_5,self.hv_power_button_6,
        self.hv_power_button_7,self.hv_power_button_8,self.hv_power_button_9,
        self.hv_power_button_10,self.hv_power_button_11,self.hv_power_button_12]

        if self.hv_power[number]==True:
            indicators[number].setStyleSheet('background-color: red')
            self.hv_power[number]=False

            # if gui isn't in test mode, power down hv channel
            if self.test is False:
                # use threading to ensure that the gui doesn't freeze during rampup
                #self.rampup_list.append([number,False])
                pass
        else:
            indicators[number].setStyleSheet('background-color: green')
            self.hv_power[number]=True

            # if gui isn't in test mode, power up hv channel
            if self.test is False:
                # use threading to ensure that the gui doesn't freeze during rampup
                #self.rampup_list.append([number,True])
                pass


    # sets up the hv control tab for the GUI
    def hv_controls_setup(self):
        self.tab3=QWidget()
        self.tab3.layout=QGridLayout()

        # initilize hv control buttons
        self.hv_power_button_1=QPushButton("HV 0")
        self.hv_power_button_1.setFixedSize(QSize(130, 80))
        self.hv_power_button_1.setStyleSheet('background-color: red')
        self.hv_power_button_1.setFont(QFont("Arial", 30))

        self.hv_power_button_2=QPushButton("HV 1")
        self.hv_power_button_2.setFixedSize(QSize(130, 80))
        self.hv_power_button_2.setStyleSheet('background-color: red')
        self.hv_power_button_2.setFont(QFont("Arial", 30))

        self.hv_power_button_3=QPushButton("HV 2")
        self.hv_power_button_3.setFixedSize(QSize(130, 80))
        self.hv_power_button_3.setStyleSheet('background-color: red')
        self.hv_power_button_3.setFont(QFont("Arial", 30))

        self.hv_power_button_4=QPushButton("HV 3")
        self.hv_power_button_4.setFixedSize(QSize(130, 80))
        self.hv_power_button_4.setStyleSheet('background-color: red')
        self.hv_power_button_4.setFont(QFont("Arial", 30))

        self.hv_power_button_5=QPushButton("HV 4")
        self.hv_power_button_5.setFixedSize(QSize(130, 80))
        self.hv_power_button_5.setStyleSheet('background-color: red')
        self.hv_power_button_5.setFont(QFont("Arial", 30))

        self.hv_power_button_6=QPushButton("HV 5")
        self.hv_power_button_6.setFixedSize(QSize(130, 80))
        self.hv_power_button_6.setStyleSheet('background-color: red')
        self.hv_power_button_6.setFont(QFont("Arial", 30))

        self.hv_power_button_7=QPushButton("HV 6")
        self.hv_power_button_7.setFixedSize(QSize(130, 80))
        self.hv_power_button_7.setStyleSheet('background-color: red')
        self.hv_power_button_7.setFont(QFont("Arial", 30))

        self.hv_power_button_8=QPushButton("HV 7")
        self.hv_power_button_8.setFixedSize(QSize(130, 80))
        self.hv_power_button_8.setStyleSheet('background-color: red')
        self.hv_power_button_8.setFont(QFont("Arial", 30))

        self.hv_power_button_9=QPushButton("HV 8")
        self.hv_power_button_9.setFixedSize(QSize(130, 80))
        self.hv_power_button_9.setStyleSheet('background-color: red')
        self.hv_power_button_9.setFont(QFont("Arial", 30))

        self.hv_power_button_10=QPushButton("HV 9")
        self.hv_power_button_10.setFixedSize(QSize(130, 80))
        self.hv_power_button_10.setStyleSheet('background-color: red')
        self.hv_power_button_10.setFont(QFont("Arial", 30))

        self.hv_power_button_11=QPushButton("HV 10")
        self.hv_power_button_11.setFixedSize(QSize(130, 80))
        self.hv_power_button_11.setStyleSheet('background-color: red')
        self.hv_power_button_11.setFont(QFont("Arial", 30))

        self.hv_power_button_12=QPushButton("HV 11")
        self.hv_power_button_12.setFixedSize(QSize(130, 80))
        self.hv_power_button_12.setStyleSheet('background-color: red')
        self.hv_power_button_12.setFont(QFont("Arial", 30))

        # initialize hv ramp up bars
        self.hv_bar_1=QProgressBar()
        self.hv_bar_1.setFixedSize(QSize(130, 20))

        self.hv_bar_2=QProgressBar()
        self.hv_bar_2.setFixedSize(QSize(130, 20))

        self.hv_bar_3=QProgressBar()
        self.hv_bar_3.setFixedSize(QSize(130, 20))

        self.hv_bar_4=QProgressBar()
        self.hv_bar_4.setFixedSize(QSize(130, 20))

        self.hv_bar_5=QProgressBar()
        self.hv_bar_5.setFixedSize(QSize(130, 20))

        self.hv_bar_6=QProgressBar()
        self.hv_bar_6.setFixedSize(QSize(130, 20))

        self.hv_bar_7=QProgressBar()
        self.hv_bar_7.setFixedSize(QSize(130, 20))

        self.hv_bar_8=QProgressBar()
        self.hv_bar_8.setFixedSize(QSize(130, 20))

        self.hv_bar_9=QProgressBar()
        self.hv_bar_9.setFixedSize(QSize(130, 20))

        self.hv_bar_10=QProgressBar()
        self.hv_bar_10.setFixedSize(QSize(130, 20))

        self.hv_bar_11=QProgressBar()
        self.hv_bar_11.setFixedSize(QSize(130, 20))

        self.hv_bar_12=QProgressBar()
        self.hv_bar_12.setFixedSize(QSize(130, 20))

        # add hv power buttons to layout
        self.tab3.layout.addWidget(self.hv_power_button_1,1,0)
        self.tab3.layout.addWidget(self.hv_power_button_2,1,1)
        self.tab3.layout.addWidget(self.hv_power_button_3,1,2)
        self.tab3.layout.addWidget(self.hv_power_button_4,1,3)
        self.tab3.layout.addWidget(self.hv_power_button_5,3,0)
        self.tab3.layout.addWidget(self.hv_power_button_6,3,1)
        self.tab3.layout.addWidget(self.hv_power_button_7,3,2)
        self.tab3.layout.addWidget(self.hv_power_button_8,3,3)
        self.tab3.layout.addWidget(self.hv_power_button_9,5,0)
        self.tab3.layout.addWidget(self.hv_power_button_10,5,1)
        self.tab3.layout.addWidget(self.hv_power_button_11,5,2)
        self.tab3.layout.addWidget(self.hv_power_button_12,5,3)

        # add hv progress bars to layout
        self.tab3.layout.addWidget(self.hv_bar_1,0,0)
        self.tab3.layout.addWidget(self.hv_bar_2,0,1)
        self.tab3.layout.addWidget(self.hv_bar_3,0,2)
        self.tab3.layout.addWidget(self.hv_bar_4,0,3)
        self.tab3.layout.addWidget(self.hv_bar_5,2,0)
        self.tab3.layout.addWidget(self.hv_bar_6,2,1)
        self.tab3.layout.addWidget(self.hv_bar_7,2,2)
        self.tab3.layout.addWidget(self.hv_bar_8,2,3)
        self.tab3.layout.addWidget(self.hv_bar_9,4,0)
        self.tab3.layout.addWidget(self.hv_bar_10,4,1)
        self.tab3.layout.addWidget(self.hv_bar_11,4,2)
        self.tab3.layout.addWidget(self.hv_bar_12,4,3)

        #connect hv power buttons to actuate_hv_power
        self.hv_power_button_1.clicked.connect(lambda: self.actuate_hv_power(0))
        self.hv_power_button_2.clicked.connect(lambda: self.actuate_hv_power(1))
        self.hv_power_button_3.clicked.connect(lambda: self.actuate_hv_power(2))
        self.hv_power_button_4.clicked.connect(lambda: self.actuate_hv_power(3))
        self.hv_power_button_5.clicked.connect(lambda: self.actuate_hv_power(4))
        self.hv_power_button_6.clicked.connect(lambda: self.actuate_hv_power(5))
        self.hv_power_button_7.clicked.connect(lambda: self.actuate_hv_power(6))
        self.hv_power_button_8.clicked.connect(lambda: self.actuate_hv_power(7))
        self.hv_power_button_9.clicked.connect(lambda: self.actuate_hv_power(8))
        self.hv_power_button_10.clicked.connect(lambda: self.actuate_hv_power(9))
        self.hv_power_button_11.clicked.connect(lambda: self.actuate_hv_power(10))
        self.hv_power_button_12.clicked.connect(lambda: self.actuate_hv_power(11))

        self.tab3.setLayout(self.tab3.layout)

    # initializes blade plotting (exelcys)
    def blade_plotting_setup(self):
        self.tab4=QWidget()
        self.tab4.layout=QGridLayout()

        # set up the blade plot
        self.blade_plot=Figure()
        self.blade_plot_canvas=FigureCanvas(self.blade_plot)
        self.blade_plot_axes=self.blade_plot.add_subplot(111)

        self.blade_plot_axes.set_xlim([0,10])
        self.blade_plot_axes.set_ylim([0,60])
        self.blade_plot_axes.set_title('Channel 0 Blade Voltage')
        self.blade_plot_axes.set_ylabel('Voltage (V)')
        self.blade_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + 'TBD' + ' minutes.')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.blade_plot_data_x=[*range(0,10,1)]
        self.blade_plot_data=self.blade_plot_axes.plot(self.blade_plot_data_x,self.blade_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.blade_channel_selector=QComboBox()
        self.blade_channel_selector.addItems(["Channel 0","Channel 1","Channel 2","Channel 3","Channel 4","Channel 5"])
        self.blade_channel_selector.setStyleSheet(button_color)
        self.blade_channel_selector.currentIndexChanged.connect(self.change_blade_plot)

        self.blade_measurement_selector=QComboBox()
        self.blade_measurement_selector.addItems(["Voltage","Current","Temperature"])
        self.blade_measurement_selector.setStyleSheet(button_color)
        self.blade_measurement_selector.currentIndexChanged.connect(self.change_blade_plot)

        # add widgets and set layout
        self.tab4.layout.addWidget(self.blade_channel_selector,0,0)
        self.tab4.layout.addWidget(self.blade_measurement_selector,1,0)
        self.tab4.layout.addWidget(self.blade_plot_canvas,0,1)
        self.tab4.setLayout(self.tab4.layout)

    # instantly changes what's being displayed on the main plot, depending on the user's selection
    # this function is only used when the TYPE of data that is being plotted changes, as per user input
    def change_blade_plot(self):
        channel=self.get_blade_channel()
        type=self.blade_measurement_selector.currentText()

        # update labels for the blade plot
        self.blade_plot_axes.set_title(self.blade_channel_selector.currentText() + ' Blade ' + type)
        if type=="Voltage":
            self.blade_plot_axes.set_ylabel('Voltage (V)')
        elif type=="Current":
            self.blade_plot_axes.set_ylabel('Current (A)')
        else:
            self.blade_plot_axes.set_ylabel('Temperature (C)')

        # ensure that the proper type of data is plotted
        if type=="Voltage":
            self.blade_plot_data.set_ydata(self.blade_voltage_plot[channel])
        elif type=="Current":
            self.blade_plot_data.set_ydata(self.blade_current_plot[channel])
        else:
            self.blade_plot_data.set_ydata(self.blade_temperature_plot[channel])

        # update the plot
        self.blade_plot_canvas.draw()
        self.blade_plot_canvas.flush_events()

    # initializes board plotting (readmon)
    def board_plotting_setup(self):
        self.tab5=QWidget()
        self.tab5.layout=QGridLayout()

        # setup the board plot
        self.board_plot=Figure()
        self.board_plot_canvas=FigureCanvas(self.board_plot)
        self.board_plot_axes=self.board_plot.add_subplot(111)

        self.board_plot_axes.set_xlim([0,10])
        self.board_plot_axes.set_ylim([0,60])
        self.board_plot_axes.set_title('Channel 0 5V Voltage')
        self.board_plot_axes.set_ylabel('Voltage (V)')
        self.board_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + 'TBD' + ' minutes.')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.board_plot_data_x=[*range(0,10,1)]
        self.board_plot_data=self.board_plot_axes.plot(self.board_plot_data_x,self.board_5v_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.board_channel_selector=QComboBox()
        self.board_channel_selector.addItems(["Channel 0","Channel 1","Channel 2","Channel 3","Channel 4","Channel 5"])
        self.board_channel_selector.setStyleSheet(button_color)
        self.board_channel_selector.currentIndexChanged.connect(self.change_board_plot)

        self.board_measurement_selector=QComboBox()
        self.board_measurement_selector.addItems(["5V Voltage","5V Current","Conditioned Voltage","Conditioned Current"])
        self.board_measurement_selector.setStyleSheet(button_color)
        self.board_measurement_selector.currentIndexChanged.connect(self.change_board_plot)

        # add widgets and set layout
        self.tab5.layout.addWidget(self.board_channel_selector,0,0)
        self.tab5.layout.addWidget(self.board_measurement_selector,1,0)
        self.tab5.layout.addWidget(self.board_plot_canvas,0,1)
        self.tab5.setLayout(self.tab5.layout)

    # called to change the board plot (readmon data)
    # this function is only used when the TYPE of data that is being plotted changes, as per user input
    def change_board_plot(self):
        channel=self.get_board_channel()
        type=self.board_measurement_selector.currentText()

        # update labels for the board plot
        self.board_plot_axes.set_title(self.board_channel_selector.currentText() + ' Board ' + type)
        if type=="5V Voltage":
            self.board_plot_axes.set_ylabel('5V Voltage (V)')
        elif type=="5V Current":
            self.board_plot_axes.set_ylabel('5V Current (A)')
        elif type=="Conditioned Voltage":
            self.board_plot_axes.set_ylabel('Conditioned Voltage (V)')
        else:
            self.board_plot_axes.set_ylabel('Conditioned Current (A)')

        # update the data, according to what is being plotted
        if type=="5V Voltage":
            self.board_plot_data.set_ydata(self.board_5v_voltage_plot[channel])
        elif type=="5V Current":
            self.board_plot_data.set_ydata(self.board_5v_current_plot[channel])
        elif type=="Conditioned Voltage":
            self.board_plot_data.set_ydata(self.board_cond_voltage_plot[channel])
        else:
            self.board_plot_data.set_ydata(self.board_cond_current_plot[channel])

        # actually update the plot
        self.board_plot_canvas.draw()
        self.board_plot_canvas.flush_events()

    # initializes hv plotting
    def hv_plotting_setup(self):
        self.tab6=QWidget()
        self.tab6.layout=QGridLayout()

        # setup the hv plot
        self.hv_plot=Figure()
        self.hv_plot_canvas=FigureCanvas(self.hv_plot)
        self.hv_plot_axes=self.hv_plot.add_subplot(111)

        self.hv_plot_axes.set_xlim([0,10])
        self.hv_plot_axes.set_ylim([0,1600])
        self.hv_plot_axes.set_title('Channel 0 HV Voltage')
        self.hv_plot_axes.set_ylabel('Voltage (V)')
        self.hv_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + 'TBD' + ' minutes.')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.hv_plot_data_x=[*range(0,10,1)]
        self.hv_plot_data=self.hv_plot_axes.plot(self.hv_plot_data_x,self.hv_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.hv_channel_selector=QComboBox()
        self.hv_channel_selector.addItems(["Channel 0","Channel 1","Channel 2","Channel 3","Channel 4","Channel 5",
        "Channel 6","Channel 7","Channel 8","Channel 9","Channel 10","Channel 11"])
        self.hv_channel_selector.setStyleSheet(button_color)
        self.hv_channel_selector.currentIndexChanged.connect(self.change_hv_plot)

        self.hv_measurement_selector=QComboBox()
        self.hv_measurement_selector.addItems(["Voltage","Current"])
        self.hv_measurement_selector.setStyleSheet(button_color)
        self.hv_measurement_selector.currentIndexChanged.connect(self.change_hv_plot)

        # add widgets and set layout
        self.tab6.layout.addWidget(self.hv_channel_selector,0,0)
        self.tab6.layout.addWidget(self.hv_measurement_selector,1,0)
        self.tab6.layout.addWidget(self.hv_plot_canvas,0,1)
        self.tab6.setLayout(self.tab6.layout)

    # called to change the hv plot
    # this function is only used when the TYPE of data that is being plotted changes, as per user input
    def change_hv_plot(self):
        channel=self.get_hv_channel()
        type=self.hv_measurement_selector.currentText()

        # update labels for the hv plot
        self.hv_plot_axes.set_title(self.hv_channel_selector.currentText() + ' HV ' + type)
        if type=="Voltage":
            self.hv_plot_axes.set_ylabel('Voltage (V)')
            self.hv_plot_axes.set_ylim([0,1600])
        else:
            self.hv_plot_axes.set_ylabel('Current (A)')
            self.hv_plot_axes.set_ylim([0,100])

        # ensure that the proper type of data is being plotted
        if type=="Voltage":
            self.hv_plot_data.set_ydata(self.hv_voltage_plot[channel])
        else:
            self.hv_plot_data.set_ydata(self.hv_current_plot[channel])

        # update the plot
        self.hv_plot_canvas.draw()
        self.hv_plot_canvas.flush_events()

    # updates the blade table with recent data
    def update_blade_table(self):
        for j in range(6):
            self.blade_voltage_entries[j].setText(str(self.v48[j]))
            self.blade_current_entries[j].setText(str(self.i48[j]))
            self.blade_temperature_entries[j].setText(str(self.T48[j]))
        self.pcbtempentry.setText(str(self.hvpcbtemp))
        self.i12Ventry.setText(str(self.i12V))

    # updates the board table with recent data (readmon data)
    def update_board_table(self):
        for j in range(6):
            self.board_5v_voltage_entries[j].setText(str(self.five_voltage[j]))
            self.board_5v_current_entries[j].setText(str(self.five_current[j]))
            self.board_cond_voltage_entries[j].setText(str(self.cond_voltage[j]))
            self.board_cond_current_entries[j].setText(str(self.cond_current[j]))

    # updates the hv table with latest available data
    def update_hv_table(self):
        for j in range(12):
            self.hv_voltage_entries[j].setText(str(self.hv_v[j]))
            self.hv_current_entries[j].setText(str(self.hv_i[j]))

    def update_data(self):
        self.update_hv_table()
        self.update_blade_table()

    def initialize_data(self):
        # keeps lv screen update from occuring until data is acquired
        self.initial_lv_display=True

        # initialize lists of data
        self.blade_voltage_plot=[[500]*10]*6
        self.blade_current_plot=[[500]*10]*6
        self.blade_temperature_plot=[[500]*10]*6

        self.board_5v_voltage_plot=[[500]*10]*6
        self.board_5v_current_plot=[[500]*10]*6
        self.board_cond_voltage_plot=[[500]*10]*6
        self.board_cond_current_plot=[[500]*10]*6

        self.hv_voltage_plot=[[10000]*10]*12
        self.hv_current_plot=[[10000]*10]*12

        self.stability_blade_voltage_plot=[[500]*48]*6
        self.stability_blade_current_plot=[[500]*48]*6
        self.stability_blade_temperature_plot=[[500]*48]*6

        self.stability_board_5v_voltage_plot=[[500]*48]*6
        self.stability_board_5v_current_plot=[[500]*48]*6
        self.stability_board_cond_voltage_plot=[[500]*48]*6
        self.stability_board_cond_current_plot=[[500]*48]*6

        self.stability_hv_voltage_plot=[[10000]*48]*12
        self.stability_hv_current_plot=[[10000]*48]*12

        # fill blade table with entries and set background color
        self.blade_voltage_entries=[]
        self.blade_current_entries=[]
        self.blade_temperature_entries=[]

        # keeps track of blade power statuses
        self.blade_power=[False]*6

        # keeps track of hv power statuses
        self.hv_power=[False]*12

        # vars to keep track of hv ramping
        self.is_ramping = False
        self.rampup_list=[]

        self.hv_voltage = [0]*12
        self.hv_current = [0]*12

        self.hv_board_temp=0
        self.hv_board_current=0

        self.table_update_timer = QTimer(self)
        self.table_update_timer.setSingleShot(False)
        self.table_update_timer.timeout.connect(self.update_data)
        self.table_update_timer.start(1000)




## Main function
## =============

if __name__ == '__main__':
    test = True
    if not test:
        history_file = os.path.expanduser('.lvhv_history')
        if not os.path.exists(history_file):
            with open(history_file, "w") as fobj:
                fobj.write("")
        readline.read_history_file(history_file)
        atexit.register(readline.write_history_file, history_file)

        topdir = os.path.dirname(os.path.realpath(__file__))


        lvqueue = queue.Queue()
        hvqueue1 = queue.Queue()
        hvqueue2 = queue.Queue() # this is such a hack!!!!

        logging.basicConfig(filename='lvhvbox.log', format='%(asctime)s:%(levelname)s:%(message)s', encoding='utf-8', level=logging.DEBUG)

        sertmp1 = serial.Serial('/dev/ttyACM0', 115200, timeout=10,write_timeout = 1)
        sertmp2 = serial.Serial('/dev/ttyACM1', 115200, timeout=10,write_timeout = 1)

        #decide which on the 1 and which is 2
        sertmp1.timeout = None

        line = ""
        while(len(line)) <30:
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
        #    print(len(line))
        whichone = line.split("|")[3][1]
        print("ser2 is " + str(whichone))


        lvlogname = "lvdata.log"
        lvlog = open(os.path.join(topdir,lvlogname),"w")
        hvlogname0 = "hvdata0.log"
        hvlog0 = open(os.path.join(topdir,hvlogname0),"w")
        hvlogname1 = "hvdata1.log"
        hvlog1 = open(os.path.join(topdir,hvlogname1),"w")


        app = CmdLoop()
        lvhvbox = LVHVBox(app,ser1,ser2,hvlog0,hvlog1,lvlog)


        lvThrd = threading.Thread(target=lvloop, daemon = True)
        lvThrd.start()
        hvThrd1 = threading.Thread(target=hvloop1, daemon = True)
        hvThrd1.start()
        hvThrd2 = threading.Thread(target=hvloop2, daemon = True)
        hvThrd2.start()

        time.sleep(4)

        App = QApplication(sys.argv)



        hv_i=lvhvbox.ihv0+lvhvbox.ihv1
        hv_v=lvhvbox.vhv0+lvhvbox.vhv1

        window = Window(True,lvhvbox.v48,lvhvbox.i48,lvhvbox.T48,hv_i,hv_v,lvhvbox.hvpcbtemp,lvhvbox.i12V)

        gui_thread = threading.Thread(target=App.exec(), daemon = True)
        gui_thread.start()

        app.cmdloop()
        lvlog.close()
        hvlog.close()
        sys.exit()
        sys.exit()
    else:
        v48=[48 for i in range(6)]
        i48=[6 for i in range(6)]
        T48=[30 for i in range(6)]
        hv_i=[0.1 for i in range(12)]
        hv_v=[1500 for i in range(12)]
        hvpcbtemp=35
        i12V=1

        App = QApplication(sys.argv)
        window = Window(True,v48,i48,T48,hv_i,hv_v,hvpcbtemp,i12V)

        gui_thread = threading.Thread(target=App.exec(), daemon = True)
        gui_thread.start()



    '''
    App = QApplication(sys.argv)
    window = Window(True)
    sys.exit(App.exec())
    '''
