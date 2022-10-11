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



NCHANNELS = 6
NHVCHANNELS=12
HVSERIALDATALENGTH  = 20

# def test(channel):
    
#     ret = []
    
#     if channel[0] == None:
#         for i in range(NCHANNELS):
#             ret.append(i)

#     else:
#         ret.append(channel[0])

#     return ret

hvlock = threading.Lock()

I2C_sleep_time = 0.5 # seconds to sleep between each channel reading

max_reading = 8388608.0
vref = 3.3 #this is only for the second box
V5DIVIDER = 10

pins = ["P9_15","P9_15","P9_15","P9_27","P9_41","P9_12"]
GLOBAL_ENABLE_PIN =  15
RESET_PIN = 32

addresses = [0x14,0x16,0x26]


class LVHVBox:
    def __init__ (self,cmdapp,ser1,ser2,hvlog,lvlog):

        self.ser1 = ser1
        self.ser2 = ser2
        self.hvlog = hvlog
        self.lvlog = lvlog
        
        self.mcp = MCP23S17(bus=0x00, pin_cs=0x00, device_id=0x00)

        self.mcp.open()
        self.mcp._spi.max_speed_hz = 10000000

        for x in range(8, 16):
            self.mcp.setDirection(x, self.mcp.DIR_OUTPUT)
            self.mcp.digitalWrite(x, MCP23S17.LEVEL_LOW)

        self.bus = SMBus(1)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(GLOBAL_ENABLE_PIN,GPIO.OUT)
        GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
        GPIO.setup(RESET_PIN,GPIO.OUT)
        GPIO.output(RESET_PIN,GPIO.HIGH)


        rampup = "/home/mu2e/LVHVBox/control_gui/python_connect.so"
        self.rampup=CDLL(rampup)
        self.rampup.initialization()
        
        self.cmdapp = cmdapp

        logging.basicConfig(filename='lvhvbox.log',format='%(asctime)s %(message)s',encoding='utf-8',level=logging.DEBUG)
        
        token = "0K7grsktz-6TCb3PRlieKXpfy_ZRTxtjXgh0GciQ7N5d0sjv9Dc6Ao2gkIMo-erNGVohdv7Aseq5UXqXbisXpw=="
        self.org = "MU2E"
        self.bucket = "TESTTRACKER"

        self.client = InfluxDBClient(url="http://raspberrypi.local:8086", token=token, org=self.org)

        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)


    def __del__(self):
#        self.client.close()
        self.hvlog.close()
        self.lvlog.close()


    def loglvdata(self):

    # this has to use the commands in commands.py to read: voltages, currents, temps and whatever else we put in GUI
#    lvlog.write("1 2 3\n")
        voltages = self.readvoltage([None])
        self.v48 = [0]*NCHANNELS
        for ich in range(NCHANNELS):
            self.v48[ich] = voltages[ich]

        self.lvlog.write(" ".join(str(e) for e in  voltages))
        self.lvlog.write("\n")
        self.lvlog.flush()

        point = Point("lvdata") \
            .tag("user", "vrusu") \
            .field("v48_0", self.v48[0]) \
            .field("v48_1", self.v48[1]) \
            .field("v48_2", self.v48[2]) \
            .field("v48_3", self.v48[3]) \
            .field("v48_4", self.v48[4]) \
            .field("v48_5", self.v48[5]) \
            .time(datetime.utcnow(), WritePrecision.NS)

        self.write_api.write(self.bucket, self.org, point)


        
    def loghvdata(self):

        line1 = self.ser1.readline().decode('ascii')
        line2 = self.ser2.readline().decode('ascii')

        d1 = line1.split()
        if (len(d1) != HVSERIALDATALENGTH):
            logging.error('HV data from serial not the right length')
            logging.error(line1)
            return 0
        if (d1[6] != "|" or d1[13] != "|" or d1[15]!= "|" or d1[17]!= "|"):
            logging.error('HV data from serial not right format')
            logging.error(line1)
            return 0

        d2 = line2.split()
        if (len(d2) != HVSERIALDATALENGTH):
            logging.error('HV data from serial not the right length')
            logging.error(line2)
            return 0

        if (d2[6] != "|" or d2[13] != "|" or d2[15]!= "|" or d2[17]!= "|"):
            logging.error('HV data from serial not right format')
            logging.error(line1)
            return 0

        hvlist = []
        self.ihv = [0]*NHVCHANNELS
        self.vhv = [0]*NHVCHANNELS
        for ich in range(6):
            self.ihv[ich] = float(d1[5-ich])
            self.vhv[ich] = float(d1[12-ich])
            self.ihv[ich+6] = float(d2[5-ich])
            self.vhv[ich+6] = float(d2[12-ich])
            hvlist.append(self.ihv[ich])
            hvlist.append(self.vhv[ich])
            hvlist.append(self.ihv[ich+6])
            hvlist.append(self.vhv[ich+6])
            
        self.i12V = float(d1[14])
        hvlist.append(self.i12V)
        
        self.hvpcbtemp = float(d2[14])        
        hvlist.append(self.hvpcbtemp)
        
        
        self.hvlog.write(" ".join(str(e) for e in hvlist))
        self.hvlog.write("\n")
        self.hvlog.flush()
        
        point = Point("hvdata3") \
            .tag("user", "vrusu") \
            .field("ihv0", self.ihv[0]) \
            .field("vhv0", self.vhv[0]) \
            .field("ihv1", self.ihv[1]) \
            .field("vhv1", self.vhv[1]) \
            .field("ihv2", self.ihv[2]) \
            .field("vhv2", self.vhv[2]) \
            .field("ihv3", self.ihv[3]) \
            .field("vhv3", self.vhv[3]) \
            .field("ihv4", self.ihv[4]) \
            .field("vhv4", self.vhv[4]) \
            .field("ihv5", self.ihv[5]) \
            .field("vhv5", self.vhv[5]) \
            .field("ihv6", self.ihv[6]) \
            .field("vhv6", self.vhv[6]) \
            .field("ihv7", self.ihv[7]) \
            .field("vhv7", self.vhv[7]) \
            .field("ihv8", self.ihv[8]) \
            .field("vhv8", self.vhv[8]) \
            .field("ihv9", self.ihv[9]) \
            .field("vhv9", self.vhv[9]) \
            .field("ihv10", self.ihv[10]) \
            .field("vhv10", self.vhv[10]) \
            .field("ihv11", self.ihv[11]) \
            .field("vhv11", self.vhv[11]) \
            .field("i12V", self.i12V) \
            .field("hvpcbtemp", self.hvpcbtemp) \
            .time(datetime.utcnow(), WritePrecision.NS)

        self.write_api.write(self.bucket, self.org, point)

        

    def ramphvupdown(self,channel,rampitup):
        hvlock.acquire()
        if rampitup == True:
            self.rampup.rampup_hv(channel,1500)
        else:
            self.rampup.rampup_hv(channel,0)
        #        for i in tqdm(range(10)):
#            time.sleep(3)

        self.cmdapp.async_alert('Channel '+str(channel)+' done ramping')
        hvlock.release()
        
        
    def ramp(self,arglist):
        """spi linux driver is thread safe but the exteder operations are not. However, I 
        only need to worry about the HV, since other LV stuff is on different pins and the MCP writes should 
        not affect them"""

        rampThrd = threading.Thread(target=self.ramphvupdown,args=(arglist[0],arglist[1]))
        rampThrd.start()
        return [0]

    def resetHV(self,arglist):
        if arglist[0] == 0:
            self.ser1.write(str.encode('R'))
        else:
            self.ser2.write(str.encode('R'))

        return [0]
        
        
    def setHVtrip(self,arglist):
#        cmd = "T"+str(arglist[1]) #T100 changes trip point to 100nA
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

        return [arglist[0],arglist[1]]
        
    
    def powerOn(self,channel):
        ret = []
        if channel[0] ==  None:
            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
            for ich in range(0,6):
                self.self.mcp.digitalWrite(ich+8, MCP23S17.LEVEL_HIGH)
        else:
             ch = abs (channel[0])
             GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
             self.mcp.digitalWrite(ch+8, MCP23S17.LEVEL_HIGH)
        return ret
        
        
    def powerOff(self,channel):
        ret = []
        if channel[0] ==  None:
            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
            for ich in range(0,6):
                self.self.mcp.digitalWrite(ich+8, MCP23S17.LEVEL_LOW)
        else:
             ch = abs (channel[0])
             GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
             self.mcp.digitalWrite(ch+8, MCP23S17.LEVEL_LOW)
        return ret
        
        
    def test(self,channel):
        ret = []
        print(channel)
        if channel[0] == None:
            for i in range(NCHANNELS):
                ret.append(i)
        else:
    #        for i in range(10):
    #            app.async_alert("Testing " + str(i))
    #            time.sleep(1)
            if channel[1] == True:
                ret.append(channel[0])
            else:
                ret.append(-channel[0])
        return ret



    ## readvoltage()
    ## =============
    def readvoltage(self,channel):

        ret = []
        if channel[0] == None:
            for ich in range(NCHANNELS):
                self.bus.write_byte_data(0x50,0x0,ich+1)  # first is the coolpac
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

        return ret
    
    
    ## readcurrent()
    ## =============
    def readcurrent(self,channel):

        ret = []
        if channel[0] == None:
            for ich in range(NCHANNELS):
                self.bus.write_byte_data(0x50,0x0,ich+1)  # first is the coolpac
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

        return ret
    
    
    ## readtemp()
    ## ==========
    def readtemp(self,channel):

        ret = []
        if channel[0] == None:
            for ich in range(NCHANNELS):
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

        return ret
