import matplotlib.pyplot as plt
import cmd2
import json
import readline
import os
import atexit
import threading
import socket
import time

import numpy as np
import math

HEADER_LENGTH = 10
LVTYPE = 0
HVTYPE0 = 1
HVTYPE1 = 2
BATTERYTYPE = 3

class QC:
    def __init__(self):
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect(("127.0.0.1",12000))

        self.vhv0 = [-100 for i in range(6)]
        self.ihv0 = [-100 for i in range(6)]

        self.vhv0_short = [[-100 for i in range(80)] for j in range(6)]
        self.ihv0_short = [[-100 for i in range(80)] for j in range(6)]

        self.vhv0_long = [[-100 for i in range(5760)] for j in range(6)]
        self.ihv0_long = [[-100 for i in range(5760)] for j in range(6)]

        self.ax_short = []
        self.ax_long = []
        self.ax_long_voltage = []

        #self.short_time = [-5*i/60 for i in range(60)]
        #self.long_time = [-5*i/60 for i in range(4320)]
        self.short_time = list(1/20*i for i in list(range(80)))
        self.long_time = list(1/20*i for i in list(range(5760)))

        self.short_plots=[]
        self.long_plots=[]
        self.long_plots_voltage=[]

        self.short_plots_time=[]
        self.long_plots_time=[]

        self.newest_time = time.time()
    
    def send(self,data):
        serialized = json.dumps(data)
        msg = f"{len(serialized):<{HEADER_LENGTH}}"

        self.socket.send(bytes(msg+serialized,"utf-8"))
    
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
        


    def update_data(self):

        # ----- get vhv0 -----
        vhv0_message = {
            "type" : HVTYPE0,
            "cmdname" : "get_vhv0",
            "args" : [None]
        }
        self.send(vhv0_message)

        vhv0_received = json.loads(str(self.receive_message(self.conn)["data"].decode('utf-8').strip()))['response']

        for i in range(6):
            self.vhv0[i] = round(vhv0_received[i],1)



        # ----- get ihv0 -----
        ihv0_message = {
            "type" : HVTYPE0,
            "cmdname" : "get_ihv0",
            "args" : [None]
        }
        self.send(ihv0_message)

        ihv0_received = json.loads(str(self.receive_message(self.conn)["data"].decode('utf-8').strip()))['response']


        for i in range(6):
            self.ihv0[i] = round(ihv0_received[i],1)



        # update short term voltage
        for i in range(len(self.vhv0_short)):
            self.vhv0_short[i] = [self.vhv0[i]] + self.vhv0_short[i][:-1]
        
        # update short term current
        for i in range(len(self.ihv0_short)):
            self.ihv0_short[i] = [self.ihv0[i]] + self.ihv0_short[i][:-1]
        
        # update long term current
        for i in range(len(self.ihv0_long)):
            self.ihv0_long[i] = [self.ihv0[i]] + self.ihv0_long[i][:-1]

        # update long term voltage
        for i in range(len(self.vhv0_long)):
            self.vhv0_long[i] = [self.vhv0[i]] + self.vhv0_long[i][:-1]

        # update short times
        for i in range(len(self.short_time)):
            self.short_time[i] += (time.time() - self.newest_time)/60
        self.short_time = [0] + self.short_time[:-1]

        # update long times
        for i in range(len(self.long_time)):
            self.long_time[i] += (time.time() - self.newest_time)/60
        self.long_time = [0] + self.long_time[:-1]

        print(time.time() - self.newest_time)
        self.newest_time = time.time()


        


    def send(self,data):
        serialized = json.dumps(data)
        msg = f"{len(serialized):<{HEADER_LENGTH}}"

        self.conn.send(bytes(msg+serialized,"utf-8"))
    
    def update_short(self):
        while True:
            try:
                qc.update_data()

                for channel in range(6):
                    self.short_plots[channel].set_ydata(qc.ihv0_short[channel])

                    self.short_plots[channel].set_xdata(qc.short_time)


                    self.ax_short[channel].set_xlim(self.short_time[0],self.short_time[-1])

                    
                
                figure.canvas.draw()
        

                figure.canvas.flush_events()
                print('update')
            except:
                print("Issue Updating Short")
    
    def update_long(self):
        while True:
            try:
                for channel in range(6):


                    self.long_plots[channel].set_ydata(qc.ihv0_long[channel])
                    self.long_plots_voltage[channel].set_ydata(qc.vhv0_long[channel])
                    
                    self.long_plots[channel].set_xdata(qc.long_time)
                    self.long_plots_voltage[channel].set_xdata(qc.long_time)

                    self.ax_long[channel].set_xlim(self.long_time[0],self.long_time[-1])
                    self.ax_long_voltage[channel].set_xlim(self.long_time[0],self.long_time[-1])

                    
                
                figure.canvas.draw()
        

                figure.canvas.flush_events()
                print('update')
                time.sleep(10)
            except:
                print("Issue Updating Long")
    
    def update_all(self):
        while True:
            try:
                self.update_data()

                for channel in range(6):
                    self.short_plots[channel].set_ydata(qc.ihv0_short[channel])
                    self.long_plots[channel].set_ydata(qc.ihv0_long[channel])
                    self.long_plots_voltage[channel].set_ydata(qc.vhv0_long[channel])

                    self.short_plots[channel].set_xdata(qc.short_time)
                    self.long_plots[channel].set_xdata(qc.long_time)
                    self.long_plots_voltage[channel].set_xdata(qc.long_time)

                    self.ax_short[channel].set_xlim(self.short_time[0],self.short_time[-1])
                    self.ax_long[channel].set_xlim(self.long_time[0],self.long_time[-1])
                    self.ax_long_voltage[channel].set_xlim(self.long_time[0],self.long_time[-1])

                    
                
                figure.canvas.draw()
        

                figure.canvas.flush_events()
                print('update')
                time.sleep(10)
            except:
                print("Issue Updating")
    


if __name__=="__main__":
    qc = QC()

    qc.update_data()

    qc.short_plots = []
    qc.long_plots = []
    qc.long_plots_voltage = []

    qc.short_plots_time = []
    qc.long_plots_time = []

    figure, axis = plt.subplots(6,2)
    figure.tight_layout(pad=1.5)

    for i in range(6):
        temp = axis[i,0]
    
        temp.set_title('Channel ' + str(i) + ' Short Term Plot')
        temp.set_xlabel('Data Point Age (Minutes)')
        temp.set_ylabel('Current (nA)')
        temp.set_ylim(0,200)

        qc.ax_short.append(temp)

        plt_temp, = temp.plot(qc.short_time,qc.ihv0_short[i],'o',markersize=2)


        qc.short_plots.append(plt_temp)
    
    for i in range(6):
        temp = axis[i,1]
        temp.set_title('Channel ' + str(i) + ' Long Term Plot')
        temp.set_xlabel('Data Point Age (Minutes)')
        temp.set_ylabel('Current (nA)', color='b')
        temp.set_ylim(0,200)

        qc.ax_long.append(temp)

        plt_temp, = temp.plot(qc.long_time,qc.ihv0_long[i],'o',markersize=2)

        temp_voltage = temp.twinx()
        temp_voltage.set_ylim(0,2000)
        temp_voltage.set_ylabel('Voltage (V)', color='r')
        plt_temp_voltage, = temp_voltage.plot(qc.long_time,qc.vhv0_long[i], 'o', markersize=2, color='r')
        qc.long_plots_voltage.append(plt_temp_voltage)

        qc.ax_long_voltage.append(temp_voltage)

        qc.long_plots.append(plt_temp)



        

    '''
    plot1 = plt.subplot2grid((3, 3), (0, 0), colspan=2)
    plot2 = plt.subplot2grid((3, 3), (0, 2), rowspan=3, colspan=2)
    plot3 = plt.subplot2grid((3, 3), (1, 0), rowspan=2)
    
    # Using Numpy to create an array x
    x = np.arange(1, 10)
    
    # Plot for square root
    plot2.plot(x, x**0.5)
    plot2.set_title('Square Root')
    
    # Plot for exponent
    plot1.plot(x, np.exp(x))
    plot1.set_title('Exponent')
    '''

    
    # Packing all the plots and displaying them

    update_thread_short = threading.Thread(target=qc.update_short)
    update_thread_short.start()

    update_thread_long = threading.Thread(target=qc.update_long)
    update_thread_long.start()




    plt.show()
