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

from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

os.environ["DISPLAY"] = ':0'
background_color='background-color: white;'
button_color='background-color: white;'



class Window(QMainWindow):
    def __init__(self):
        super(Window,self).__init__()


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

        '''
        # initialize hv controls
        self.lv_controls_setup()

        # initialize hv controls setup
        self.hv_controls_setup()

        # initialize misc tab
        #self.misc_setup()

        # initialize blade plotting Window
        self.blade_plotting_setup()

        # initialize board plotting Window
        self.board_plotting_setup()

        # initialize hv plotting Window
        self.hv_plotting_setup()

        # initialize stability blade plotting Window
        self.stability_blade_plotting_setup()

        # initialize stabiility board plotting Window
        self.stability_board_plotting_setup()

        # initialize stability hv plotting Window
        self.stability_hv_plotting_setup()
        '''


        # adds tabs to the overall GUI
        self.tabs.addTab(self.tab1,"Tables")
        '''
        self.tabs.addTab(self.tab2,"LV Actuation")
        self.tabs.addTab(self.tab3,"HV Actuation")
        self.tabs.addTab(self.plotting,"Plots")
        #self.tabs.addTab(self.misc_functions,"Misc")
        self.plotting_tabs.addTab(self.tab4,"Blade Plots")
        self.plotting_tabs.addTab(self.tab5,"Board Plots")
        self.plotting_tabs.addTab(self.tab6,"HV Plots")
        self.plotting_tabs.addTab(self.tab7,"Blade Stability")
        self.plotting_tabs.addTab(self.tab8,"Board Stability")
        self.plotting_tabs.addTab(self.tab9,"HV Stability")
        self.plotting.layout.addWidget(self.plotting_tabs)
        self.plotting.setLayout(self.plotting.layout)
        '''

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
        self.blade_control_table.setColumnCount(3)
        self.blade_control_table.setFixedWidth(550)
        self.blade_control_table.setDisabled(True)

        self.blade_control_table.setHorizontalHeaderLabels(["Voltage (V)","current (A)","Temp (C)"])
        self.blade_control_table.setVerticalHeaderLabels(["Ch 0","Ch 1","Ch 2","Ch 3","Ch 4","Ch 5"])
        #self.blade_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

        # setup board table
        self.board_control_table=QTableWidget()
        self.board_control_table.setRowCount(6)
        self.board_control_table.setColumnCount(4)
        self.board_control_table.setFixedWidth(550)
        self.board_control_table.setDisabled(True)

        self.board_control_table.setHorizontalHeaderLabels(["5V Voltage (V)","5V Current (A)","Cond Voltage (V)","Cond Current (A)"])
        self.board_control_table.setVerticalHeaderLabels(["Ch 0","Ch 1","Ch 2","Ch 3","Ch 4","Ch 5"])
        #self.board_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

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
        self.table_tab2.layout.addWidget(self.board_control_table,0,0)
        self.table_tab2.setLayout(self.table_tab2.layout)
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



## Main function
## =============

if __name__ == '__main__':
    '''
    history_file = os.path.expanduser('.lvhv_history')
    if not os.path.exists(history_file):
        with open(history_file, "w") as fobj:
            fobj.write("")
    readline.read_history_file(history_file)
    atexit.register(readline.write_history_file, history_file)

    topdir = os.path.dirname(os.path.realpath(__file__))


    lvqueue = queue.Queue()
    hvqueue = queue.Queue()

    logging.basicConfig(filename='lvhvbox.log', format='%(asctime)s:%(levelname)s:%(message)s', encoding='utf-8', level=logging.DEBUG)

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
    '''

    '''
    lvhvbox = LVHVBox(app,ser1,ser2,hvlog,lvlog)

    lvThrd = threading.Thread(target=lvloop, daemon = True)
    lvThrd.start()

    #app.cmdloop()
    lvlog.close()
    hvlog.close()
    sys.exit()
    '''

    App = QApplication(sys.argv)
    window = Window()
    sys.exit(App.exec())
