from tqdm.auto import tqdm
import os
from ctypes import *
import time
import threading
import RPi.GPIO as GPIO
from RPiMCP23S17.MCP23S17 import MCP23S17
import smbus
from smbus import SMBus
import logging

from datetime import datetime

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import numpy as np


NLVCHANNELS = 6
NHVCHANNELS = 6
HVSERIALDATALENGTH  = 20

hvlock = threading.Lock()

I2C_sleep_time = 0.5  #seconds to sleep between each channel reading

max_reading = 8388608.0
vref = 3.3  #this is only for the second box
V5DIVIDER = 10

pins = ["P9_15","P9_15","P9_15","P9_27","P9_41","P9_12"]
GLOBAL_ENABLE_PIN =  15
RESET_PIN = 32

addresses = [0x14,0x16,0x26]



## ==========================================================================================
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
##  MAIN CLASS
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
## ==========================================================================================

class LVHVBoxTest:
    def __init__ (self,hvlog0, hvlog1 ,lvlog):

       
        self.hvlog0 = hvlog0
        self.hvlog1 = hvlog1
        self.lvlog = lvlog


        # CMD stuff

        # Logfile stuff
        logging.basicConfig(filename='lvhvbox.log',format='%(asctime)s %(message)s',encoding='utf-8',level=logging.DEBUG)

        # InfluxDB stuff
        token = "TN-Yxqb6EH0slUUdDUqODr5Of0RHkwGX7t9tYPyP5VjLB5Zy2lu3TUzazySH0gaUMyD7oR0UyTfJRTdWDM9aSg=="
        #token = "7orgMug1GuFq2hfpl4PpVLzKi31E-XCbrftF6AWV1t5cwDaRrrAEY7hARL8jN6zPUy2IabTdjOnq_c98IBG-Nw==" Old token
        self.org = "Mu2e"
        self.bucket = "TrackerVST"
        self.client = InfluxDBClient(url="http://trackerpsu1.dhcp.fnal.gov:8086", token=token, org=self.org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)


    def __del__(self):
        # self.client.close()
        self.hvlog0.close()
        self.hvlog1.close()
        self.lvlog.close()



    ## ===========================================
    ## Log LV data
    ## ===========================================

    def loglvdata(self):
        try:
            self.v48 = [0]*NLVCHANNELS
            self.i48 = [0]*NLVCHANNELS
            self.T48 = [0]*NLVCHANNELS

            for ich in range(NLVCHANNELS):
                self.v48[ich] = round(np.random.normal(48,1),2)
                self.i48[ich] = round(np.random.normal(1,1),2)
                self.T48[ich] = round(np.random.normal(22,1),2)

            self.lvlog.write(str(datetime.now().strftime("%Y:%m:%d-%H:%M:%S ")))
            self.lvlog.write(" ".join(str(e) for e in self.v48))
            self.lvlog.write(" ")
            self.lvlog.write(" ".join(str(e) for e in self.i48))
            self.lvlog.write(" ")
            self.lvlog.write(" ".join(str(e) for e in self.T48))
            self.lvlog.write("\n")

            # self.lvlog.write(str(self.mcp._readRegister(MCP23S17.MCP23S17_GPIOA)))
            # self.lvlog.write("\n")
            # self.lvlog.write(str(self.mcp._readRegister(MCP23S17.MCP23S17_GPIOB)))
            # self.lvlog.write("\n")
            self.lvlog.flush()

            point = Point("lvdata") \
                .tag("user", "vrusu") \
                .field("v48_0", self.v48[0]) \
                .field("v48_1", self.v48[1]) \
                .field("v48_2", self.v48[2]) \
                .field("v48_3", self.v48[3]) \
                .field("v48_4", self.v48[4]) \
                .field("v48_5", self.v48[5]) \
                .field("i48_0", self.i48[0]) \
                .field("i48_1", self.i48[1]) \
                .field("i48_2", self.i48[2]) \
                .field("i48_3", self.i48[3]) \
                .field("i48_4", self.i48[4]) \
                .field("i48_5", self.i48[5]) \
                .field("T48_0", self.T48[0]) \
                .field("T48_1", self.T48[1]) \
                .field("T48_2", self.T48[2]) \
                .field("T48_3", self.T48[3]) \
                .field("T48_4", self.T48[4]) \
                .field("T48_5", self.T48[5]) \
                .time(datetime.utcnow(), WritePrecision.NS)

            self.write_api.write(self.bucket, self.org, point)

        
        except:
            logging.error("LV channels logging failed")
        



    ## ===========================================
    ## Log HV data (channels 6 to 11)
    ## ===========================================

    def loghvdata1(self):

        try:
            hvlist = []
            self.ihv1 = [0]*NHVCHANNELS
            self.vhv1 = [0]*NHVCHANNELS
            for ich in range(6):
                hvlist.append(round(np.random.normal(3,0.2),2))
                hvlist.append(round(np.random.normal(48,0.25),2))

            self.hvpcbtemp = round(np.random.normal(22,0.1),2)
            hvlist.append(self.hvpcbtemp)

            self.hvlog1.write(datetime.now().strftime("%Y:%m:%d-%H:%M:%S "))
            self.hvlog1.write(" ".join(str(e) for e in hvlist))
            self.hvlog1.write("\n")

            self.hvlog1.flush()

            point = Point("hvdata2") \
                .tag("user", "vrusu") \
                .field("ihv6", self.ihv1[0]) \
                .field("vhv6", self.vhv1[0]) \
                .field("ihv7", self.ihv1[1]) \
                .field("vhv7", self.vhv1[1]) \
                .field("ihv8", self.ihv1[2]) \
                .field("vhv8", self.vhv1[2]) \
                .field("ihv9", self.ihv1[3]) \
                .field("vhv9", self.vhv1[3]) \
                .field("ihv10", self.ihv1[4]) \
                .field("vhv10", self.vhv1[4]) \
                .field("ihv11", self.ihv1[5]) \
                .field("vhv11", self.vhv1[5]) \
                .field("hvpcbtemp", self.hvpcbtemp) \
                .time(datetime.utcnow(), WritePrecision.NS)

            self.write_api.write(self.bucket, self.org, point)

        
        except:
            logging.error("HV channels 6 to 11 logging failed")
        



    ## ===========================================
    ## Log HV data (channels 0 to 5)
    ## ===========================================

    def loghvdata0(self):

        try:
            hvlist = []
            self.ihv0 = [0]*NHVCHANNELS
            self.vhv0 = [0]*NHVCHANNELS
            for ich in range(6):
                hvlist.append(round(np.random.normal(3,0.2),2))
                hvlist.append(round(np.random.normal(48,0.25),2))


            hvlist.append(round(np.random.normal(50,0.5),2))
            self.hvlog0.write(str(datetime.now().strftime("%Y:%m:%d-%H:%M:%S ")))

            self.hvlog0.write(" ".join(str(e) for e in hvlist))
            self.hvlog0.write("\n")
            self.hvlog0.flush()

            point = Point("hvdata1") \
                .tag("user", "vrusu") \
                .field("ihv0", self.ihv0[0]) \
                .field("vhv0", self.vhv0[0]) \
                .field("ihv1", self.ihv0[1]) \
                .field("vhv1", self.vhv0[1]) \
                .field("ihv2", self.ihv0[2]) \
                .field("vhv2", self.vhv0[2]) \
                .field("ihv3", self.ihv0[3]) \
                .field("vhv3", self.vhv0[3]) \
                .field("ihv4", self.ihv0[4]) \
                .field("vhv4", self.vhv0[4]) \
                .field("ihv5", self.ihv0[5]) \
                .field("vhv5", self.vhv0[5]) \
                .field("i12V", self.i12V) \
                .time(datetime.utcnow(), WritePrecision.NS)

            self.write_api.write(self.bucket, self.org, point)

        except:
            logging.error("HV channels 0 to 5 logging failed")

