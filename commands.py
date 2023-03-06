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

class LVHVBox:
    def __init__ (self,ser1,ser2,hvlog0, hvlog1 ,lvlog, is_test):

        self.ser1 = ser1
        self.ser2 = ser2
        self.hvlog0 = hvlog0
        self.hvlog1 = hvlog1
        self.lvlog = lvlog
        self.is_test = is_test

        self.ihv0 = [0 for i in range(6)]
        self.ihv1 = [0 for i in range(6)]
        self.vhv0 = [0 for i in range(6)]
        self.vhv1 = [0 for i in range(6)]


        if not self.is_test:
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup(GLOBAL_ENABLE_PIN,GPIO.OUT)
            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
            GPIO.setup(RESET_PIN,GPIO.OUT)
            GPIO.output(RESET_PIN,GPIO.LOW)
            GPIO.output(RESET_PIN,GPIO.HIGH)

            self.mcp = MCP23S17(bus=0x00, pin_cs=0x00, device_id=0x00)

            self.mcp.open()
            self.mcp._spi.max_speed_hz = 10000000

            for x in range(8, 16):
                self.mcp.setDirection(x, self.mcp.DIR_OUTPUT)
                self.mcp.digitalWrite(x, MCP23S17.LEVEL_LOW)




            self.bus = SMBus(1)
            self.bus.pec=1

            # HV manipulating stuff
            rampup = os.getcwd()+"/control_gui/python_connect.so"
            self.rampup=CDLL(rampup)
            self.rampup.initialization()

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
            if not self.is_test:
                voltages = self.readvoltage([None])
                self.v48 = [0]*NLVCHANNELS

                currents = self.readcurrent([None])
                self.i48 = [0]*NLVCHANNELS

                temps = self.readtemp([None])
                self.T48 = [0]*NLVCHANNELS
   

                for ich in range(NLVCHANNELS):
                    self.v48[ich] = voltages[ich]
                    self.i48[ich] = currents[ich]
                    self.T48[ich] = temps[ich]
            else:
                self.v48 = [0]*NLVCHANNELS
                self.i48 = [0]*NLVCHANNELS
                self.T48 = [0]*NLVCHANNELS

                for ich in range(NLVCHANNELS):
                    self.v48[ich] = round(np.random.normal(48,1),2)
                    self.i48[ich] = round(np.random.normal(1,1),2)
                    self.T48[ich] = round(np.random.normal(22,1),2)
                
                voltages = self.v48
                currents = self.i48
                temps = self.T48

            self.lvlog.write(str(datetime.now().strftime("%Y:%m:%d-%H:%M:%S ")))
            self.lvlog.write(" ".join(str(e) for e in voltages))
            self.lvlog.write(" ")
            self.lvlog.write(" ".join(str(e) for e in currents))
            self.lvlog.write(" ")
            self.lvlog.write(" ".join(str(e) for e in temps))
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
            if not self.is_test:
                line2 = self.ser2.readline().decode('ascii')

                if line2.startswith("Trip"):
                    logging.error(line2)
                    return 0

                d2 = line2.split()
                if (len(d2) != HVSERIALDATALENGTH):
                    logging.error('HV data from serial not the right length')
                    logging.error(line2)
                    return 0

                if (d2[6] != "|" or d2[13] != "|" or d2[15]!= "|" or d2[17]!= "|"):
                    logging.error('HV data from serial is not the right format')
                    logging.error(line1)
                    return 0

                hvlist = []
                self.ihv1 = [0]*NHVCHANNELS
                self.vhv1 = [0]*NHVCHANNELS
                for ich in range(6):
                    self.ihv1[ich] = float(d2[5-ich])
                    self.vhv1[ich] = float(d2[12-ich])
                    hvlist.append(self.ihv1[ich])
                    hvlist.append(self.vhv1[ich])

                self.hvpcbtemp = float(d2[14])
                hvlist.append(self.hvpcbtemp)
            else:
                hvlist = []
                self.ihv1 = [0]*NHVCHANNELS
                self.vhv1 = [0]*NHVCHANNELS
                for ich in range(6):
                    self.ihv1[ich] = round(np.random.normal(3,0.2),2)
                    self.vhv1[ich] = round(np.random.normal(48,0.25),2)
                    hvlist.append(self.ihv1[ich])
                    hvlist.append(self.vhv1[ich])

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
            if not self.is_test:
                line1 = self.ser1.readline().decode('ascii')

                if line1.startswith("Trip"):
                    logging.error(line1)
                    return 0
                d1 = line1.split()
                if (len(d1) != HVSERIALDATALENGTH):
                    logging.error('HV data from serial not the right length')
                    logging.error(line1)
                    return 0

                if (d1[6] != "|" or d1[13] != "|" or d1[15]!= "|" or d1[17]!= "|"):
                    logging.error('HV data from serial not right format')
                    logging.error(line1)
                    return 0

                hvlist = []
                self.ihv0 = [0]*NHVCHANNELS
                self.vhv0 = [0]*NHVCHANNELS
                for ich in range(6):
                    self.ihv0[ich] = float(d1[5-ich])
                    self.vhv0[ich] = float(d1[12-ich])
                    hvlist.append(self.ihv0[ich])
                    hvlist.append(self.vhv0[ich])

                self.i12V = float(d1[14])
                hvlist.append(self.i12V)
            else:
                hvlist = []
                self.ihv0 = [0]*NHVCHANNELS
                self.vhv0 = [0]*NHVCHANNELS
                for ich in range(6):
                    self.ihv0[ich] = round(np.random.normal(3,0.2),2)
                    self.vhv0[ich] = round(np.random.normal(48,0.25),2)

                    hvlist.append(self.ihv0[ich])
                    hvlist.append(self.vhv0[ich])


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
        
    def get_v48(self,channel):
        try:
            if channel[0] is not None:
                return self.v48[channel[0]]
            else:
                return self.v48
        except:
            return False
    
    def get_i48(self,channel):
        try:
            if channel[0] is not None:
                return self.i48[channel[0]]
            else:
                return self.i48
        except:
            return False
    
    def get_T48(self,channel):
        try:
            if channel[0] is not None:
                return self.T48[channel[0]]
            else:
                return self.T48
        except:
            return False
    
    def get_ihv0(self,channel):
        try:
            if channel[0] is not None:
                return self.ihv0[channel[0]]
            else:
                return self.ihv0
        except:
            return False
    
    def get_ihv1(self,channel):
        try:
            if channel[0] is not None:
                return self.ihv0[channel[0]-5]
            else:
                return self.ihv0
        except:
            return False
    
    def get_vhv0(self,channel):
        try:
            if channel[0] is not None:
                return self.vhv0[channel[0]-5]
            else:
                return self.vhv0
        except:
            return False

    
    def get_vhv1(self,channel):
        try:
            if channel[0] is not None:
                return self.vhv1[channel[0]-5]
            else:
                return self.vhv1
        except:
            return False
    
    def get_all_data(self,channel):
        ret = {}
        try:
            ret['v48']=self.get_v48(channel)
            ret['i48']=self.get_i48(channel)
            ret['T48']=self.get_T48(channel)
            ret['ihv0']=self.get_ihv0(channel)
            ret['ihv1']=self.get_ihv1(channel)
            ret['vhv0']=self.get_vhv0(channel)
            ret['vhv1']=self.get_vhv1(channel)
        except:
            ret='data access error'

        return ret





    ## ===========================================
    ## HV manipulating commands
    ## ===========================================

    # Ramp up
    # =======
    # 'rampHV()' calls inside 'ramphvup()' which exists in 'control_gui' and also includes corrections
    # such that the input and ramped up voltages match at 1450 V

    # ramphvup()
    def ramphvup(self,channel,voltage):
        hvlock.acquire()

        if (channel == 0):
            alpha = 0.9055
        elif (channel == 1):
            alpha = 0.9073
        elif (channel == 2):
            alpha = 0.9051
        elif (channel == 3):
            alpha = 0.9012
        elif (channel == 4):
            alpha = 0.9012
        elif (channel == 5):
            alpha = 0.9034
        elif (channel == 6):
            alpha = 0.9009
        elif (channel == 7):
            alpha = 0.9027
        elif (channel == 8):
            alpha = 0.8977
        elif (channel == 9):
            alpha = 0.9012
        elif (channel == 10):
            alpha = 0.9015
        elif (channel == 11):
            alpha = 1.0  # BURNED BOARD - FIX ME!!
        else:

            hvlock.release()
            return "Select an HV channel from 0 to 11!"


        self.rampup.rampup_hv.argtypes = [c_int , c_float]
        self.rampup.rampup_hv(channel,alpha*voltage)

        hvlock.release()
        return ("HV channel " + str(channel) + " done ramping " + " to " + str(voltage) + "V")

    # rampHV()
    def rampHV(self,arglist):
        """ VADIM'S COMMENT: spi linux driver is thread safe but the exteder operations are not. However, I
        only need to worry about the HV, since other LV stuff is on different pins and the MCP writes should
        not affect them"""
        rampThrd = threading.Thread(target=self.ramphvup,args=(arglist[0],arglist[1]))
        rampThrd.start()
        return 0


    # Set voltage
    # ===========
    # Similarly, 'setHV()' and 'downHV()' use 'sethv()' in 'controlgui'
    # to set an arbitrary voltage or turn off HV to zero, respectively

    # sethv()
    def sethv(self,channel,voltage):
        hvlock.acquire()

        if (channel == 0):
            alpha = 0.9055
        elif (channel == 1):
            alpha = 0.9073
        elif (channel == 2):
            alpha = 0.9051
        elif (channel == 3):
            alpha = 0.9012
        elif (channel == 4):
            alpha = 0.9012
        elif (channel == 5):
            alpha = 0.9034
        elif (channel == 6):
            alpha = 0.9009
        elif (channel == 7):
            alpha = 0.9027
        elif (channel == 8):
            alpha = 0.8977
        elif (channel == 9):
            alpha = 0.9012
        elif (channel == 10):
            alpha = 0.9015
        elif (channel == 11):
            alpha = 1.0  # BURNED BOARD - FIX ME!!
        else:

            hvlock.release()
            return  "Select an HV channel from 0 to 11!"

        self.rampup.set_hv.argtypes = [c_int , c_float]
        self.rampup.set_hv(channel,alpha*voltage) #FIXME why does it need int on lvhvbox.py???
        #I changed the python connect as well. Must be some mem alignemnt issue

        hvlock.release()
        return "HV channel " + str(channel) + " set " + " to " + str(voltage) + " V"

    # downHV()
    def downHV(self,arglist):
        """ VADIM'S COMMENT: spi linux driver is thread safe but the exteder operations are not. However, I
        only need to worry about the HV, since other LV stuff is on different pins and the MCP writes should
        not affect them"""
        rampThrd = threading.Thread(target=self.sethv,args=(arglist[0],0))
        rampThrd.start()
        return 0


    # setHV()
    def setHV(self,arglist):
        """ VADIM'S COMMENT: spi linux driver is thread safe but the exteder operations are not. However, I
        only need to worry about the HV, since other LV stuff is on different pins and the MCP writes should
        not affect them"""
        rampThrd = threading.Thread(target=self.sethv,args=(arglist[0],arglist[1]))
        rampThrd.start()
        return 0


    # Reset HV serial
    # ===============
    # Use only in case of trip. Receives as an argument a serial port index
    # -> 0: serial 1
    # -> 1: serial 2

    def resetHV(self,arglist):
        if arglist[0] == 0:
            self.ser1.write(str.encode('R'))
        else:
            self.ser2.write(str.encode('R'))
        return 0


    # Set HV trip
    # ===========
    # Set a trip treshold in nA

    def setHVtrip(self,arglist):
        #cmd = "T"+str(arglist[1]) #T100 changes trip point to 100nA
        cmd = "T"
        if arglist[0] == 0:
            self.ser1.write(str.encode(cmd))
        else:
            self.ser2.write(str.encode(cmd))

        cmd = str(arglist[1]) + "\r\n"
        if arglist[0] == 0:
            self.ser1.write(str.encode(cmd))
        else:
            self.ser2.write(str.encode(cmd))

        return 0


    def getHVvoltages(self,arglist):
        if arglist[0] == 0:
            ret=[self.vhv0,0]
        elif arglist[0] == 1:
            ret=[self.vhv1,1]
        else:
            return "Please select proper pico"

        return ret


    def getHVcurrents(self,arglist):
        if arglist[0] == 0:
            try:
                ret=[self.ihv0,0]
            except:
                ret=[0 for i in range(6)]
        elif arglist[0] == 1:
            try:
                ret=[self.ihv1,0]
            except:
                ret=[0 for i in range(6)]
        else:
            return "Please select proper pico"

        return ret



    ## ===========================================
    ## LV manipulating commands
    ## ===========================================

    # Turn on LV channel
    # ==================
    def powerOn(self,channel):


        if channel[0] ==  None:
            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
            for ich in range(0,6):
                self.mcp.digitalWrite(ich+8, MCP23S17.LEVEL_HIGH)
        else:
            ch = abs(channel[0])
#            self.bus.write_byte_data(0x50,0x0,ch+1)
#            self.bus.write_byte_data(0x50,0x01,0x80)

            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
            self.mcp.digitalWrite(ch+8, MCP23S17.LEVEL_HIGH)

        return 0


    # Enable LV channel
    # ==================
    def enable(self,channel):


        self.bus.write_byte_data(0x50,0x0,channel+1)
        self.bus.write_byte_data(0x50,0x01,0x80)

        return 0


    # Disable LV channel
    # ==================
    def disable(self,channel):


        self.bus.write_byte_data(0x50,0x0,channel+1)
        self.bus.write_byte_data(0x50,0x01,0x0)

        return 0



    # Turn off LV channel
    # ===================
    def powerOff(self,channel):



        if channel[0] ==  None:
            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
            for ich in range(0,6):
                self.mcp.digitalWrite(ich+8, MCP23S17.LEVEL_LOW)
        else:
            ch = abs(channel[0])
 #           self.bus.write_byte_data(0x50,0x0,ch+1)
 #           self.bus.write_byte_data(0x50,0x01,0x0)

            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW) #if this is off, the I2C bus commands are disabled. At least that's what it seems... Need to look more into it
            self.mcp.digitalWrite(ch+8, MCP23S17.LEVEL_LOW)

        return 0



    # Read LV channel voltage
    # =======================
    def readvoltage(self,channel):

        ret= []
        try:
            if channel[0] == None:
                for ich in range(NLVCHANNELS):
                    self.bus.write_byte_data(0x50,0x0,ich+1)
                    reading=self.bus.read_byte_data(0x50,0xD0)
                    reading=self.bus.read_i2c_block_data(0x50,0x8B,2)
                    value = float(reading[0]+256*reading[1])/256.
                    ret.append(value)
            else:
                self.bus.write_byte_data(0x50,0x0,channel[0]+1)
                reading=self.bus.read_byte_data(0x50,0xD0)
                reading=self.bus.read_i2c_block_data(0x50,0x8B,2)
                value = float(reading[0]+256*reading[1])/256.
                ret.append(value)

        except:
            logging.error("I2C reading error")

        return ret


    # Read LV channel current
    # =======================
    def readcurrent(self,channel):
        ret = []

        try:
            if channel[0] == None:
                for ich in range(NLVCHANNELS):
                    self.bus.write_byte_data(0x50,0x0,ich+1)
                    reading=self.bus.read_byte_data(0x50,0xD0)
                    reading=self.bus.read_i2c_block_data(0x50,0x8C,2)
                    value = reading[0]+256*reading[1]
                    exponent = ( value >> 11 ) & 0x1f
                    exponent = exponent-32
                    mantissa = value & 0x7ff
                    current = mantissa*2**exponent
                    ret.append(current)
            else:
                self.bus.write_byte_data(0x50,0x0,channel[0]+1)
                reading=self.bus.read_byte_data(0x50,0xD0)
                reading=self.bus.read_i2c_block_data(0x50,0x8C,2)
                value = reading[0]+256*reading[1]
                exponent = ( value >> 11 ) & 0x1f
                exponent = exponent-32
                mantissa = value & 0x7ff
                current = mantissa*2**exponent
                ret.append(current)
        except:
            logging.error("I2C reading error")

        return ret


    # Read LV channel temperature
    # ===========================
    def readtemp(self,channel):
        ret = []

        try:
            if channel[0] == None:
                for ich in range(NLVCHANNELS):
                    self.bus.write_byte_data(0x50,0x0,ich+1)  # first is the coolpac
                    reading=self.bus.read_byte_data(0x50,0xD0)
                    reading=self.bus.read_i2c_block_data(0x50,0x8D,2)
                    value = reading[0]+256*reading[1]
                    exponent = ( value >> 11 ) & 0x1f
                    mantissa = value & 0x7ff
                    temp = mantissa*2**exponent
                    ret.append(temp)
            else:
                self.bus.write_byte_data(0x50,0x0,channel[0]+1)
                reading=self.bus.read_byte_data(0x50,0xD0)
                reading=self.bus.read_i2c_block_data(0x50,0x8D,2)
                value = reading[0]+256*reading[1]
                exponent = ( value >> 11 ) & 0x1f
                mantissa = value & 0x7ff
                temp = mantissa*2**exponent
                ret.append(temp)

        except:
            logging.error("I2C reading error")

        return ret


    # Test function from early times?
    #def test(self,channel):
    #     ret = []
    #     print(channel)
    #     if channel[0] == None:
    #         for i in range(NLVCHANNELS):
    #             ret.append(i)
    #     else:
    ##        for i in range(10):
    # #            app.async_alert("Testing " + str(i))
    # #            time.sleep(1)
    #         if channel[1] == True:
    #             ret.append(channel[0])
    #        else:
    #            ret.append(-channel[0])
    #    return ret
