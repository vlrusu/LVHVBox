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


HEADER_LENGTH = 10
LVTYPE = 0
HVTYPE0 = 1
HVTYPE1 = 2
BATTERYTYPE = 3



class QC:
    def __init__(self, total_values):
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect(("127.0.0.1",12000))

        self.total_values = total_values


        # initialize current and voltage values
        self.current = np.zeros((6, total_values))
        self.voltage = np.zeros((6, total_values))

        # initialize time stuff
        self.start_time = datetime.now()
        self.timestamps = np.zeros(total_values)
        self.inv_timestamps = np.zeros(total_values)

        self.background = np.empty((12,1))

        # define plotting stuff
        self.fig,self.ax = plt.subplots(6,2,gridspec_kw={'width_ratios':[1,3]})
        plt.grid(visible=True,which='major',axis='x')
        self.lns = [[1 for j in range(2)] for i in range(6)]
        self.lns_v = [1 for i in range(6)]

        # twin axes for voltage plots
        self.vax = [None for i in range(6)]
        for i in range(6):
            self.vax[i] = self.ax[i][1].twinx()

        for i in range(6):
            (self.lns[i][0],) = self.ax[i][0].plot(self.timestamps,self.current[i],'o',animated=True,color='r',markersize=2)
            (self.lns[i][1],) = self.ax[i][1].plot(self.timestamps,self.current[i],'o',animated=True,color='r',markersize=2)
            (self.lns_v[i],) = self.vax[i].plot(self.timestamps,self.voltage[i],'o',animated=True,color='b',markersize=2)


        # plot titles
        for i in range(6):
            self.ax[i][0].set_ylabel(f'Ch{i} Short \n Current (nA)')
            self.ax[i][1].set_ylabel(f'Ch{i} Long \n Current (nA)',color='r')
            self.vax[i].set_ylabel("Voltage (V)",color='b')
        
            

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
            self.ax[i][0].set_ylim(0,200) # max current of short term plot
            self.ax[i][0].set_xlim(0,300) # max time of short term plot in seconds

            self.ax[i][1].set_ylim(0,200) # max current of long term plot
            self.ax[i][1].set_xlim(0,21600) # max time of long term plot in seconds

            self.vax[i].set_ylim(0,2000)
            self.vax[i].set_xlim(0,21600)

    def check_overflow(self):
        #limits max values of arrays to size of display
        # prevents memory overflow on arrays

        if len(self.background) > 20:
            self.background = np.delete(self.background,0)
        if self.current.shape[1] > self.total_values:
            self.current = np.delete(self.current,0,1)
            self.timestamps = np.delete(self.timestamps,0)
        if self.voltage.shape[1] > self.total_values:
            self.voltage = np.delete(self.voltage,0,1)

    def grab_new_values(self):
        new_vhv0=[]
        new_ihv0=[]
        # ----- get vhv0 -----
        vhv0_message = {
            "type" : HVTYPE0,
            "cmdname" : "get_vhv0",
            "args" : [None]
        }
        self.send(vhv0_message)

        vhv0_received = json.loads(str(self.receive_message(self.conn)["data"].decode('utf-8').strip()))['response']

        print
        for i in range(6):
            new_vhv0.append(round(vhv0_received[i],1))




        # ----- get ihv0 -----
        ihv0_message = {
            "type" : HVTYPE0,
            "cmdname" : "get_ihv0",
            "args" : [None]
        }
        self.send(ihv0_message)

        ihv0_received = json.loads(str(self.receive_message(self.conn)["data"].decode('utf-8').strip()))['response']


        for i in range(6):
            new_ihv0.append(round(ihv0_received[i],1))




        #self.background = np.hstack((self.background,new_ihv0))


        ihv0_np = np.array(new_ihv0).reshape(6,1)
        vhv0_np = np.array(new_vhv0).reshape(6,1)
        self.current = np.hstack((self.current,ihv0_np)) # adds readout information to end of current array
        self.voltage = np.hstack((self.voltage,vhv0_np))
        event_time = datetime.now() # grabs current time
        delta_t = float((event_time-self.start_time).total_seconds()) # finds time passed since start of code
        self.timestamps = np.append(self.timestamps,delta_t) # adds timestamp of current value to timestamps array

        self.check_overflow()
    

    def update_plot(self):
        self.fig.canvas.restore_region(self.bg)
        self.inv_timestamps = abs(self.timestamps[-1] - self.timestamps) # updates inv_timestamps for better plotting
        



        ## loops through each table and updates the plots accordingly
        for i in range(6):
            self.lns[i][0].set_ydata(self.current[i]) # sets the current data for the long term plots (y axis)
            self.lns[i][0].set_xdata(self.inv_timestamps) # sets the timestammps for the long term plots (x axis)
            
            #self.ax[i][0].draw_artist(self.current[i])
            #self.ax[i][0].draw_artist(self.lns[i][0])
            self.ax[i][0].draw_artist(self.lns[i][0])



            self.lns[i][1].set_ydata(self.current[i]) # sets the current data for the long term plots (y axis)
            self.lns[i][1].set_xdata(self.inv_timestamps) # sets the timestammps for the long term plots (x axis)
            
            #self.ax[i][1].draw_artist(self.current[i])
            #self.ax[i][1].draw_artist(self.lns[i][1])
            self.ax[i][1].draw_artist(self.lns[i][1])


            self.lns_v[i].set_ydata(self.voltage[i])
            self.lns_v[i].set_xdata(self.inv_timestamps)

            self.vax[i].draw_artist(self.lns_v[i])


        #increases speed of readout
        self.fig.canvas.blit(self.fig.bbox)

        # self.fig.canvas.draw()

        # not sure what this does but again necessary for the live plotting
        self.fig.canvas.flush_events()


if __name__=="__main__":
    qc = QC(45000)
    
    count = 0
    time_var = time.time()
    while True:
        qc.grab_new_values()
        qc.update_plot()

        count+=1
        print(str(count) + ": " + str(qc.current[0]))
        print(str(time.time() - time_var))
        time_var = time.time()



