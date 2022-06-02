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
from grafana_api.grafana_face import GrafanaFace

# ensure that the window closes on control c
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)


os.environ["DISPLAY"] = ':0'
background_color='background-color: white;'
button_color='background-color: white;'

# serial to acquire hv data
import serial


class Session():
    def __init__(self):
        self.voltage=None
        self.current=None
        self.temperature=None

    def power_on(self,test):
        GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
        if not test:
            for ich in range(0,12):
                mcp1.digitalWrite(ich+8, MCP23S17.LEVEL_LOW)
                print("Channel " + str(ich) + " enabled")
        else:
            print("Testing Mode Enabled")

    def power_off(self,test):
        GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
        if not test:
            for ich in range(0,12):
                mcp1.digitalWrite(ich+8, MCP23S17.LEVEL_LOW)
                print("Channel " + str(ich) + "disabled")
        else:
            print("Testing Mode Exited")

    def initialize_lv(self,test):
        if not test:
            self.mcp1 = MCP23S17(bus=0x00, pin_cs=0x00, device_id=0x00)

            self.mcp1.open()
            self.mcp1._spi.max_speed_hz = 10000000

            for x in range(8, 16):
                self.mcp1.setDirection(x, mcp1.DIR_OUTPUT)
                self.mcp1.digitalWrite(x, MCP23S17.LEVEL_LOW)

            self.I2C_sleep_time = 0.2 # seconds to sleep between each channel reading
            self.bus = SMBus(1)

            self.max_reading = 8388608.0
            self.vref = 2.048

            self.pins = ["P9_15","P9_15","P9_15","P9_27","P9_41","P9_12"]
            self.GLOBAL_ENABLE_PIN =  15
            self.RESET_PIN = 32

            if "libedit" in readline.__doc__:
                self.readline.parse_and_bind("bind ^I rl_complete")
        else:
            pass

    def get_data(self,test):

        # acquire Voltage
        voltage_values=[]
        if not test:
            """
            for i in range(0,6):
                # acquire the voltage measurement for each of the six blades
                self.bus.write_byte_data(0x50,0x0,i+1)
                reading=self.bus.read_byte_data(0x50,0xD0)
                value=float(reading[0]+256*reading[1])/256.

                # append acquired voltage measurement to output list
                voltage_values.append(round(value,3))
            """
            for i in range(0,6):
                voltage_values.append(round(random.uniform(35,45),3))
        else:
            for i in range(0,6):
                voltage_values.append(round(random.uniform(35,45),3))
                # ensure delay between channel readings

        # acquire Current
        current_values=[]
        if not test:
            """
            for i in range(0,6):
                # acquire the current measurement for each of the six blades
                self.bus.write_byte_data(0x50,0x0,i+1)
                reading=self.bus.read_byte_data(0x50,0xD0)
                reading=self.bus.read_i2c_block_data(0x50,0x8C,2)
                value=reading[0]+256*reading[1]
                exponent=(value >> 11) & 0x1f
                exponent=exponent-32
                mantissa=value & 0x7ff
                current=mantissa*2**exponent

                # append acquired current measurement to output list
                current_values.append(round(current,3))
            """
            for i in range(0,6):
                current_values.append(round(random.uniform(10,15),3))
        else:
            for i in range(0,6):
                current_values.append(round(random.uniform(10,15),3))
                # ensure delay between channel readings

        # acquire Temperature
        temperature_values=[]
        if not test:
            """
            for i in range(0,6):
                # acquire the temperature measurement for each of the six blades
                self.bus.write_byte_data(0x50,0x0,i+1)
                reading=self.bus.read_byte_data(0x50,0xD0)
                reading=self.bus.read_i2c_block_data(0x50,0x8D,2)
                value-reading[0]+256*reading[1]
                exponent=(value >> 11) & 0x1f
                temp=mantissa*2**exponent

                # append acquired temperature measurement to output list
                temperature_values.append(round(temp,3))
            """
            for i in range(0,6):
                temperature_values.append(round(random.uniform(28,35),3))
        else:
            for i in range(0,6):
                temperature_values.append(round(random.uniform(28,35),3))
                # ensure delay between channel readings

        # acquire 5v voltage
        five_voltage=[]
        if not test:
            for i in range(0,6):
                five_voltage.append(round(random.uniform(45,52),3))
        else:
            for i in range(0,6):
                five_voltage.append(round(random.uniform(45,52),3))

        # acquire 5v current
        five_current=[]
        if not test:
            for i in range(0,6):
                five_current.append(round(random.uniform(10,20),3))
        else:
            for i in range(0,6):
                five_current.append(round(random.uniform(10,20),3))

        # acquire conditioned voltage
        cond_voltage=[]
        if not test:
            for i in range(0,6):
                cond_voltage.append(round(random.uniform(45,52),3))
        else:
            for i in range(0,6):
                cond_voltage.append(round(random.uniform(45,52),3))

        # acquire conditioned current
        cond_current=[]
        if not test:
            for i in range(0,6):
                cond_current.append(round(random.uniform(10,20),3))
        else:
            for i in range(0,6):
                cond_current.append(round(random.uniform(10,20),3))


        # acquire hv current and voltage
        hv_current=[]
        hv_voltage=[]
        if not test:
            try:
                ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
                line = ser.readline().decode('ascii')

                processed_line = line.split(" ")

                on_voltage=False
                end=False
                for i in processed_line:
                    if i != '' and i != '|' and on_voltage is False:
                        hv_current.append(float(i))
                    elif i != '' and i != '|' and on_voltage is True and end is False:
                        hv_voltage.append(float(i))
                    elif end is False and i == '|':
                        if on_voltage is False:
                            on_voltage = True
                        else:
                            end = True

                # temporary measure because only one pico is connected
                hv_current=hv_current+hv_current
                hv_voltage=hv_voltage+hv_voltage

                assert len(hv_current) == 12
                assert len(hv_voltage) == 12
                # todo ensure proper length of hv current and voltage

            except:
                print("improper communication")
                return False
        else:
            for i in range(0,12):
                hv_voltage.append(round(random.uniform(1450,1550),3))
                hv_current.append(round(random.uniform(20,30),3))

        # save data lists for blades
        self.voltage=voltage_values
        self.current=current_values
        self.temperature=temperature_values

        # save data lists for board
        self.five_voltage=five_voltage
        self.five_current=five_current
        self.cond_voltage=cond_voltage
        self.cond_current=cond_current

        # save data lists for hv
        self.hv_voltage=hv_voltage
        self.hv_current=hv_current

        return True

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
            output+=','+str(self.cond_current[i])
        output+=','+str(time.time())
        output+='\n'

        file1=open("logfile.txt", "a")
        file1.write(output)
        file1.close()

class Window(QMainWindow,Session):
    def __init__(self):
        super(Window,self).__init__()
        self.initialize_data()
        # since it's a touch screen, the cursor is irritating
        self.setCursor(Qt.BlankCursor)

        self.setWindowTitle("LVHV GUI")

        self.setStyleSheet(background_color)

        # call function to set up the overall tab layout
        self.tabs()

        self.showFullScreen()

    def tabs(self):
        self.tabs=QTabWidget()

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

        # initialize diagnostics Window
        self.diagnostics_setup()

        self.tabs.addTab(self.tab1,"Tables")
        self.tabs.addTab(self.tab2,"LV Controls")
        self.tabs.addTab(self.tab3,"HV Controls")
        self.tabs.addTab(self.tab4,"Raw Blade Plots")
        self.tabs.addTab(self.tab5,"Board Plots")
        self.tabs.addTab(self.tab6,"HV Plots")
        self.tabs.addTab(self.tab7,"Diagnostics")

        self.setWindowTitle("LVHV GUI")
        self.setCentralWidget(self.tabs)

        self.show()


    def blade_plotting_setup(self):
        self.tab4=QWidget()
        self.tab4.layout=QGridLayout()

        # set up the blade plot
        self.blade_plot=Figure()
        self.blade_plot_canvas=FigureCanvas(self.blade_plot)
        self.blade_plot_axes=self.blade_plot.add_subplot(111)

        self.blade_plot_axes.set_xlim([0,50])
        self.blade_plot_axes.set_ylim([0,100])
        self.blade_plot_axes.set_title('Channel 1 Blade Voltage')
        self.blade_plot_axes.set_ylabel('Voltage (V)')
        self.blade_plot_axes.set_xlabel('Iterative Age of Datapoint')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.blade_plot_data_x=[*range(0,50,1)]
        self.blade_plot_data=self.blade_plot_axes.plot(self.blade_plot_data_x,self.blade_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.blade_channel_selector=QComboBox()
        self.blade_channel_selector.addItems(["Channel 1","Channel 2","Channel 3","Channel 4","Channel 5","Channel 6"])
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

    def board_plotting_setup(self):
        self.tab5=QWidget()
        self.tab5.layout=QGridLayout()

        # setup the board plot
        self.board_plot=Figure()
        self.board_plot_canvas=FigureCanvas(self.board_plot)
        self.board_plot_axes=self.board_plot.add_subplot(111)

        self.board_plot_axes.set_xlim([0,50])
        self.board_plot_axes.set_ylim([0,100])
        self.board_plot_axes.set_title('Channel 1 5V Voltage')
        self.board_plot_axes.set_ylabel('Voltage (V)')
        self.board_plot_axes.set_xlabel('Iterative Age of Datapoint')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.board_plot_data_x=[*range(0,50,1)]
        self.board_plot_data=self.board_plot_axes.plot(self.board_plot_data_x,self.board_5v_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.board_channel_selector=QComboBox()
        self.board_channel_selector.addItems(["Channel 1","Channel 2","Channel 3","Channel 4","Channel 5","Channel 6"])
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

    def hv_plotting_setup(self):
        self.tab6=QWidget()
        self.tab6.layout=QGridLayout()

        # setup the hv plot
        self.hv_plot=Figure()
        self.hv_plot_canvas=FigureCanvas(self.hv_plot)
        self.hv_plot_axes=self.hv_plot.add_subplot(111)

        self.hv_plot_axes.set_xlim([0,50])
        self.hv_plot_axes.set_ylim([1000,2000])
        self.hv_plot_axes.set_title('Channel 1 HV Voltage')
        self.hv_plot_axes.set_ylabel('Voltage (V)')
        self.hv_plot_axes.set_xlabel('Iterative Age of Datapoint')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.hv_plot_data_x=[*range(0,50,1)]
        self.hv_plot_data=self.hv_plot_axes.plot(self.hv_plot_data_x,self.hv_voltage_plot[0],marker='o',linestyle='None',markersize=2,color='k')[0]

        # add dropdown menus to select what's plotted
        self.hv_channel_selector=QComboBox()
        self.hv_channel_selector.addItems(["Channel 1","Channel 2","Channel 3","Channel 4","Channel 5","Channel 6",
        "Channel 7","Channel 8","Channel 9","Channel 10","Channel 11","Channel 12"])
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

    def diagnostics_setup(self):
        self.tab7=QWidget()

    def lv_controls_setup(self):
        self.tab2=QWidget()
        self.tab2.layout=QGridLayout()

        # initialize lv control buttons and indicators
        self.lv_power_button_1=QPushButton("LV 1")
        self.lv_power_button_1.setFixedSize(QSize(210, 130))
        self.lv_power_button_1.setStyleSheet('background-color: red')
        self.lv_power_button_1.setFont(QFont("Arial", 45))

        self.lv_power_button_2=QPushButton("LV 2")
        self.lv_power_button_2.setFixedSize(QSize(210, 130))
        self.lv_power_button_2.setStyleSheet('background-color: red')
        self.lv_power_button_2.setFont(QFont("Arial", 45))

        self.lv_power_button_3=QPushButton("LV 3")
        self.lv_power_button_3.setFixedSize(QSize(210, 130))
        self.lv_power_button_3.setStyleSheet('background-color: red')
        self.lv_power_button_3.setFont(QFont("Arial", 45))

        self.lv_power_button_4=QPushButton("LV 4")
        self.lv_power_button_4.setFixedSize(QSize(210, 130))
        self.lv_power_button_4.setStyleSheet('background-color: red')
        self.lv_power_button_4.setFont(QFont("Arial", 45))

        self.lv_power_button_5=QPushButton("LV 5")
        self.lv_power_button_5.setFixedSize(QSize(210, 130))
        self.lv_power_button_5.setStyleSheet('background-color: red')
        self.lv_power_button_5.setFont(QFont("Arial", 45))

        self.lv_power_button_6=QPushButton("LV 6")
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

    def hv_controls_setup(self):
        self.tab3=QWidget()
        self.tab3.layout=QGridLayout()

        # initilize hv control buttons
        self.hv_power_button_1=QPushButton("HV 1")
        self.hv_power_button_1.setFixedSize(QSize(130, 80))
        self.hv_power_button_1.setStyleSheet('background-color: red')
        self.hv_power_button_1.setFont(QFont("Arial", 30))

        self.hv_power_button_2=QPushButton("HV 2")
        self.hv_power_button_2.setFixedSize(QSize(130, 80))
        self.hv_power_button_2.setStyleSheet('background-color: red')
        self.hv_power_button_2.setFont(QFont("Arial", 30))

        self.hv_power_button_3=QPushButton("HV 3")
        self.hv_power_button_3.setFixedSize(QSize(130, 80))
        self.hv_power_button_3.setStyleSheet('background-color: red')
        self.hv_power_button_3.setFont(QFont("Arial", 30))

        self.hv_power_button_4=QPushButton("HV 4")
        self.hv_power_button_4.setFixedSize(QSize(130, 80))
        self.hv_power_button_4.setStyleSheet('background-color: red')
        self.hv_power_button_4.setFont(QFont("Arial", 30))

        self.hv_power_button_5=QPushButton("HV 5")
        self.hv_power_button_5.setFixedSize(QSize(130, 80))
        self.hv_power_button_5.setStyleSheet('background-color: red')
        self.hv_power_button_5.setFont(QFont("Arial", 30))

        self.hv_power_button_6=QPushButton("HV 6")
        self.hv_power_button_6.setFixedSize(QSize(130, 80))
        self.hv_power_button_6.setStyleSheet('background-color: red')
        self.hv_power_button_6.setFont(QFont("Arial", 30))

        self.hv_power_button_7=QPushButton("HV 7")
        self.hv_power_button_7.setFixedSize(QSize(130, 80))
        self.hv_power_button_7.setStyleSheet('background-color: red')
        self.hv_power_button_7.setFont(QFont("Arial", 30))

        self.hv_power_button_8=QPushButton("HV 8")
        self.hv_power_button_8.setFixedSize(QSize(130, 80))
        self.hv_power_button_8.setStyleSheet('background-color: red')
        self.hv_power_button_8.setFont(QFont("Arial", 30))

        self.hv_power_button_9=QPushButton("HV 9")
        self.hv_power_button_9.setFixedSize(QSize(130, 80))
        self.hv_power_button_9.setStyleSheet('background-color: red')
        self.hv_power_button_9.setFont(QFont("Arial", 30))

        self.hv_power_button_10=QPushButton("HV 10")
        self.hv_power_button_10.setFixedSize(QSize(130, 80))
        self.hv_power_button_10.setStyleSheet('background-color: red')
        self.hv_power_button_10.setFont(QFont("Arial", 30))

        self.hv_power_button_11=QPushButton("HV 11")
        self.hv_power_button_11.setFixedSize(QSize(130, 80))
        self.hv_power_button_11.setStyleSheet('background-color: red')
        self.hv_power_button_11.setFont(QFont("Arial", 30))

        self.hv_power_button_12=QPushButton("HV 12")
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
        self.blade_control_table.setVerticalHeaderLabels(["Ch 1","Ch 2","Ch 3","Ch 4","Ch 5","Ch 6"])
        self.blade_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

        # setup board table
        self.board_control_table=QTableWidget()
        self.board_control_table.setRowCount(6)
        self.board_control_table.setColumnCount(4)
        self.board_control_table.setFixedWidth(550)
        self.board_control_table.setDisabled(True)

        self.board_control_table.setHorizontalHeaderLabels(["5V Voltage (V)","5V Current (A)","Cond Voltage (V)","Cond Current (A)"])
        self.board_control_table.setVerticalHeaderLabels(["Ch 1","Ch 2","Ch 3","Ch 4","Ch 5","Ch 6"])
        self.board_control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

        # setup hv table
        self.hv_control_table=QTableWidget()
        self.hv_control_table.setRowCount(12)
        self.hv_control_table.setColumnCount(2)
        self.hv_control_table.setFixedWidth(550)
        self.hv_control_table.setDisabled(True)
        for i in range(0,12):
            self.hv_control_table.setRowHeight(i,24)

        self.hv_control_table.setVerticalHeaderLabels(["Ch 1","Ch 2","Ch 3","Ch 4","Ch 5","Ch 6","Ch 7","Ch 8","Ch 9","Ch 10","Ch 11","Ch 12"])
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

        # fill blade table with entries and set background color
        self.blade_voltage_entries=[]
        self.blade_current_entries=[]
        self.blade_temperature_entries=[]

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
        else:
            indicators[number].setStyleSheet('background-color: green')
            self.blade_power[number]=True

    # called when one of the hv power buttons is pressed
    def actuate_hv_power(self,number):
        indicators=[self.hv_power_button_1,self.hv_power_button_2,self.hv_power_button_3,
        self.hv_power_button_4,self.hv_power_button_5,self.hv_power_button_6,
        self.hv_power_button_7,self.hv_power_button_8,self.hv_power_button_9,
        self.hv_power_button_10,self.hv_power_button_11,self.hv_power_button_12]

        if self.hv_power[number]==True:
            indicators[number].setStyleSheet('background-color: red')
            self.hv_power[number]=False
        else:
            indicators[number].setStyleSheet('background-color: green')
            self.hv_power[number]=True

    def update_blade_table(self):
        for j in range(6):
            self.blade_voltage_entries[j].setText(str(self.voltage[j]))
            self.blade_current_entries[j].setText(str(self.current[j]))
            self.blade_temperature_entries[j].setText(str(self.temperature[j]))

    def update_board_table(self):
        for j in range(6):
            self.board_5v_voltage_entries[j].setText(str(self.five_voltage[j]))
            self.board_5v_current_entries[j].setText(str(self.five_current[j]))
            self.board_cond_voltage_entries[j].setText(str(self.cond_voltage[j]))
            self.board_cond_current_entries[j].setText(str(self.cond_current[j]))

    def update_hv_table(self):
        for j in range(12):
            self.hv_voltage_entries[j].setText(str(self.hv_voltage[j]))
            self.hv_current_entries[j].setText(str(self.hv_current[j]))

    # acquires the channel being measured
    def get_blade_channel(self):
        # determine which blade data is to be plotted for
        channels={"Channel 1": 0,"Channel 2": 1,"Channel 3": 2,"Channel 4": 3,"Channel 5": 4,"Channel 6": 5}
        channel=channels[self.blade_channel_selector.currentText()]
        return channel

    def get_board_channel(self):
        # determine which blade data is to be plotted for
        channels={"Channel 1": 0,"Channel 2": 1,"Channel 3": 2,"Channel 4": 3,"Channel 5": 4,"Channel 6": 5}
        channel=channels[self.board_channel_selector.currentText()]
        return channel

    def get_hv_channel(self):
        # determine which hv channel data is to be plotted for
        channels={"Channel 1": 0,"Channel 2": 1,"Channel 3": 2,"Channel 4": 3,"Channel 5": 4,
        "Channel 6": 5,"Channel 7": 6,"Channel 8": 7,"Channel 9": 8,"Channel 10": 9,
        "Channel 11": 10,"Channel 12": 11}
        channel=channels[self.hv_channel_selector.currentText()]
        return channel

    # instantly changes what's being displayed on the main plot, depending on the user's selection
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

        if type=="Voltage":
            self.blade_plot_data.set_ydata(self.blade_voltage_plot[channel])
        elif type=="Current":
            self.blade_plot_data.set_ydata(self.blade_current_plot[channel])
        else:
            self.blade_plot_data.set_ydata(self.blade_temperature_plot[channel])
        self.blade_plot_canvas.draw()
        self.blade_plot_canvas.flush_events()

    def change_hv_plot(self):
        channel=self.get_hv_channel()
        type=self.hv_measurement_selector.currentText()

        # update labels for the hv plot
        self.hv_plot_axes.set_title(self.hv_channel_selector.currentText() + ' HV ' + type)
        if type=="Voltage":
            self.hv_plot_axes.set_ylabel('Voltage (V)')
            self.hv_plot_axes.set_ylim([1000,2000])
        else:
            self.hv_plot_axes.set_ylabel('Current (A)')
            self.hv_plot_axes.set_ylim([0,100])

        if type=="Voltage":
            self.hv_plot_data.set_ydata(self.hv_voltage_plot[channel])
        else:
            self.hv_plot_data.set_ydata(self.hv_current_plot[channel])
        self.hv_plot_canvas.draw()
        self.hv_plot_canvas.flush_events()

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

        if type=="5V Voltage":
            self.board_plot_data.set_ydata(self.board_5v_voltage_plot[channel])
        elif type=="5V Current":
            self.board_plot_data.set_ydata(self.board_5v_current_plot[channel])
        elif type=="Conditioned Voltage":
            self.board_plot_data.set_ydata(self.board_cond_voltage_plot[channel])
        else:
            self.board_plot_data.set_ydata(self.board_cond_current_plot[channel])
        self.board_plot_canvas.draw()
        self.board_plot_canvas.flush_events()



    # called by the timer to update the main plot with new data
    def update_blade_plot(self):
        channel=self.get_blade_channel()
        type=self.blade_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.blade_voltage_plot)):
            self.blade_voltage_plot[i]=[self.voltage[i]]+self.blade_voltage_plot[i][:-1]
            self.blade_current_plot[i]=[self.current[i]]+self.blade_current_plot[i][:-1]
            self.blade_temperature_plot[i]=[self.temperature[i]]+self.blade_temperature_plot[i][:-1]

        if type=="Voltage":
            self.blade_plot_data.set_ydata(self.blade_voltage_plot[channel])
        elif type=="Current":
            self.blade_plot_data.set_ydata(self.blade_current_plot[channel])
        else:
            self.blade_plot_data.set_ydata(self.blade_temperature_plot[channel])
        self.blade_plot_canvas.draw()
        self.blade_plot_canvas.flush_events()

    def update_board_plot(self):
        channel=self.get_board_channel()
        type=self.board_measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.board_5v_voltage_plot)):
            self.board_5v_voltage_plot[i]=[self.five_voltage[i]]+self.board_5v_voltage_plot[i][:-1]
            self.board_5v_current_plot[i]=[self.five_current[i]]+self.board_5v_current_plot[i][:-1]
            self.board_cond_voltage_plot[i]=[self.cond_voltage[i]]+self.board_cond_voltage_plot[i][:-1]
            self.board_cond_current_plot[i]=[self.cond_current[i]]+self.board_cond_current_plot[i][:-1]

        if type=="5V Voltage":
            self.board_plot_data.set_ydata(self.board_5v_voltage_plot[channel])
        elif type=="5V Current":
            self.board_plot_data.set_ydata(self.board_5v_current_plot[channel])
        elif type=="Conditioned Voltage":
            self.board_plot_data.set_ydata(self.board_cond_voltage_plot[channel])
        else:
            self.board_plot_data.set_ydata(self.board_cond_current_plot[channel])
        self.board_plot_canvas.draw()
        self.board_plot_canvas.flush_events()

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

    def assorted_update(self):
        update=self.get_data(False)
        if update:
            self.update_blade_table()
            self.update_board_table()
            self.update_hv_table()
            self.update_blade_plot()
            self.update_board_plot()
            self.update_hv_plot()
            self.save_txt()

    def initialize_data(self):
        self.blade_voltage_plot=[[500]*50]*6
        self.blade_current_plot=[[500]*50]*6
        self.blade_temperature_plot=[[500]*50]*6

        self.board_5v_voltage_plot=[[500]*50]*6
        self.board_5v_current_plot=[[500]*50]*6
        self.board_cond_voltage_plot=[[500]*50]*6
        self.board_cond_current_plot=[[500]*50]*6

        self.hv_voltage_plot=[[10000]*50]*12
        self.hv_current_plot=[[10000]*50]*12

        # keeps track of blade power statuses
        self.blade_power=[False]*6

        # keeps track of hv power statuses
        self.hv_power=[False]*12

    def run(self):
        self.timer = QTimer(self)
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.assorted_update)
        self.timer.start(1000)

if __name__=="__main__":
    try:
        # create pyqt5 app
        App = QApplication(sys.argv)

        # create the instance of our Window
        window = Window()

        # run the lv initialization function
        window.initialize_lv(True)

        window.run()

        # start the app
        sys.exit(App.exec())

    except KeyboardInterrupt:
        stored_exception=sys.exc_info()
    except Exception as e:
        print (type(e),e)
