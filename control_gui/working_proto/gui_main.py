# GUI/Monitoring Software for the LVHV Boxes
# Coded by Isaiah Wardlaw

import sys
import glob
import os
import json
import struct
import time
import threading
import readline
import asyncio

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.figure import *

import math
import rlcompleter
from pprint import pprint
import smbus
from smbus import SMBus
#import Adafruit_BBIO.GPIO as GPIO
import RPi.GPIO as GPIO
from RPiMCP23S17.MCP23S17 import MCP23S17
import random

# ensure that the window closes on control c
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

import wiringpi

# import c functions for lv
from ctypes import *


import os
import subprocess
import re

import logging

# initialize gui stuff

os.environ["DISPLAY"] = ':0'




background_color='background-color: white;'
button_color='background-color: white;'

# serial to acquire hv data
import serial

# session class focuses on interactions with the hardware, providing them to the gui class
class Session():


    def power_on(self,channel):
        channel=abs(channel-5)
        GPIO.output(self.GLOBAL_ENABLE_PIN,GPIO.HIGH)
        self.mcp1.digitalWrite(channel+8, MCP23S17.LEVEL_HIGH)

    def power_off(self,channel):
        channel=abs(channel-5)
        self.mcp1.digitalWrite(channel+8, MCP23S17.LEVEL_LOW)

    def initialize_lv(self,test):
        if not test:
            self.mcp1 = MCP23S17(bus=0x00, pin_cs=0x01, device_id=0x00)
            self.mcp1.open()
            self.mcp1._spi.max_speed_hz = 10000000

            for x in range(8, 16):
                self.mcp1.setDirection(x, self.mcp1.DIR_OUTPUT)
                self.mcp1.digitalWrite(x, MCP23S17.LEVEL_LOW)

            self.I2C_sleep_time = 0.25 # seconds to sleep between each channel reading
            self.bus = SMBus(1)

            # sleep to keep i2c from complaining
            time.sleep(1)

            # setup GPIO pins
            GPIO.setup(self.GLOBAL_ENABLE_PIN,GPIO.OUT)
            GPIO.setup(self.RESET_PIN,GPIO.OUT)
            GPIO.output(self.GLOBAL_ENABLE_PIN,GPIO.LOW)
            GPIO.output(self.RESET_PIN,GPIO.HIGH)

            if "libedit" in readline.__doc__:
                self.readline.parse_and_bind("bind ^I rl_complete")
        else:
            self.save_error("Error initializing low voltage connection.")

    # initializes connection with hv control
    def initialize_hv(self,test):
        if not test:
            self.rampup.initialization()
        else:
            self.save_error("Error initializing high voltage connection.")

    # called within a thread to actuate hv rampup
    def hv_rampup_on_off(self):
        self.is_ramping=True

        # depending on the "on" arg, actuate the hv channel
        if self.rampup_list[0][1] == True:
            self.rampup.rampup_hv(self.rampup_list[0][0],1500)
        else:
            self.rampup.rampup_hv(self.rampup_list[0][0],0)

        temp=[]
        for i in range(1,len(self.rampup_list)):
            temp.append(self.rampup_list[i])
        self.rampup_list=temp

        self.is_ramping=False

    def call_hv_data(self):
        try:

            hv_thread=threading.Thread(target=self.get_hv_data,args=[False])
            hv_thread.setDaemon(True)
            hv_thread.start()

        except:
            self.save_error("problem with call hv data")

    # acquires hv data from pico via pyserial connection
    def get_hv_data(self,test):
        # acquire hv current and voltage
        hv_voltage_1=[]
        hv_current_1=[]

        hv_voltage_2=[]
        hv_current_2=[]

        if not test:
            # make serial connection and close as soon as most recent line of data is acquired

            ser = serial.Serial('/dev/ttyACM0', 115200, timeout=2)
            line = ser.readline().decode('ascii')

            ser1 = serial.Serial('/dev/ttyACM1', 115200, timeout=2)
            line1 = ser1.readline().decode('ascii')

            # break apart the acquired pyserial output line and parse
            processed_line = line.split(" ")
            processed_line1 = line1.split(" ")

            # determine which pico is first
            picocheck1=line.split("|")[3][1]
            picocheck2=line1.split("|")[3][1]

            # get the hv overall current and temperature
            pico_add_1=line.split("|")[2][1:-2]
            pico_add_2=line1.split("|")[2][1:-2]

            on_voltage=False
            end=False
            for i in processed_line:
                if i != '' and i != '|' and on_voltage is False:
                    hv_current_1.append(float(i))
                elif i != '' and i != '|' and on_voltage is True and end is False:
                    hv_voltage_1.append(float(i))
                elif end is False and i == '|':
                    if on_voltage is False:
                        on_voltage = True
                    else:
                        end = True

            on_voltage=False
            end=False
            for i in processed_line1:
                if i != '' and i != '|' and on_voltage is False:
                    hv_current_2.append(float(i))
                elif i != '' and i != '|' and on_voltage is True and end is False:
                    hv_voltage_2.append(float(i))
                elif end is False and i == '|':
                    if on_voltage is False:
                        on_voltage = True
                    else:
                        end = True
            # based on picocheck results, form main hv lists
            if picocheck1 == '2':
                hv_voltage = hv_voltage_1 + hv_voltage_2
                hv_current = hv_current_1 + hv_current_2
                self.hv_board_temp=float(pico_add_1)
                self.hv_board_current=float(pico_add_2)
            else:
                hv_voltage = hv_voltage_2 + hv_voltage_1
                hv_current = hv_current_2 + hv_current_1
                self.hv_board_temp=float(pico_add_2)
                self.hv_board_current=float(pico_add_1)



            # returned lists are flipped
            hv_current.reverse()
            hv_voltage.reverse()

            # round hv voltage
            temp=[]
            for i in hv_voltage:
                temp.append(round(int(i),1))
            hv_voltage=temp

            print(len(hv_current))
            print(len(hv_voltage))

            assert len(hv_current) == 12
            assert len(hv_voltage) == 12
            # todo ensure proper length of hv current and voltage

            '''
            except:
                self.save_error("Error acquiring hv data")
            '''
        else:
            # if data acquisition function is in test mode, populate with bogus data for testing purposes
            for i in range(0,12):
                hv_voltage.append(round(random.uniform(1450,1550),3))
                hv_current.append(round(random.uniform(20,30),3))

        # save data lists for hv

        try:
            if len(hv_voltage) == 12 and len(hv_current) == 12:
                self.hv_voltage=hv_voltage
                self.hv_current=hv_current
        except:
            self.save_error("hv data is of improper length")

    # used to acquire assorted data from exelcys blade modules via I2C protocol
    def get_blade_data(self,test):
        # acquire Voltage
        #self.bus.pec=1
        try:
            voltage_values=[]
            if not test:
                for i in range(0,6):
                    time.sleep(self.I2C_sleep_time)
                    try:
                        self.bus.pec=1
                        # acquire the voltage measurement for each of the six blades
                        self.bus.write_byte_data(0x50,0x0,i+1)
                        reading=self.bus.read_i2c_block_data(0x50,0x8B,2)
                        value=float(reading[0]+256*reading[1])/256.

                        # append acquired voltage measurement to output list
                        voltage_values.append(round(value,3))
                        self.bus.pec=0
                    except:
                        self.bus.pec=0
                        self.save_error("Error acquiring blade voltage data on channel " + str(i))
            else:
                # for testing purposes, autopopulate with bogus data
                for i in range(0,6):
                    voltage_values.append(round(random.uniform(35,45),3))
                    # ensure delay between channel readings

            # acquire Current
            current_values=[]
            if not test:
                for i in range(0,6):
                    time.sleep(self.I2C_sleep_time)
                    try:
                        self.bus.pec=1
                        # acquire the current measurement for each of the six blades
                        self.bus.write_byte_data(0x50,0x0,i+1)
                        reading=self.bus.read_i2c_block_data(0x50,0x8C,2)
                        value=reading[0]+256*reading[1]
                        exponent=(value >> 11) & 0x1f
                        exponent=exponent-32
                        mantissa=value & 0x7ff
                        current=mantissa*2**exponent

                        # append acquired current measurement to output list
                        current_values.append(round(current,3))
                        self.bus.pec=0
                    except:
                        self.bus.pec=0
                        self.save_error("Error acquiring blade current data on channel " + str(i))
            else:
                # for testing purposes, autopopulate with bogus data
                for i in range(0,6):
                    current_values.append(round(random.uniform(10,15),3))
                    # ensure delay between channel readings

            # acquire Temperature
            temperature_values=[]
            if not test:
                for i in range(0,6):
                    time.sleep(self.I2C_sleep_time)
                    try:
                        self.bus.pec=1
                        # acquire the temperature measurement for each of the six blades
                        self.bus.write_byte_data(0x50,0x0,i+1)
                        reading=self.bus.read_i2c_block_data(0x50,0x8D,2)
                        value=reading[0]+256*reading[1]
                        exponent=(value >> 11) & 0x1f
                        mantissa = value & 0x7ff
                        temp=mantissa*2**exponent

                        # append acquired temperature measurement to output list
                        temperature_values.append(round(temp,3))
                        self.bus.pec=0
                    except:
                        self.bus.pec=0
                        self.save_error("Error acquiring blade temperature data on channel " + str(i))
            else:
                for i in range(0,6):
                    temperature_values.append(round(random.uniform(28,35),3))
                    # ensure delay between channel readings

            # save data lists for blades
            self.voltage=voltage_values
            self.current=current_values
            self.temperature=temperature_values
        except:
            self.save_error("Bus Busy")

    def get_lv_data(self,test):
        self.accessing_lv = True
        # call blade data initially
        try:
            self.get_blade_data(False)
        except:
            self.save_error("Error acquiring blade data inside get lv data.")

        # acquire readMon data
        five_voltage=[]
        five_current=[]
        cond_voltage=[]
        cond_current=[]
        # iterates through all six lv channels to acquire readMon data
        for channel in reversed(range(0,6)):
            try:
                address=self.addresses[int(channel/2)]
                ch=channel%2

                temp_vals=[]
                for index in range(4):
                    time.sleep(self.I2C_sleep_time)
                    channelLTC = (0b101<<5) + 4*ch + index
                    self.bus.write_byte(address, channelLTC)

                    time.sleep(self.I2C_sleep_time)
                    reading = self.bus.read_i2c_block_data(address, channelLTC, 3)

                    # convert I2C reading to legitimate data
                    val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                    volts = val*self.vref/self.max_reading

                    vvolts = volts / 0.01964
                    ivolts = volts / 0.4
                    v12volts = volts * 10

                    if (ch == 0):
                        if (index%2 == 0):
                            if ( index % 4 == 0):
                                temp_vals.append(round(vvolts,3))
                            else:
                                temp_vals.append(round(v12volts,3))
                        else:
                            temp_vals.append(round(ivolts,3))
                    else:
                        if (index%2 == 1):
                            if ( index % 4 == 3):
                                temp_vals.append(round(vvolts,3))
                            else:
                                temp_vals.append(round(v12volts,3))
                        else:
                            temp_vals.append(round(ivolts,3))

                if channel%2 == 0:
                    cond_voltage.append(temp_vals[0])
                    cond_current.append(temp_vals[1])
                    five_voltage.append(temp_vals[2])
                    five_current.append(temp_vals[3])
                else:
                    cond_voltage.append(temp_vals[3])
                    cond_current.append(temp_vals[2])
                    five_voltage.append(temp_vals[1])
                    five_current.append(temp_vals[0])
            except:
                self.save_error("Error acquiring board data on channel " + str(channel))

        # save data lists for board
        self.five_voltage=five_voltage
        self.five_current=five_current
        self.cond_voltage=cond_voltage
        self.cond_current=cond_current

        self.accessing_lv=False

    def save_txt(self):
        output=''
        for i in range(0,6):
            output+='ch'+str(i)
            output+=','+str(self.voltage[i])
            output+=','+str(self.current[i])
            output+=','+str(self.temperature[i])
            output+=','+str(self.five_voltage[i])
            output+=','+str(self.five_current[i])
            output+=','+str(self.cond_voltage[i])
            output+=','+str(self.cond_current[i])+','
        for i in range(0,12):
            output+='ch'+str(i)
            output+=','+str(self.hv_voltage[i])
            output+=','+str(self.hv_current[i])+','

        output+=str(self.hv_board_temp)+','
        output+=str(self.hv_board_current)+','

        output+=str(time.time())
        output+='\n'

        file1=open("/home/mu2e/LVHVBox/control_gui/working_proto/logfile.txt", "a")
        file1.write(output)
        file1.close()


        # also save data to the logfile
        output='lvhvbox1 '
        for i in range(0,6):
            output += 'ch' + str(i) + 'v: ' + str(self.voltage[i]) + ' '
            output += 'ch' + str(i) + 'c: ' + str(self.current[i]) + ' '
            output += 'ch' + str(i) + 't: ' + str(self.temperature[i]) + ' '
            output += 'ch' + str(i) + '5v: ' + str(self.five_voltage[i]) + ' '
            output += 'ch' + str(i) + '5c: ' + str(self.five_current[i]) + ' '
            output += 'ch' + str(i) + 'cv: ' + str(self.cond_voltage[i]) + ' '
            output += 'ch' + str(i) + 'cc: ' + str(self.cond_current[i]) + ' '
        for i in range(0,12):
            output += 'ch' + str(i) + 'hvv: ' + str(self.hv_voltage[i]) + ' '
            output += 'ch' + str(i) + 'hvc: ' + str(self.hv_current[i]) + ' '

        output += 'hvbt: ' + str(self.hv_board_temp) + ' '
        output += 'hvbc: ' + str(self.hv_board_current) + ' '
        output += 'timestamp: ' + str(time.time)


        logging.info(output)

    def save_error(self,text):
        file2=open("/home/mu2e/LVHVBox/control_gui/working_proto/error_logfile.txt","a")
        file2.write(text)
        file2.write(str(time.time()) + "\n")
        file2.close()

class Window(QMainWindow,Session):
    def __init__(self):
        super(Window,self).__init__()

        logging.basicConfig(level=logging.INFO, filename='../../../../../var/log/data.log')

        # initialize variables to store data
        self.initialize_data()

        # since it's a touch screen, the cursor is irritating
        self.setCursor(Qt.BlankCursor)

        self.setWindowTitle("LVHV GUI")
        self.setStyleSheet(background_color)

        # call function to set up the overall tab layout
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


        # adds tabs to the overall GUI
        self.tabs.addTab(self.tab1,"Tables")
        self.tabs.addTab(self.tab2,"LV Actuation")
        self.tabs.addTab(self.tab3,"HV Actuation")
        self.tabs.addTab(self.plotting,"Plots")
        self.plotting_tabs.addTab(self.tab4,"Blade Plots")
        self.plotting_tabs.addTab(self.tab5,"Board Plots")
        self.plotting_tabs.addTab(self.tab6,"HV Plots")
        self.plotting_tabs.addTab(self.tab7,"Blade Stability")
        self.plotting_tabs.addTab(self.tab8,"Board Stability")
        self.plotting_tabs.addTab(self.tab9,"HV Stability")
        self.plotting.layout.addWidget(self.plotting_tabs)
        self.plotting.setLayout(self.plotting.layout)

        # set title and place tab widget for pyqt
        self.setWindowTitle("LVHV GUI")
        self.setCentralWidget(self.tabs)

        self.show()

    def stability_blade_plotting_setup(self):
        self.tab7=QWidget()
        self.tab7.layout=QGridLayout()

        # set up the blade plot
        self.stability_blade_plot=Figure()
        self.stability_blade_plot_canvas=FigureCanvas(self.stability_blade_plot)
        self.stability_blade_plot_axes=self.stability_blade_plot.add_subplot(111)

        self.stability_blade_plot_axes.set_xlim([0,48])
        self.stability_blade_plot_axes.set_ylim([0,60])
        self.stability_blade_plot_axes.set_title('Channel 0 Blade Voltage')
        self.stability_blade_plot_axes.set_ylabel('Voltage (V)')
        self.stability_blade_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + str(round(self.save_time/60000,1)) + ' minutes.')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.stability_blade_plot_data_x=[*range(0,48,1)]
        self.stability_blade_plot_data=self.stability_blade_plot_axes.plot(self.stability_blade_plot_data_x,self.stability_blade_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.stability_blade_channel_selector=QComboBox()
        self.stability_blade_channel_selector.addItems(["Channel 0","Channel 1","Channel 2","Channel 3","Channel 4","Channel 5"])
        self.stability_blade_channel_selector.setStyleSheet(button_color)
        self.stability_blade_channel_selector.currentIndexChanged.connect(self.change_stability_blade_plot)

        self.stability_blade_measurement_selector=QComboBox()
        self.stability_blade_measurement_selector.addItems(["Voltage","Current","Temperature"])
        self.stability_blade_measurement_selector.setStyleSheet(button_color)
        self.stability_blade_measurement_selector.currentIndexChanged.connect(self.change_stability_blade_plot)

        # add widgets and set layout
        self.tab7.layout.addWidget(self.stability_blade_channel_selector,0,0)
        self.tab7.layout.addWidget(self.stability_blade_measurement_selector,1,0)
        self.tab7.layout.addWidget(self.stability_blade_plot_canvas,0,1)
        self.tab7.setLayout(self.tab7.layout)

    def stability_board_plotting_setup(self):
        self.tab8=QWidget()
        self.tab8.layout=QGridLayout()

        # setup the board plot
        self.stability_board_plot=Figure()
        self.stability_board_plot_canvas=FigureCanvas(self.stability_board_plot)
        self.stability_board_plot_axes=self.stability_board_plot.add_subplot(111)

        self.stability_board_plot_axes.set_xlim([0,48])
        self.stability_board_plot_axes.set_ylim([0,60])
        self.stability_board_plot_axes.set_title('Channel 0 5V Voltage')
        self.stability_board_plot_axes.set_ylabel('Voltage (V)')
        self.stability_board_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + str(round(self.save_time/60000,1)) + ' minutes.')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.stability_board_plot_data_x=[*range(0,48,1)]
        self.stability_board_plot_data=self.stability_board_plot_axes.plot(self.stability_board_plot_data_x,self.stability_board_5v_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.stability_board_channel_selector=QComboBox()
        self.stability_board_channel_selector.addItems(["Channel 0","Channel 1","Channel 2","Channel 3","Channel 4","Channel 5"])
        self.stability_board_channel_selector.setStyleSheet(button_color)
        self.stability_board_channel_selector.currentIndexChanged.connect(self.change_stability_board_plot)

        self.stability_board_measurement_selector=QComboBox()
        self.stability_board_measurement_selector.addItems(["5V Voltage","5V Current","Conditioned Voltage","Conditioned Current"])
        self.stability_board_measurement_selector.setStyleSheet(button_color)
        self.stability_board_measurement_selector.currentIndexChanged.connect(self.change_stability_board_plot)

        # add widgets and set layout
        self.tab8.layout.addWidget(self.stability_board_channel_selector,0,0)
        self.tab8.layout.addWidget(self.stability_board_measurement_selector,1,0)
        self.tab8.layout.addWidget(self.stability_board_plot_canvas,0,1)
        self.tab8.setLayout(self.tab8.layout)

    def stability_hv_plotting_setup(self):
        self.tab9=QWidget()
        self.tab9.layout=QGridLayout()

        # setup the hv plot
        self.stability_hv_plot=Figure()
        self.stability_hv_plot_canvas=FigureCanvas(self.stability_hv_plot)
        self.stability_hv_plot_axes=self.stability_hv_plot.add_subplot(111)

        self.stability_hv_plot_axes.set_xlim([0,48])
        self.stability_hv_plot_axes.set_ylim([0,1600])
        self.stability_hv_plot_axes.set_title('Channel 0 HV Voltage')
        self.stability_hv_plot_axes.set_ylabel('Voltage (V)')
        self.stability_hv_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + str(round(self.save_time/60000,1)) + ' minutes.')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.stability_hv_plot_data_x=[*range(0,48,1)]
        self.stability_hv_plot_data=self.stability_hv_plot_axes.plot(self.stability_hv_plot_data_x,self.stability_hv_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.stability_hv_channel_selector=QComboBox()
        self.stability_hv_channel_selector.addItems(["Channel 0","Channel 1","Channel 2","Channel 3","Channel 4","Channel 5",
        "Channel 6","Channel 7","Channel 8","Channel 9","Channel 10","Channel 11"])
        self.stability_hv_channel_selector.setStyleSheet(button_color)
        self.stability_hv_channel_selector.currentIndexChanged.connect(self.change_stability_hv_plot)

        self.stability_hv_measurement_selector=QComboBox()
        self.stability_hv_measurement_selector.addItems(["Voltage","Current"])
        self.stability_hv_measurement_selector.setStyleSheet(button_color)
        self.stability_hv_measurement_selector.currentIndexChanged.connect(self.change_stability_hv_plot)

        # add widgets and set layout
        self.tab9.layout.addWidget(self.stability_hv_channel_selector,0,0)
        self.tab9.layout.addWidget(self.stability_hv_measurement_selector,1,0)
        self.tab9.layout.addWidget(self.stability_hv_plot_canvas,0,1)
        self.tab9.setLayout(self.tab9.layout)

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
        self.blade_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + str(round(self.board_time/60000,1)) + ' minutes.')

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
        self.board_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + str(round(self.board_time/60000,1)) + ' minutes.')

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
        self.hv_plot_axes.set_xlabel('Iterative Age of Datapoint: each iteration is ' + str(round(self.board_time/60000,1)) + ' minutes.')

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
        self.blade_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

        # setup board table
        self.board_control_table=QTableWidget()
        self.board_control_table.setRowCount(6)
        self.board_control_table.setColumnCount(4)
        self.board_control_table.setFixedWidth(550)
        self.board_control_table.setDisabled(True)

        self.board_control_table.setHorizontalHeaderLabels(["5V Voltage (V)","5V Current (A)","Cond Voltage (V)","Cond Current (A)"])
        self.board_control_table.setVerticalHeaderLabels(["Ch 0","Ch 1","Ch 2","Ch 3","Ch 4","Ch 5"])
        self.board_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

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

    # called when one of the lv power buttons is pressed
    def actuate_lv_power(self,number):
        indicators=[self.lv_power_button_1,self.lv_power_button_2,self.lv_power_button_3,self.lv_power_button_4,
        self.lv_power_button_5,self.lv_power_button_6]

        if self.blade_power[number]==True:
            indicators[number].setStyleSheet('background-color: red')
            self.blade_power[number]=False
            self.power_off(number)
        else:
            indicators[number].setStyleSheet('background-color: green')
            self.blade_power[number]=True
            self.power_on(number)



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
                self.rampup_list.append([number,False])

        else:
            indicators[number].setStyleSheet('background-color: green')
            self.hv_power[number]=True

            # if gui isn't in test mode, power up hv channel
            if self.test is False:
                # use threading to ensure that the gui doesn't freeze during rampup
                self.rampup_list.append([number,True])

    # updates the blade table with recent data
    def update_blade_table(self):
        for j in range(6):
            self.blade_voltage_entries[j].setText(str(self.voltage[j]))
            self.blade_current_entries[j].setText(str(self.current[j]))
            self.blade_temperature_entries[j].setText(str(self.temperature[j]))

    # updates the board table with recent data (readmon data)
    def update_board_table(self):
        for j in range(6):
            self.board_5v_voltage_entries[j].setText(str(self.five_voltage[j]))
            self.board_5v_current_entries[j].setText(str(self.five_current[j]))
            self.board_cond_voltage_entries[j].setText(str(self.cond_voltage[j]))
            self.board_cond_current_entries[j].setText(str(self.cond_current[j]))

    # updates the hv bars to display current hv rampup level
    # converts the number to a percent progress
    def update_hv_bars(self):
        percent_progress=[]
        for i in range(12):
            temp=int(self.hv_voltage[i]/15)
            if temp > 100:
                temp=100
            percent_progress.append(temp)

        self.hv_bar_1.setValue(percent_progress[0])
        self.hv_bar_2.setValue(percent_progress[1])
        self.hv_bar_3.setValue(percent_progress[2])
        self.hv_bar_4.setValue(percent_progress[3])
        self.hv_bar_5.setValue(percent_progress[4])
        self.hv_bar_6.setValue(percent_progress[5])
        self.hv_bar_7.setValue(percent_progress[6])
        self.hv_bar_8.setValue(percent_progress[7])
        self.hv_bar_9.setValue(percent_progress[8])
        self.hv_bar_10.setValue(percent_progress[9])
        self.hv_bar_11.setValue(percent_progress[10])
        self.hv_bar_12.setValue(percent_progress[11])

    # updates the hv table with latest available data
    def update_hv_table(self):
        for j in range(12):
            self.hv_voltage_entries[j].setText(str(self.hv_voltage[j]))
            self.hv_current_entries[j].setText(str(self.hv_current[j]))

    # acquires the channel being measured
    def get_blade_channel(self):
        # determine which blade data is to be plotted for
        channels={"Channel 0": 0,"Channel 1": 1,"Channel 2": 2,"Channel 3": 3,"Channel 4": 4,"Channel 5": 5}
        channel=channels[self.blade_channel_selector.currentText()]
        return channel

    # returns the proper board channel number, based on the current user selection
    def get_board_channel(self):
        # determine which blade data is to be plotted for
        channels={"Channel 0": 0,"Channel 1": 1,"Channel 2": 2,"Channel 3": 3,"Channel 4": 4,"Channel 5": 5}
        channel=channels[self.board_channel_selector.currentText()]
        return channel

    # returns the proper hv channel number, based on the current user selection
    def get_hv_channel(self):
        # determine which hv channel data is to be plotted for
        channels={"Channel 0": 0,"Channel 1": 1,"Channel 2": 2,"Channel 3": 3,"Channel 4": 4,
        "Channel 5": 5,"Channel 6": 6,"Channel 7": 7,"Channel 8": 8,"Channel 9": 9,
        "Channel 10": 10,"Channel 11": 11}
        channel=channels[self.hv_channel_selector.currentText()]
        return channel

    # acquires the channel being measured
    def get_stability_blade_channel(self):
        # determine which blade data is to be plotted for
        channels={"Channel 0": 0,"Channel 1": 1,"Channel 2": 2,"Channel 3": 3,"Channel 4": 4,"Channel 5": 5}
        channel=channels[self.stability_blade_channel_selector.currentText()]
        return channel

    # returns the proper board channel number, based on the current user selection
    def get_stability_board_channel(self):
        # determine which blade data is to be plotted for
        channels={"Channel 0": 0,"Channel 1": 1,"Channel 2": 2,"Channel 3": 3,"Channel 4": 4,"Channel 5": 5}
        channel=channels[self.stability_board_channel_selector.currentText()]
        return channel

    # returns the proper hv channel number, based on the current user selection
    def get_stability_hv_channel(self):
        # determine which hv channel data is to be plotted for
        channels={"Channel 0": 0,"Channel 1": 1,"Channel 2": 2,"Channel 3": 3,"Channel 4": 4,
        "Channel 5": 5,"Channel 6": 6,"Channel 7": 7,"Channel 8": 8,"Channel 9": 9,
        "Channel 10": 10,"Channel 11": 11}
        channel=channels[self.stability_hv_channel_selector.currentText()]
        return channel

    def change_stability_blade_plot(self):
        channel=self.get_stability_blade_channel()
        type=self.stability_blade_measurement_selector.currentText()

        # update labels for the blade plot
        self.stability_blade_plot_axes.set_title(self.stability_blade_channel_selector.currentText() + ' Blade ' + type)
        if type=="Voltage":
            self.stability_blade_plot_axes.set_ylabel('Voltage (V)')
        elif type=="Current":
            self.stability_blade_plot_axes.set_ylabel('Current (A)')
        else:
            self.stability_blade_plot_axes.set_ylabel('Temperature (C)')

        # ensure that the proper type of data is plotted
        if type=="Voltage":
            self.stability_blade_plot_data.set_ydata(self.stability_blade_voltage_plot[channel])
        elif type=="Current":
            self.stability_blade_plot_data.set_ydata(self.stability_blade_current_plot[channel])
        else:
            self.stability_blade_plot_data.set_ydata(self.stability_blade_temperature_plot[channel])

        # update the plot
        self.stability_blade_plot_canvas.draw()
        self.stability_blade_plot_canvas.flush_events()

    # called to change the hv plot
    # this function is only used when the TYPE of data that is being plotted changes, as per user input
    def change_stability_hv_plot(self):
        channel=self.get_stability_hv_channel()
        type=self.stability_hv_measurement_selector.currentText()

        # update labels for the hv plot
        self.stability_hv_plot_axes.set_title(self.stability_hv_channel_selector.currentText() + ' HV ' + type)
        if type=="Voltage":
            self.stability_hv_plot_axes.set_ylabel('Voltage (V)')
            self.stability_hv_plot_axes.set_ylim([0,1600])
        else:
            self.stability_hv_plot_axes.set_ylabel('Current (A)')
            self.stability_hv_plot_axes.set_ylim([0,100])

        # ensure that the proper type of data is being plotted
        if type=="Voltage":
            self.stability_hv_plot_data.set_ydata(self.stability_hv_voltage_plot[channel])
        else:
            self.stability_hv_plot_data.set_ydata(self.stability_hv_current_plot[channel])

        # update the plot
        self.stability_hv_plot_canvas.draw()
        self.stability_hv_plot_canvas.flush_events()

    # called to change the board plot (readmon data)
    # this function is only used when the TYPE of data that is being plotted changes, as per user input
    def change_stability_board_plot(self):
        channel=self.get_stability_board_channel()
        type=self.stability_board_measurement_selector.currentText()

        # update labels for the board plot
        self.stability_board_plot_axes.set_title(self.stability_board_channel_selector.currentText() + ' Board ' + type)
        if type=="5V Voltage":
            self.stability_board_plot_axes.set_ylabel('5V Voltage (V)')
        elif type=="5V Current":
            self.stability_board_plot_axes.set_ylabel('5V Current (A)')
        elif type=="Conditioned Voltage":
            self.stability_board_plot_axes.set_ylabel('Conditioned Voltage (V)')
        else:
            self.stability_board_plot_axes.set_ylabel('Conditioned Current (A)')

        # update the data, according to what is being plotted
        if type=="5V Voltage":
            self.stability_board_plot_data.set_ydata(self.stability_board_5v_voltage_plot[channel])
        elif type=="5V Current":
            self.stability_board_plot_data.set_ydata(self.stability_board_5v_current_plot[channel])
        elif type=="Conditioned Voltage":
            self.stability_board_plot_data.set_ydata(self.stability_board_cond_voltage_plot[channel])
        else:
            self.stability_board_plot_data.set_ydata(self.stability_board_cond_current_plot[channel])

        # actually update the plot
        self.stability_board_plot_canvas.draw()
        self.stability_board_plot_canvas.flush_events()

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

    # called by the timer to update the main plot with new data
    def update_stability_blade_plot(self):
        channel=self.get_blade_channel()
        type=self.stability_blade_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.stability_blade_voltage_plot)):
            self.stability_blade_voltage_plot[i]=[self.voltage[i]]+self.stability_blade_voltage_plot[i][:-1]
            self.stability_blade_current_plot[i]=[self.current[i]]+self.stability_blade_current_plot[i][:-1]
            self.stability_blade_temperature_plot[i]=[self.temperature[i]]+self.stability_blade_temperature_plot[i][:-1]

        # determine what kind of data is being plotted, and respond accordingly
        if type=="Voltage":
            self.stability_blade_plot_data.set_ydata(self.stability_blade_voltage_plot[channel])
        elif type=="Current":
            self.stability_blade_plot_data.set_ydata(self.stability_blade_current_plot[channel])
        else:
            self.stability_blade_plot_data.set_ydata(self.stability_blade_temperature_plot[channel])

        # update the plot
        self.stability_blade_plot_canvas.draw()
        self.stability_blade_plot_canvas.flush_events()

    # this function updates the board plot (readmon data)
    def update_stability_board_plot(self):
        channel=self.get_board_channel()
        type=self.stability_board_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.stability_board_5v_voltage_plot)):
            self.stability_board_5v_voltage_plot[i]=[self.five_voltage[i]]+self.stability_board_5v_voltage_plot[i][:-1]
            self.stability_board_5v_current_plot[i]=[self.five_current[i]]+self.stability_board_5v_current_plot[i][:-1]
            self.stability_board_cond_voltage_plot[i]=[self.cond_voltage[i]]+self.stability_board_cond_voltage_plot[i][:-1]
            self.stability_board_cond_current_plot[i]=[self.cond_current[i]]+self.board_cond_current_plot[i][:-1]

        # determine which type of data is currently being plotted, and set data accordingly
        if type=="5V Voltage":
            self.stability_board_plot_data.set_ydata(self.stability_board_5v_voltage_plot[channel])
        elif type=="5V Current":
            self.stability_board_plot_data.set_ydata(self.stability_board_5v_current_plot[channel])
        elif type=="Conditioned Voltage":
            self.stability_board_plot_data.set_ydata(self.stability_board_cond_voltage_plot[channel])
        else:
            self.stability_board_plot_data.set_ydata(self.stability_board_cond_current_plot[channel])

        # actually update the plot
        self.stability_board_plot_canvas.draw()
        self.stability_board_plot_canvas.flush_events()

    # this function updates the hv plot
    def update_stability_hv_plot(self):
        channel=self.get_hv_channel()
        type=self.stability_hv_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.stability_hv_voltage_plot)):
            self.stability_hv_voltage_plot[i]=[self.hv_voltage[i]]+self.stability_hv_voltage_plot[i][:-1]
            self.stability_hv_current_plot[i]=[self.hv_current[i]]+self.stability_hv_current_plot[i][:-1]

        if type=="Voltage":
            self.stability_hv_plot_data.set_ydata(self.stability_hv_voltage_plot[channel])
        else:
            self.stability_hv_plot_data.set_ydata(self.stability_hv_current_plot[channel])
        self.stability_hv_plot_canvas.draw()
        self.stability_hv_plot_canvas.flush_events()

    # called by the timer to update the main plot with new data
    def update_blade_plot(self):
        channel=self.get_blade_channel()
        type=self.blade_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.blade_voltage_plot)):
            self.blade_voltage_plot[i]=[self.voltage[i]]+self.blade_voltage_plot[i][:-1]
            self.blade_current_plot[i]=[self.current[i]]+self.blade_current_plot[i][:-1]
            self.blade_temperature_plot[i]=[self.temperature[i]]+self.blade_temperature_plot[i][:-1]

        # determine what kind of data is being plotted, and respond accordingly
        if type=="Voltage":
            self.blade_plot_data.set_ydata(self.blade_voltage_plot[channel])
        elif type=="Current":
            self.blade_plot_data.set_ydata(self.blade_current_plot[channel])
        else:
            self.blade_plot_data.set_ydata(self.blade_temperature_plot[channel])

        # update the plot
        self.blade_plot_canvas.draw()
        self.blade_plot_canvas.flush_events()

    # this function updates the board plot (readmon data)
    def update_board_plot(self):
        channel=self.get_board_channel()
        type=self.board_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.board_5v_voltage_plot)):
            self.board_5v_voltage_plot[i]=[self.five_voltage[i]]+self.board_5v_voltage_plot[i][:-1]
            self.board_5v_current_plot[i]=[self.five_current[i]]+self.board_5v_current_plot[i][:-1]
            self.board_cond_voltage_plot[i]=[self.cond_voltage[i]]+self.board_cond_voltage_plot[i][:-1]
            self.board_cond_current_plot[i]=[self.cond_current[i]]+self.board_cond_current_plot[i][:-1]

        # determine which type of data is currently being plotted, and set data accordingly
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

    # this function updates the hv plot
    def update_hv_plot(self):
        channel=self.get_hv_channel()
        type=self.hv_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.hv_voltage_plot)):
            self.hv_voltage_plot[i]=[self.hv_voltage[i]]+self.hv_voltage_plot[i][:-1]
            self.hv_current_plot[i]=[self.hv_current[i]]+self.hv_current_plot[i][:-1]

        if type=="Voltage":
            self.hv_plot_data.set_ydata(self.hv_voltage_plot[channel])
        else:
            self.hv_plot_data.set_ydata(self.hv_current_plot[channel])
        self.hv_plot_canvas.draw()
        self.hv_plot_canvas.flush_events()

    def call_lv_data(self):
        try:
            if not self.accessing_lv:
                threading.Thread(target=self.get_lv_data,args=[False]).start()
        except:
            self.save_error("Error calling lv data")

    # this function updates all of the plots, as well as everything that has to do with readmon data
    # because readmon also takes the longest, this update function saves data to logfile.txt
    def primary_update(self):
        if self.initial_lv_display == False:
            try:
                self.update_board_table()
            except:
                self.save_error("Error with update board table.")
            try:
                self.update_blade_table()
            except:
                self.save_error("Error with update blade table.")
            try:
                self.update_blade_plot()
            except:
                self.save_error("Error with update blade plot.")
            try:
                self.update_board_plot()
            except:
                self.save_error("Error with update board plot.")
            try:
                self.update_hv_plot()
            except:
                self.save_error("Error with update hv plot.")
        else:
            self.initial_lv_display = True

    def stability_save(self):
        try:
            self.update_stability_blade_plot()
        except:
            self.save_error("Error with the stability blade plot update.")
        try:
            self.update_stability_board_plot()
        except:
            self.save_error("Error with the stability board plot update.")
        try:
            self.update_stability_hv_plot()
        except:
            self.save_error("Error with the stability hv plot update.")
        try:
            self.save_txt()
        except:
            self.save_error("Error saving the txt.")

    # updates the hv table and hv rampup status bars
    def hv_update(self):
        self.update_hv_table()
        self.update_hv_bars()

        # if applicable, call function to rampup/rampdown next item in hv queue
        if self.is_ramping == False and len(self.rampup_list) != 0:
            threading.Thread(target=self.hv_rampup_on_off).start()

    def initialize_data(self):
        # set vars to control timers
        self.board_time=20000
        self.hv_time=2500
        self.save_time=60000
        self.hv_display_time=2000

        self.max_reading = 8388608.0
        self.vref = 3.3
        self.pins = ["P9_15","P9_15","P9_15","P9_27","P9_41","P9_12"]
        self.GLOBAL_ENABLE_PIN =  15
        self.RESET_PIN = 32
        self.addresses = [0x14,0x16,0x26]

        # set vars to track hardware connections in threads
        self.acquiring_hv = False
        self.accessing_lv = False
        self.hv_lock_time=time.time()
        self.hv_threadlist=[]

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

    def run(self):
        try:
            # initialize timers required to update gui/get and log data
            self.lv_timer = QTimer(self)
            self.lv_timer.setSingleShot(False)
            self.hv_timer = QTimer(self)
            self.hv_timer.setSingleShot(False)
            self.stability_timer=QTimer(self)
            self.stability_timer.setSingleShot(False)
            self.hv_display_timer=QTimer(self)
            self.hv_display_timer.setSingleShot(False)

            # readMon update timer
            self.lv_timer.timeout.connect(self.call_lv_data)
            self.lv_timer.timeout.connect(self.primary_update)
            self.lv_timer.start(self.board_time)

            # hv update timer
            self.hv_timer.timeout.connect(lambda:self.call_hv_data())
            self.hv_timer.start(self.hv_time)

            # update hv table and bars
            self.hv_display_timer.timeout.connect(self.hv_update)
            self.hv_display_timer.start(self.hv_display_time)

            # call save function and update stability_plots
            self.stability_timer.timeout.connect(self.stability_save)
            self.stability_timer.start(self.save_time)
        except:
            self.save_error("problem with main run call")


if __name__=="__main__":
    try:
        # create pyqt5 app
        App = QApplication(sys.argv)

        # create the instance of our Window
        window = Window()

        # run the lv initialization function
        # for whatever ungodly reason, it sometimes needs to be run more than once to properly work
        # TODO FIX
        try:
            window.initialize_lv(False)
            window.initialize_lv(False)
            window.initialize_lv(False)
        except:
            window.save_error("Error initializing LV in main")

        # import c functions for hv
        rampup = "/home/mu2e/LVHVBox/control_gui/working_proto/python_connect.so"
        window.rampup=CDLL(rampup)
        window.test = False

        # run the hv initialization program
        try:
            window.initialize_hv(False)
        except:
            window.save_error("Error intializing HV in main")

        try:
            window.run()
        except:
            window.save_error("Error running window in main")

        # start the app
        sys.exit(App.exec())

    except KeyboardInterrupt:
        stored_exception=sys.exc_info()
    except Exception as e:
        window.save_error("-- EXCEPTION as e --")
