import sys
import glob
import serial
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta
import socket
import time
import json
from collections import deque
import math

import subprocess
import select

from file_read_backwards import FileReadBackwards


HEADER_LENGTH = 10
LVTYPE = 0
HVTYPE0 = 1
HVTYPE1 = 2
BATTERYTYPE = 3

CONFIG_PATH = "../config.txt"

class QC:
    def __init__(self, total_values, frequency):

        # open config.txt file
        with open(CONFIG_PATH) as file:
            lines = file.readlines()
        
            parameters = {}

            for item in lines:
                parameter = item.split(":")
                parameters[parameter[0]] = parameter[1]
        
        self.parameters = parameters






        self.total_values = total_values
        self.frequency = frequency

        self.short_plot_length = 1000


        # initialize current and voltage values
        self.long_current = np.zeros((6, total_values))

        self.short_current = np.zeros((6,self.short_plot_length))
        self.short_timestamps = np.linspace(0,self.short_plot_length/self.frequency,self.short_plot_length)


        self.voltage = np.zeros((6, total_values))

        # initialize time stuff
        self.start_time = datetime.now()
        self.start_time_standard = time.time()
        self.timestamps = np.zeros(total_values)

        #self.timestamps = np.linspace(0,total_values/frequency,total_values)
        self.inv_timestamps = np.zeros(total_values)

        self.background = np.empty((12,1))

        # define plotting stuff
        self.fig,self.ax = plt.subplots(6,2,gridspec_kw={'width_ratios':[1,3]})
        plt.grid(visible=True,which='major',axis='x')
        self.lns = [[1 for j in range(2)] for i in range(6)]

        for i in range(6):
            (self.lns[i][0],) = self.ax[i][0].plot(self.short_timestamps,self.short_current[i],'o',animated=True,color='r',markersize=2)
            (self.lns[i][1],) = self.ax[i][1].plot(self.timestamps,self.long_current[i],'o',animated=True,color='r',markersize=2)
            #(self.lns_v[i],) = self.vax[i].plot(self.timestamps,self.voltage[i],'o',animated=True,color='b',markersize=2)


        # plot titles
        for i in range(6):
            self.ax[i][0].set_ylabel(f'Ch{i} Short \n Current (uA)')
            self.ax[i][1].set_ylabel(f'Ch{i} Long \n Current (uA)',color='r')
            self.ax[i][1].set_title("",y=1.0, pad=-14)
            #self.vax[i].set_ylabel("Voltage (V)",color='b')
    
        self.t = [None for i in range(6)]
        for i in range(6):
            self.t[i] = self.ax[i][1].text(500,100,'')
        
            

        # set plots to fullscreen
        self.manager = plt.get_current_fig_manager()
        self.manager.full_screen_toggle()
        self.set_limits()


        # plot axis labels
        for i in range(6):
            self.ax[i][0].set_xlabel('Time(s)')
            self.ax[i][1].set_xlabel('Time(s)')


        plt.show(block=False)
        plt.pause(0.1)

        #more animation settings
        self.bg = self.fig.canvas.copy_from_bbox(self.fig.bbox)
    
    def send(self,data):
        serialized = json.dumps(data)
        msg = f"{len(serialized):<{HEADER_LENGTH}}"

        self.conn.send(bytes(msg+serialized,"utf-8"))
    
    def receive_message(self, socket):

        try:
            # Receive our "header" containing message length, it's size is defined and constant
            message_header = socket.recv(HEADER_LENGTH)

            # If we received no data, client gracefully closed a connection, for example using socket.close() or socket.shutdown(socket.SHUT_RDWR)
            if not len(message_header):
                return False

            # Convert header to int value
            message_length = int(message_header.decode('utf-8').strip())

    #        app.async_alert(str(message_length))

            # Return an object of message header and message data
            return {'header': message_header, 'data': socket.recv(message_length)}

        except:

            # If we are here, client closed connection violently, for example by pressing ctrl+c on his script
            # or just lost his connection
            # socket.close() also invokes socket.shutdown(socket.SHUT_RDWR) what sends information about closing the socket (shutdown read/write)
            # and that's also a cause when we receive an empty message
            return False
    
    def set_limits(self):
        for i in range(6):
            self.ax[i][0].set_ylim(0,260) # max current of short term plot
            self.ax[i][0].set_xlim(0,self.short_plot_length/self.frequency) # max time of short term plot in seconds

            self.ax[i][1].set_ylim(0,260) # max current of long term plot
            self.ax[i][1].set_xlim(0,600) # max time of long term plot in seconds

            #[i].set_ylim(0,2000)
            #self.vax[i].set_xlim(0,600)

    def check_overflow(self):
        #limits max values of arrays to size of display
        # prevents memory overflow on arrays

        if len(self.background) > 20:
            self.background = np.delete(self.background,0)
        if self.long_current.shape[1] > self.total_values:
            self.long_current = np.delete(self.long_current,0,1)
        if len(self.timestamps) > self.total_values:
            self.timestamps = np.delete(self.timestamps,0)
        if self.voltage.shape[1] > self.total_values:
            self.voltage = np.delete(self.voltage,0,1)



   

    def grab_new_values(self):
        new_vhv0=[]
        new_ihv0=[]


        new_vhv0=[]


        num_lines = 600
        num_chars = 78*num_lines
        avg = [0 for i in range(6)]

        with open("../" + self.parameters["CServer_Path"]+"/Currents_0.txt", "rb") as file:
            try:
                file.seek(-num_chars, os.SEEK_END)
                while file.read(1) != b'\n':
                    file.seek(-2, os.SEEK_CUR)
            except OSError:
                file.seek(0)

            
            for i in range(num_lines):
                line = file.readline().decode()

                temp_ihv0=[float(i)/num_lines for i in line.split(' ')[:-1]]

                for j in range(6):
                    avg[j] += temp_ihv0[j]

            


            if len(avg) == 6:
                ihv0_np = np.array(avg).reshape(6,1)
                
                self.long_current = np.hstack((self.long_current,ihv0_np))

            event_time = datetime.now() # grabs current time
            delta_t = float((event_time-self.start_time).total_seconds()) # finds time passed since start of code
            self.timestamps = np.append(self.timestamps,delta_t) # adds timestamp of current value to timestamps array
                 
            
        search_multiplier=10 
        num_lines = self.short_plot_length*search_multiplier
        num_chars = 78*num_lines
        avg = [0 for i in range(6)]
        potential_maxes=[]
        

        with open("../" + self.parameters["CServer_Path"]+"/Currents_0.txt", "rb") as file:
            try:
                file.seek(-num_chars, os.SEEK_END)
                while file.read(1) != b'\n':
                    file.seek(-2, os.SEEK_CUR)
            except OSError:
                file.seek(0)

            
            for i in range(num_lines):
                line = file.readline().decode()

                new_ihv0=[float(i) for i in line.split(' ')[:-1]]
                potential_maxes.append(new_ihv0)
              
        
        max_index=0
        max_value=0
        for time_iteration in range(len(potential_maxes)):
            if len(potential_maxes[time_iteration]) == 6:
                for channel in range(6):
                    if potential_maxes[time_iteration][channel] > max_value:
                        max_value = potential_maxes[time_iteration][channel]
                        max_index = time_iteration
        
        # determine bounding indices for short term plot
        if max_index > self.short_plot_length/2:
            if math.floor(max_index + self.short_plot_length/2) >= search_multiplier*self.short_plot_length:
                upper_index = search_multiplier*self.short_plot_length-1
                lower_index = upper_index - math.floor(self.short_plot_length/2)
            else:
                lower_index=math.floor(max_index-self.short_plot_length/2)
                upper_index = lower_index + self.short_plot_length
        else:
            lower_index=0
            upper_index = self.short_plot_length
        
        


        # update short plot data
        for index in range(lower_index,upper_index):
            #print("length of potential_maxes: " + str(len(potential_maxes)))
            #print("lower index: " + str(lower_index))
            #print("upper index: " + str(upper_index))
            
            ihv0_np = np.array(potential_maxes[index]).reshape(6,1)
            self.short_current = np.hstack((self.short_current,ihv0_np))
        
        self.short_current = np.delete(self.short_current,np.arange(0,len(self.short_current[0])-self.short_plot_length),1)

        avg = [0 for i in range(6)]
        with open("../" + self.parameters["CServer_Path"]+"/Voltages_0.txt", "rb") as file:
            try:
                num_lines = 10
                num_chars = 78*num_lines
                file.seek(-num_chars, os.SEEK_END)
                while file.read(1) != b'\n':
                    file.seek(-2, os.SEEK_CUR)
            except OSError:
                file.seek(0)


            for i in range(num_lines):
                line = file.readline().decode()
                temp_vhv0=[float(i)/num_lines for i in line.split(' ')[:-1]]

                for j in range(6):
                    avg[j] += temp_vhv0[j]

            for j in range(6):
                avg[j] = round(avg[j],2)






            
            #line = file.readline().decode()

            #self.voltage=[float(i) for i in line.split(' ')[:-1]]


            if len(avg) == 6:
                self.voltage = np.array(avg).reshape(6,1)
                #self.voltage = np.array(self.voltage).reshape(6,1)

        self.check_overflow()
    

    def update_plot(self):
        self.fig.canvas.restore_region(self.bg)
        self.inv_timestamps = abs(self.timestamps[-1] - self.timestamps) # updates inv_timestamps for better plotting
        
        self.inv_short_timestamps = abs(self.short_timestamps[-1] - self.short_timestamps)

        # update voltage labels
        for i in range(6):
            self.t[i].set_text("Voltage (V): " + str(self.voltage[i][0]))

            self.ax[i][1].draw_artist(self.t[i])

        ## loops through each table and updates the plots accordingly
        for i in range(6):
            self.lns[i][0].set_ydata(self.short_current[i]) # sets the current data for the long term plots (y axis)
            self.lns[i][0].set_xdata(self.inv_short_timestamps) # sets the timestammps for the long term plots (x axis)

            self.ax[i][0].draw_artist(self.lns[i][0])



            self.lns[i][1].set_ydata(self.long_current[i]) # sets the current data for the long term plots (y axis)
            self.lns[i][1].set_xdata(self.inv_timestamps) # sets the timestammps for the long term plots (x axis)
            
            self.ax[i][1].draw_artist(self.lns[i][1])

        #increases speed of readout
        self.fig.canvas.blit(self.fig.bbox)

        # self.fig.canvas.draw()

        # not sure what this does but again necessary for the live plotting
        self.fig.canvas.flush_events()


if __name__=="__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = "127.0.0.1"
    port = 12000
    sock.connect((host,port))

    time.sleep(2)


    qc = QC(45000, 1000)
    
    count = 0
    time_var = time.time()


    while True:
        start_time = time.time()



        try:
            qc.grab_new_values()
            qc.update_plot()
        except KeyboardInterrupt:
            break
        except:
            print("error")

        count+=1

        print(time.time() - start_time)
