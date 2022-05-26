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

        # initialize blade plotting Window
        self.plotting_setup()

        # initialize board plotting Window
        self.readMon_setup()

        # initialize diagnostics Window
        self.diagnostics_setup()

        self.tabs.addTab(self.tab1,"Controls")
        self.tabs.addTab(self.tab2,"Raw Blade Plots")
        self.tabs.addTab(self.tab3,"Board Plots")
        self.tabs.addTab(self.tab4,"Diagnostics")

        self.setWindowTitle("LVHV GUI")
        self.setCentralWidget(self.tabs)

        self.show()


    def plotting_setup(self):
        self.tab2=QWidget()
        self.tab2.layout=QGridLayout()

        # set up the primary plot
        self.main_plot=Figure()
        self.main_plot_canvas=FigureCanvas(self.main_plot)
        self.main_plot_axes=self.main_plot.add_subplot(111)

        self.main_plot_axes.set_xlim([0,50])
        self.main_plot_axes.set_ylim([0,100])
        self.main_plot_axes.set_title('Channel 1 Blade Voltage')
        self.main_plot_axes.set_ylabel('Voltage (V)')
        self.main_plot_axes.set_xlabel('Iterative Age of Datapoint')

        # initialize data (placed outside of bounds, so that it doesn't show up initially)
        self.main_plot_data_y=[500]*50
        self.main_plot_data_x=[*range(0,50,1)]

        self.main_plot_data=self.main_plot_axes.plot(self.main_plot_data_x,self.main_plot_data_y,marker='o',linestyle='None',markersize=2,color='k')[0]


        # add dropdown menus to select what's plotted
        self.channel_selector=QComboBox()
        self.channel_selector.addItems(["Channel 1","Channel 2","Channel 3","Channel 4","Channel 5","Channel 6"])
        self.channel_selector.setStyleSheet(button_color)
        self.channel_selector.currentIndexChanged.connect(self.change_main_plot)

        self.measurement_selector=QComboBox()
        self.measurement_selector.addItems(["Voltage","Current","Temperature"])
        self.measurement_selector.setStyleSheet(button_color)
        self.measurement_selector.currentIndexChanged.connect(self.change_main_plot)

        # add widgets and set layout
        self.tab2.layout.addWidget(self.channel_selector,0,0)
        self.tab2.layout.addWidget(self.measurement_selector,1,0)
        self.tab2.layout.addWidget(self.main_plot_canvas,0,1)
        self.tab2.setLayout(self.tab2.layout)

    def readMon_setup(self):
        self.tab3=QWidget()

    def diagnostics_setup(self):
        self.tab4=QWidget()


    def controls_setup(self):
        self.tab1=QWidget()
        self.tab1.layout=QGridLayout()
        self.tab1.layout.setContentsMargins(20,20,20,20)

        # define buttons and indicators

        self.power_button_1=QPushButton("Blade 1 Power")
        self.power_button_1.setStyleSheet(button_color)
        self.power_indicator_1=QCheckBox()
        self.power_indicator_1.setStyleSheet('background-color: red')
        self.power_indicator_1.setDisabled(True)

        self.power_button_2=QPushButton("Blade 2 Power")
        self.power_button_2.setStyleSheet(button_color)
        self.power_indicator_2=QCheckBox()
        self.power_indicator_2.setStyleSheet('background-color: red')
        self.power_indicator_2.setDisabled(True)

        self.power_button_3=QPushButton("Blade 3 Power")
        self.power_button_3.setStyleSheet(button_color)
        self.power_indicator_3=QCheckBox()
        self.power_indicator_3.setStyleSheet('background-color: red')
        self.power_indicator_3.setDisabled(True)

        self.power_button_4=QPushButton("Blade 4 Power")
        self.power_button_4.setStyleSheet(button_color)
        self.power_indicator_4=QCheckBox()
        self.power_indicator_4.setStyleSheet('background-color: red')
        self.power_indicator_4.setDisabled(True)

        self.power_button_5=QPushButton("Blade 5 Power")
        self.power_button_5.setStyleSheet(button_color)
        self.power_indicator_5=QCheckBox()
        self.power_indicator_5.setStyleSheet('background-color: red')
        self.power_indicator_5.setDisabled(True)

        self.power_button_6=QPushButton("Blade 6 Power")
        self.power_button_6.setStyleSheet(button_color)
        self.power_indicator_6=QCheckBox()
        self.power_indicator_6.setStyleSheet('background-color: red')
        self.power_indicator_6.setDisabled(True)


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
        self.power_button_box=QWidget()
        self.power_button_box.layout=QGridLayout()
        self.power_button_box.layout.addWidget(self.power_button_1,0,0)
        self.power_button_box.layout.addWidget(self.power_button_2,1,0)
        self.power_button_box.layout.addWidget(self.power_button_3,2,0)
        self.power_button_box.layout.addWidget(self.power_button_4,3,0)
        self.power_button_box.layout.addWidget(self.power_button_5,4,0)
        self.power_button_box.layout.addWidget(self.power_button_6,5,0)

        self.power_button_box.layout.addWidget(self.power_indicator_1,0,1)
        self.power_button_box.layout.addWidget(self.power_indicator_2,1,1)
        self.power_button_box.layout.addWidget(self.power_indicator_3,2,1)
        self.power_button_box.layout.addWidget(self.power_indicator_4,3,1)
        self.power_button_box.layout.addWidget(self.power_indicator_5,4,1)
        self.power_button_box.layout.addWidget(self.power_indicator_6,5,1)

        self.power_button_box.setLayout(self.power_button_box.layout)

        self.blade_table_box=QWidget()
        self.blade_table_box.layout=QGridLayout()
        self.blade_table_box.layout.addWidget(self.blade_table_label,0,1)
        self.blade_table_box.layout.addWidget(self.control_table,1,1)
        self.blade_table_box.setLayout(self.blade_table_box.layout)

        self.tab1.layout.addWidget(self.power_button_box,0,0)
        self.tab1.layout.addWidget(self.blade_table_box,0,1)

        self.tab1.setLayout(self.tab1.layout)

    def update_table(self):
        for j in range(6):
            self.blade_voltage_entries[j].setText(str(self.voltage[j]))
            self.blade_current_entries[j].setText(str(self.current[j]))
            self.blade_temperature_entries[j].setText(str(self.temperature[j]))

    # acquires the channel being measured
    def get_channel(self):
        # determine which blade data is to be plotted for
        channels={"Channel 1": 0,"Channel 2": 1,"Channel 3": 2,"Channel 4": 3,"Channel 5": 4,"Channel 6": 5}
        channel=channels[self.channel_selector.currentText()]
        return channel

    # instantly changes what's being displayed on the main plot, depending on the user's selection
    def change_main_plot(self):
        channel=self.get_channel()
        type=self.measurement_selector.currentText()

        # update labels for the main plot
        self.main_plot_axes.set_title(self.channel_selector.currentText() + ' Blade ' + type)
        if type=="Voltage":
            self.main_plot_axes.set_ylabel('Voltage (V)')
        elif type=="Current":
            self.main_plot_axes.set_ylabel('Current (A)')
        else:
            self.main_plot_axes.set_ylabel('Temperature (C)')

        if type=="Voltage":
            self.main_plot_data.set_ydata(self.blade_voltage_plot[channel])
        elif type=="Current":
            self.main_plot_data.set_ydata(self.blade_current_plot[channel])
        else:
            self.main_plot_data.set_ydata(self.blade_temperature_plot[channel])
        self.main_plot_canvas.draw()
        self.main_plot_canvas.flush_events()



    # called by the timer to update the main plot with new data
    def update_main_plot(self):
        channel=self.get_channel()
        type=self.measurement_selector.currentText()

        # rotate plot lists
        for i in range(len(self.blade_voltage_plot)):
            self.blade_voltage_plot[i]=[self.voltage[i]]+self.blade_voltage_plot[i][:-1]
            self.blade_current_plot[i]=[self.current[i]]+self.blade_current_plot[i][:-1]
            self.blade_temperature_plot[i]=[self.temperature[i]]+self.blade_temperature_plot[i][:-1]

        if type=="Voltage":
            self.main_plot_data.set_ydata(self.blade_voltage_plot[channel])
        elif type=="Current":
            self.main_plot_data.set_ydata(self.blade_current_plot[channel])
        else:
            self.main_plot_data.set_ydata(self.blade_temperature_plot[channel])
        self.main_plot_canvas.draw()
        self.main_plot_canvas.flush_events()


    def assorted_update(self):
        self.get_data(True)
        self.update_table()
        self.update_main_plot()

    def initialize_data(self):
        self.blade_voltage_plot=[[500]*50]*6
        self.blade_current_plot=[[500]*50]*6
        self.blade_temperature_plot=[[500]*50]*6

    def run(self):
        self.initialize_data()
        self.timer = QTimer(self)
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.assorted_update)
        self.timer.start(200)

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
