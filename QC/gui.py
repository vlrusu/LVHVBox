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

# Only needed for access to command line arguments
import sys
import signal
import threading
import os
import socket
import time

from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

os.environ["DISPLAY"] = ':0'
background_color='background-color: white;'
button_color='background-color: white;'

def bitstring_to_bytes(s):
    return int(s, 2).to_bytes(4, byteorder='big')

def process_float(input):
    v = format(input[3], '008b') + format(input[2], '008b') + format(input[1], '008b') + format(input[0], '008b')

    sign = (-1) ** int(v[0],2)
    exponent = int(v[1:9],2)-127
    mantissa = int(v[9::],2)
    float_val = sign * (1+mantissa*(2**-23)) * 2**exponent
    
    return float_val


class Window(QMainWindow):
    def __init__(self):
        super(Window,self).__init__()

        self.v48=[0 for i in range(6)]
        self.i48=[0 for i in range(6)]
        self.v6=[0 for i in range(6)]
        self.i6=[0 for i in range(6)]
        self.T48=[0 for i in range(6)]
        self.hv_v=[0 for i in range(12)]
        self.hv_i=[0 for i in range(12)]
        self.hvpcbtemp=0
        self.i12V=0

        # initialize socket connection
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host = "127.0.0.1"
        self.port = 12000
        self.sock.connect((self.host,self.port))
    




        #window.setCursor(PyQt5.BlankCursor)
        self.setWindowTitle("LVHV GUI")
        self.setStyleSheet(background_color)
        

        # start data update timer
        self.table_update_timer = QTimer(self)
        self.table_update_timer.setSingleShot(False)
        self.table_update_timer.timeout.connect(self.update_data)
        self.table_update_timer.start(5000)


        self.display_setup()
        self.load_commands()




        #self.showFullScreen()
        self.show()



    # ----- data acquisition functions -----
    def update_hv_v(self):
        command_get_vhv = bitstring_to_bytes(self.command_dict["COMMAND_get_vhv"])
        type_hv = bitstring_to_bytes(self.command_dict["TYPE_hv"])

        for channel in range(12):
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_get_vhv + type_hv + bits_channel + padding

            self.sock.send(command_string)

            temp = self.sock.recv(1024)
            self.hv_v[channel] = round(process_float(temp),2)
    
    def update_hv_i(self):
        command_get_ihv = bitstring_to_bytes(self.command_dict["COMMAND_get_ihv"])
        type_hv = bitstring_to_bytes(self.command_dict["TYPE_hv"])

        for channel in range(12):
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_get_ihv + type_hv + bits_channel + padding

            self.sock.send(command_string)

            temp = self.sock.recv(1024)
            self.hv_i[channel] = round(process_float(temp),2)
    
    def update_v48(self):
        command_readMonV48 = bitstring_to_bytes(self.command_dict["COMMAND_readMonV48"])
        type_lv = bitstring_to_bytes(self.command_dict["TYPE_lv"])

        for channel in range(6):
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonV48 + type_lv + bits_channel + padding

            self.sock.send(command_string)

            temp = self.sock.recv(1024)
            self.v48[channel] = round(process_float(temp),2)

    def update_i48(self):
        command_readMonI48 = bitstring_to_bytes(self.command_dict["COMMAND_readMonI48"])
        type_lv = bitstring_to_bytes(self.command_dict["TYPE_lv"])

        for channel in range(6):
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonI48 + type_lv + bits_channel + padding

            self.sock.send(command_string)

            temp = self.sock.recv(1024)
            self.i48[channel] = round(process_float(temp),2)
    
    def update_v6(self):
        command_readMonV6 = bitstring_to_bytes(self.command_dict["COMMAND_readMonV6"])
        type_lv = bitstring_to_bytes(self.command_dict["TYPE_lv"])

        for channel in range(6):
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonV6 + type_lv + bits_channel + padding

            self.sock.send(command_string)

            temp = self.sock.recv(1024)
            self.v6[channel] = round(process_float(temp),2)
    
    def update_i6(self):
        command_readMonI6 = bitstring_to_bytes(self.command_dict["COMMAND_readMonI6"])
        type_lv = bitstring_to_bytes(self.command_dict["TYPE_lv"])

        for channel in range(6):
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonI6 + type_lv + bits_channel + padding

            self.sock.send(command_string)

            temp = self.sock.recv(1024)
            self.i6[channel] = round(process_float(temp),2)
     
   



    def load_commands(self):
        file = open("../commands.h", "r")
        pre_command_list = file.readlines()
        pre_command_list = [i.split() for i in pre_command_list]

        self.command_dict = {}
        for i in pre_command_list:
            #command_dict[i[1]] = format(int(i[2]), '032b')
            #command_dict[i[1]] = struct.pack('<I', int(i[2])).decode('utf-8')
            string = format(int(i[2]), '032b')
            #print(string)


            #command_dict[i[1]] = bstring_to_chars(string)
            self.command_dict[i[1]] = string

    def update_data(self):
        self.update_hv_v()
        self.update_hv_i()
        self.update_v48()
        self.update_i48()
        self.update_v6()
        self.update_i6()

        for i in range(6):
            self.lv_voltage_entries[i].setText(str(self.v48[i]))
            self.lv_current_entries[i].setText(str(self.i48[i]))
            self.lv_temp_entries[i].setText(str(self.T48[i]))

            self.six_lv_voltage_entries[i].setText(str(self.v6[i]))
            self.six_lv_current_entries[i].setText(str(self.i6[i]))
        
        for i in range(12):
            self.hv_voltage_entries[i].setText(str(self.hv_v[i]))
            self.hv_current_entries[i].setText(str(self.hv_i[i]))


    def display_setup(self):
        self.all_display = QWidget()
        self.all_display.layout = QGridLayout()
        self.setCentralWidget(self.all_display)
        
        # create table labels
        self.lv_label = QLabel("48V LV")
        self.all_display.layout.addWidget(self.lv_label,0,0)
        self.hv_label = QLabel("HV")
        self.all_display.layout.addWidget(self.hv_label,0,1)
        self.six_lv_label = QLabel("6V LV")
        self.all_display.layout.addWidget(self.six_lv_label,2,0)

        # ----- create lv table -----
        self.lv_table = QTableWidget()
        self.lv_table.setRowCount(6)
        self.lv_table.setColumnCount(3)
        self.lv_table.setVerticalHeaderLabels(["Ch " + str(i) for i in range(6)])
        self.lv_table.setHorizontalHeaderLabels(["Voltage (V)", "Current (A)", "Temp (C)"])
        self.all_display.layout.addWidget(self.lv_table,1,0)

        # populate lv table with entries
        self.lv_voltage_entries = []
        self.lv_current_entries = []
        self.lv_temp_entries = []

        for i in range(6):
            # fill with lv voltage entries
            current_entry = QLabel(str(self.v48[i]))
            current_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.lv_voltage_entries.append(current_entry)
            self.lv_table.setCellWidget(i,0,current_entry)

            # fill with lv current entries
            current_entry = QLabel(str(self.i48[i]))
            current_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.lv_current_entries.append(current_entry)
            self.lv_table.setCellWidget(i,1,current_entry)

            # fill with lv temp entries
            current_entry = QLabel(str(self.T48[i]))
            current_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.lv_temp_entries.append(current_entry)
            self.lv_table.setCellWidget(i,2,current_entry)

        # ----- create six lv table -----
        self.six_lv_table = QTableWidget()
        self.six_lv_table.setRowCount(6)
        self.six_lv_table.setColumnCount(2)
        self.six_lv_table.setVerticalHeaderLabels(["Ch " + str(i) for i in range(6)])
        self.six_lv_table.setHorizontalHeaderLabels(["Voltage (V)", "Current (uA)"])
        self.all_display.layout.addWidget(self.six_lv_table,3,0)

        # populate six lv table with entries
        self.six_lv_voltage_entries = []
        self.six_lv_current_entries = []

        for i in range(6):
            # fill with six lv voltage entries
            current_entry = QLabel(str(self.v6[i]))
            current_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.six_lv_voltage_entries.append(current_entry)
            self.six_lv_table.setCellWidget(i,0,current_entry)

            # fill with six lv current entries
            current_entry = QLabel(str(self.i6[i]))
            current_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.six_lv_current_entries.append(current_entry)
            self.six_lv_table.setCellWidget(i,1,current_entry)

        # ----- create hv table -----
        self.hv_table = QTableWidget()
        self.hv_table.setRowCount(12)
        self.hv_table.setColumnCount(2)
        self.hv_table.setVerticalHeaderLabels(["Ch " + str(i) for i in range(12)])
        self.hv_table.setHorizontalHeaderLabels(["Voltage (V)", "Current (uA)"])
        self.all_display.layout.addWidget(self.hv_table,1,1)

        # populate hv table with entries
        self.hv_voltage_entries = []
        self.hv_current_entries = []

        for i in range(12):
            # fill with hv voltage entries
            current_entry = QLabel(str(self.hv_v[i]))
            current_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.hv_voltage_entries.append(current_entry)
            self.hv_table.setCellWidget(i,0,current_entry)

            # fill with hv current entries
            current_entry = QLabel(str(self.hv_i[i]))
            current_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            current_entry.setStyleSheet(button_color)
            self.hv_current_entries.append(current_entry)
            self.hv_table.setCellWidget(i,1,current_entry)



        self.all_display.setLayout(self.all_display.layout)
    
  


if __name__=="__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)



    App = QApplication(sys.argv)

    window = Window()


    gui_thread = threading.Thread(target=App.exec(), daemon = True)
    gui_thread.start()


