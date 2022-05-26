import sys
import glob
import os
import json
import struct
import time
import threading
import readline
#import matplotlib
#import matplotlib.pyplot as plt
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

from PyQt4.QtGui import *
from PyQt4.QtCore import *


os.environ["DISPLAY"] = ':0'
background_color='background-color: blue;'
button_color='background-color: white;'


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

    def save_txt(self,text,test):
        file1=open("logfile.txt", "a")
        file1.write(text)
        file1.close()
        if test:
            print(text)

    def get_data(self,test):
        # acquire Voltage
        voltage_values=[]
        if not test:
            pass
        else:
            for i in range(0,6):
                voltage_values.append(round(random.uniform(35,45),3))
                # ensure delay between channel readings

        # acquire Current
        current_values=[]
        if not test:
            pass
        else:
            for i in range(0,6):
                current_values.append(round(random.uniform(10,15),3))
                # ensure delay between channel readings

        # acquire Temperature
        temperature_values=[]
        if not test:
            pass
        else:
            for i in range(0,6):
                temperature_values.append(round(random.uniform(28,35),3))
                # ensure delay between channel readings

        # return data lists in format voltage, current, temperature
        self.voltage=voltage_values
        self.current=current_values
        self.temperature=temperature_values



class Window(QMainWindow,Session):
    def __init__(self):
        super(Window,self).__init__()
        # since it's a touch screen, the cursor is irritating
        self.setCursor(Qt.BlankCursor)

        self.setWindowTitle("LVHV GUI")

        self.setStyleSheet(background_color)

        # call function to set up the overall tab layout
        self.tabs()

        self.showFullScreen()

    def tabs(self):
        self.tabs=QTabWidget()

        # initialize control buttons
        self.controls_setup()

        # initialize plotting Window
        self.plotting_setup()

        # initialize diagnostics Window
        self.diagnostics_setup()

        self.tabs.addTab(self.tab1,"Controls")
        self.tabs.addTab(self.tab2,"Plots")
        self.tabs.addTab(self.tab3,"Diagnostics")

        self.setWindowTitle("LVHV GUI")
        self.setCentralWidget(self.tabs)

        self.show()


    def plotting_setup(self):
        self.tab2=QWidget()

    def diagnostics_setup(self):
        self.tab3=QWidget()


    def controls_setup(self):
        self.tab1=QWidget()
        self.tab1.layout=QGridLayout()
        self.tab1.layout.setContentsMargins(20,20,20,20)

        # define buttons
        self.power_button=QPushButton("On")
        self.power_button.setStyleSheet(button_color)


        # create label for blade table
        self.blade_table_label=QLabel("Blade Data")
        self.blade_table_label.setAlignment(Qt.AlignCenter)
        self.blade_table_label.setStyleSheet("font-weight: bold")

        # setup table
        self.control_table=QTableWidget()
        self.control_table.setRowCount(6)
        self.control_table.setColumnCount(3)
        self.control_table.setFixedWidth(550)
        self.control_table.setDisabled(True)

        self.control_table.setHorizontalHeaderLabels(["Voltage (V)","current (A)","Temperature (C)"])
        self.control_table.setVerticalHeaderLabels(["Ch 1","Ch 2","Ch 3","Ch 4","Ch 5","Ch 6"])
        self.control_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)

        # fill table with entries and set background color
        self.blade_voltage_entries=[]
        self.blade_current_entries=[]
        self.blade_temperature_entries=[]

        for i in range(6):
            # fill with blade voltage entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.blade_voltage_entries.append(current_entry)
            self.control_table.setCellWidget(i,0,current_entry)

            # fill with blade current entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.blade_current_entries.append(current_entry)
            self.control_table.setCellWidget(i,1,current_entry)

            # fill with blade temperature entries
            current_entry=QLabel("N/A")
            current_entry.setAlignment(Qt.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.blade_temperature_entries.append(current_entry)
            self.control_table.setCellWidget(i,2,current_entry)

        # add items to tab 1 layout
        self.tab1.layout.addWidget(self.power_button,0,0)
        self.tab1.layout.addWidget(self.control_table,1,1)
        self.tab1.layout.addWidget(self.blade_table_label,0,1)
        self.tab1.setLayout(self.tab1.layout)

    def update_table(self):
        for j in range(6):
            self.blade_voltage_entries[j].setText(str(self.voltage[j]))
            self.blade_current_entries[j].setText(str(self.current[j]))
            self.blade_temperature_entries[j].setText(str(self.temperature[j]))

    def assorted_update(self):
        self.get_data(True)
        self.update_table()

    def run(self):
        self.timer = QTimer(self)
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.assorted_update)
        self.timer.start(3000)

if __name__=="__main__":
    try:
        """
        while True:
            voltage,current,temperature=get_data(True)
            output=str(time.time())+","
            for i in range(0,12):
                output+="ch" + str(i)
                output+=","+str(voltage[i])
                output+=","+str(current[i])
                output+=","+str(temperature[i])
            output+="\n"
            save_txt(output,True)
            time.sleep(5)
        """
        # create pyqt5 app
        App = QApplication(sys.argv)
        # create the instance of our Window
        window = Window()

        window.run()

        # start the app
        sys.exit(App.exec())

    except KeyboardInterrupt:
        stored_exception=sys.exc_info()
    except Exception as e:
        print (type(e),e)
