from tqdm.auto import tqdm
import os
from ctypes import *
import time
import threading
import RPi.GPIO as GPIO
from RPiMCP23S17.MCP23S17 import MCP23S17
import smbus
from smbus import SMBus


NCHANNELS = 6

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
    def __init__ (self,cmdapp,ser1,ser2):

        self.ser1 = ser1
        self.ser2 = ser2

        
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


        rampup = "/home/pi/LVHVBox/control_gui/python_connect.so"
        self.rampup=CDLL(rampup)
        self.rampup.initialization()
        
        self.cmdapp = cmdapp
    

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



    def readvoltage(self,channel):

        ret = []




        if channel[0] == None:
            for ich in range(NCHANNELS):
                self.bus.write_byte_data(0x50,0x0,ich+1)# first is the coolpac
                reading=self.bus.read_byte_data(0x50,0xD0)
                reading=self.bus.read_i2c_block_data(0x50,0x8B,2)
                value = float(reading[0]+256*reading[1])/256.

                ret.append(value)

        else:
            self.bus.write_byte_data(0x50,0x0,channel[0]+1)# first is the coolpac
            reading=self.bus.read_byte_data(0x50,0xD0)
            reading=self.bus.read_i2c_block_data(0x50,0x8B,2)
            value = float(reading[0]+256*reading[1])/256.

            ret.append(value)


        return ret
