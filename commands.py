from tqdm.auto import tqdm
import os
from ctypes import *
import time
import threading
import RPi.GPIO as GPIO
import smbus
from smbus import SMBus
import logging
import spidev
from MCP23S08 import MCP23S08
import struct


from datetime import datetime

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import numpy as np

import control_hv

import rampup
import rampdown


NLVCHANNELS = 6
NHVCHANNELS = 6
HVSERIALDATALENGTH  = 20

hvlock = threading.Lock()

I2C_sleep_time = 0.5  #seconds to sleep between each channel reading

max_reading = 8388608.0
vref = 3.3  #this is only for the second box
V5DIVIDER = 10

pins = ["P9_15","P9_15","P9_15","P9_27","P9_41","P9_12"]
GLOBAL_ENABLE_PIN =  12
RESET_PIN = 13

addresses = [0x14,0x16,0x26]

## ==========================================================================================
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
##  MAIN CLASS
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
## ==========================================================================================

class LVHVBox:
    def __init__ (self,outep0, inep0, outep1, inep1,hvlog0, hvlog1 ,lvlog, is_test):

        self.outep0 = outep0
        self.inep0 = inep0
        self.outep1 = outep1
        self.inep1 = inep1
        self.hvlog0 = hvlog0
        self.hvlog1 = hvlog1
        self.lvlog = lvlog
        self.is_test = is_test

        self.ihv0 = [0 for i in range(6)]
        self.ihv1 = [0 for i in range(6)]
        self.vhv0 = [0 for i in range(6)]
        self.vhv1 = [0 for i in range(6)]

        self.hv_board_current = 0
        self.hv_board_temperature = 0

        self.battery_capacity = 0
        self.battery_voltage = 0

        self.powerChMap = [5,6,7,2,3,4]

        self.hv_ramp_value = 1450

        self.hv_status = [0 for i in range(12)]

        if not self.is_test:
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup(GLOBAL_ENABLE_PIN,GPIO.OUT)
            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
            GPIO.setup(RESET_PIN,GPIO.OUT)
            GPIO.output(RESET_PIN,GPIO.LOW)
            GPIO.output(RESET_PIN,GPIO.HIGH)

            self.mcp = MCP23S08(bus=0x00, pin_cs=0x00, device_id=0x01)

            self.mcp.open()
            self.mcp._spi.max_speed_hz = 10000000

            for x in range(0, 6):
                self.mcp.setDirection(self.powerChMap[x], self.mcp.DIR_OUTPUT)
                self.mcp.digitalWrite(self.powerChMap[x], MCP23S08.LEVEL_LOW)


            self.lvbus = SMBus(3)
            self.batterybus = SMBus(1)

            self.hv_dac = control_hv.initialization()



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

                six_voltages = self.readMonV6([None])
                self.v6 = [0]*NLVCHANNELS

                six_currents = self.readMonI6([None])
                self.i6 = [0]*NLVCHANNELS
                  
                voltages = self.readMonV48([None])
                self.v48 = [0]*NLVCHANNELS

                currents = self.readMonI48([None])
                self.i48 = [0]*NLVCHANNELS

                temps = self.readtemp([None])
                self.T48 = [0]*NLVCHANNELS
   

                for ich in range(NLVCHANNELS):
                    self.v6[ich] = round(six_voltages[ich], 2)
                    self.i6[ich] = round(six_currents[ich], 2)
                    self.v48[ich] = round(voltages[ich], 2)
                    self.i48[ich] = round(currents[ich], 2)
                    self.T48[ich] = round(temps[ich], 2)
                     
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
            self.lvlog.write(" ")
            self.lvlog.write(" ".join(str(e) for e in six_voltages))
            self.lvlog.write(" ")
            self.lvlog.write(" ".join(str(e) for e in six_currents))
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
                .field("v6_0", self.T48[0]) \
                .field("v6_1", self.T48[1]) \
                .field("v6_2", self.T48[2]) \
                .field("v6_3", self.T48[3]) \
                .field("v6_4", self.T48[4]) \
                .field("v6_5", self.T48[5]) \
                .time(datetime.utcnow(), WritePrecision.NS)

            self.write_api.write(self.bucket, self.org, point)

        except:
            logging.error("LV channels logging failed")
    

    ## ===========================================
    ## Log Battery data
    ## ===========================================

    def logbatterydata(self):
        try:
            if not self.is_test:
                self.battery_capacity = self.readBatteryCapacity(None)
                self.battery_voltage = self.readBatteryVoltage(None)
            else:
                self.battery_capacity = round(np.random.normal(80,5),2)
                self.battery_voltage = round(np.random.normal(4,0.3),2)
        except:
            logging.error("Battery logging failed")


    ## ===========================================
    ## Log HV data (channels 6 to 11)
    ## ===========================================    

    def loghvdata1(self):
        try:
            if not self.is_test:
                current_string = 'I'
                voltage_string = 'V'

                currents = []
                voltages = []

                # get currents
                self.outep1.write(current_string)
                from_device = self.inep1.read(24)
                for channel in range(6):
                    v = format(from_device[4*channel + 3], '008b') + format(from_device[4*channel + 2], '008b') + format(from_device[4*channel + 1], '008b') + format(from_device[4*channel], '008b')
                    sign = (-1) ** int(v[0],2)
                    exponent = int(v[1:9],2)-127
                    mantissa = int(v[9::],2)
                    output_value = sign * (1+mantissa*(2**-23)) * 2**exponent
                    currents.append(output_value)
                
                # get voltages
                self.outep1.write(voltage_string)
                from_device = self.inep1.read(24)
                for channel in range(6):
                    v = format(from_device[4*channel + 3], '008b') + format(from_device[4*channel + 2], '008b') + format(from_device[4*channel + 1], '008b') + format(from_device[4*channel], '008b')
                    sign = (-1) ** int(v[0],2)
                    exponent = int(v[1:9],2)-127
                    mantissa = int(v[9::],2)
                    output_value = sign * (1+mantissa*(2**-23)) * 2**exponent
                    voltages.append(output_value)


                hvlist = []
                self.ihv1 = [0]*NHVCHANNELS
                self.vhv1 = [0]*NHVCHANNELS
                for ich in range(6):
                    self.ihv1[ich] = float(currents[ich])
                    self.vhv1[ich] = float(voltages[ich])
                    hvlist.append(self.ihv1[ich])
                    hvlist.append(self.vhv1[ich])

                    self.hv_board_temperature = d2[14]

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

                    self.hv_board_temperature = round(np.random.normal(1,0.2),2)

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
                current_string = 'I'
                voltage_string = 'V'

                currents = []
                voltages = []

                # get currents
                self.outep0.write(current_string)
                from_device = self.inep0.read(24)
                for channel in range(6):
                    v = format(from_device[4*channel + 3], '008b') + format(from_device[4*channel + 2], '008b') + format(from_device[4*channel + 1], '008b') + format(from_device[4*channel], '008b')
                    sign = (-1) ** int(v[0],2)
                    exponent = int(v[1:9],2)-127
                    mantissa = int(v[9::],2)
                    output_value = sign * (1+mantissa*(2**-23)) * 2**exponent
                    currents.append(output_value)
                
                # get voltages
                self.outep0.write(voltage_string)
                from_device = self.inep0.read(24)
                for channel in range(6):
                    v = format(from_device[4*channel + 3], '008b') + format(from_device[4*channel + 2], '008b') + format(from_device[4*channel + 1], '008b') + format(from_device[4*channel], '008b')
                    sign = (-1) ** int(v[0],2)
                    exponent = int(v[1:9],2)-127
                    mantissa = int(v[9::],2)
                    output_value = sign * (1+mantissa*(2**-23)) * 2**exponent
                    voltages.append(output_value)



                hvlist = []
                self.ihv0 = [0]*NHVCHANNELS
                self.vhv0 = [0]*NHVCHANNELS
                for ich in range(6):
                    self.ihv0[ich] = float(currents[ich])
                    self.vhv0[ich] = float(voltages[ich])
                    hvlist.append(self.ihv0[ich])
                    hvlist.append(self.vhv0[ich])

                    #self.hv_board_current = d1[14]

                #self.i12V = float(d1[14])
                hvlist.append(self.i12V)
            else:
                hvlist = []
                self.ihv0 = [0]*NHVCHANNELS
                self.vhv0 = [0]*NHVCHANNELS
                for ich in range(6):
                    self.ihv0[ich] = round(np.random.normal(3,0.2),2)
                    self.vhv0[ich] = round(np.random.normal(48,0.25),2)
                    self.hv_board_current = round(np.random.normal(1,0.1,2))

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
    
    def get_v6(self,channel):
        try:
            if channel[0] is not None:
                return self.v6[channel[0]]
            else:
                return self.v6
        except:
            return False
    
    def get_i6(self,channel):
        try:
            if channel[0] is not None:
                return self.i6[channel[0]]
            else:
                return self.i6
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
                return self.ihv1[channel[0]-5]
            else:
                return self.ihv1
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
    
    def get_hv_board_temperature(self):
        try:
            return self.hv_board_temperature
        except:
            return False
        
    def get_hv_board_current(self):
        try:
            return self.hv_board_current
        except:
            return False
    
    def get_battery_voltage(self):
        try:
            return self.battery_voltage
        except:
            return False
        
    def get_battery_capacity(self):
        try:
            return self.battery_capacity
        except:
            return False
    
    def get_all_hv_status(self):
        try:
            return self.hv_status
        except:
            return False
    
    def get_all_data(self,channel):
        ret = {}
        try:
            ret['v48']=self.get_v48(channel)
            ret['i48']=self.get_i48(channel)
            ret['T48']=self.get_T48(channel)
            ret['v6']=self.get_v6(channel)
            ret['i6']=self.get_v6(channel)
            ret['ihv0']=self.get_ihv0(channel)
            ret['ihv1']=self.get_ihv1(channel)
            ret['vhv0']=self.get_vhv0(channel)
            ret['vhv1']=self.get_vhv1(channel)
            ret['boardtemperature']=self.get_hv_board_temperature()
            ret['boardcurrent']=self.get_hv_board_current()
            ret['batteryvoltage']=self.get_battery_voltage()
            ret['batterycapacity']=self.get_battery_capacity()
            ret['hv_status']=self.get_all_hv_status()


            print(ret)
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
        nsteps = 200

        rampup.rampup(int(channel),voltage,nsteps,self.hv_dac)

        hvlock.release()
        return ("HV channel " + str(channel) + " done ramping " + " to " + str(voltage) + "V")

    # ramphvdown()
    def ramphvdown(self,channel,voltage):
        hvlock.acquire()
        nsteps = 200

        rampdown.rampdown(int(channel), voltage, nsteps, self.hv_dac)
        hvlock.release()

        return ("HV channel " + str(channel) + " done ramping " + " down from " + str(voltage) + "V")

    # rampHV()
    def rampHV(self,arglist):
        """ VADIM'S COMMENT: spi linux driver is thread safe but the exteder operations are not. However, I
        only need to worry about the HV, since other LV stuff is on different pins and the MCP writes should
        not affect them"""
        self.hv_status[int(arglist[0])] = 1
        if int(arglist[1]) == -1:
            rampThrd = threading.Thread(target=self.ramphvup,args=(arglist[0],self.hv_ramp_value))
        else:
            rampThrd = threading.Thread(target=self.ramphvup,args=(arglist[0],arglist[1]))
        rampThrd.start()
        return 0

    # set_hv_value()
    def set_hv_value(self,arglist):
        self.hv_ramp_value = arglist[0]

    # Set voltage
    # ===========
    # Similarly, 'setHV()' and 'downHV()' use 'sethv()' in 'controlgui'
    # to set an arbitrary voltage or turn off HV to zero, respectively

    # sethv()
    def sethv(self,channel,voltage):
        hvlock.acquire()

        control_hv.set_hv(int(channel),voltage,self.hv_dac)

        hvlock.release()
        return "HV channel " + str(channel) + " set " + " to " + str(voltage) + " V"

    # downHV()
    def downHV(self,arglist):
        """ VADIM'S COMMENT: spi linux driver is thread safe but the exteder operations are not. However, I
        only need to worry about the HV, since other LV stuff is on different pins and the MCP writes should
        not affect them"""
        self.hv_status[int(arglist[0])] = 0

        if int(arglist[0]) < 6:
            rampThrd = threading.Thread(target=self.ramphvdown,args=(arglist[0],self.vhv0[int(arglist[0])]))
        else:
            rampThrd = threading.Thread(target=self.ramphvdown,args=(arglist[0],self.vhv1[int(arglist[0]) - 6]))
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
        channel = int(arglist[0])
        
        if channel < 6:
            send_chars = chr(109 + channel)
            self.outep0.write(send_chars)
        else:
            send_chars = chr(109 + channel)
            self.outep1.write(send_chars)
        return 0


    # Set HV trip
    # ===========
    # Set a trip treshold in nA



    def setHVtrip(self,arglist):
        #cmd = "T"+str(arglist[1]) #T100 changes trip point to 100nA
        desired_trip = int(arglist[1])

        binary_trip = format(desired_trip, '#018b')[2::]

        send_chars = chr(83) + chr(int('0b' + binary_trip[0:8], 2)) + chr(int('0b' + binary_trip[8::], 2))
        
        self.outep0.write(send_chars)
        self.outep1.write(send_chars)
        return 0

    def tripHV(self,arglist):
        channel = int(arglist[0])


        if channel < 6:
            send_chars = chr(103 + channel)
            self.outep0.write(send_chars)
        else:
            send_chars = chr(103 + channel - 6)
            self.outep1.write(send_chars)
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

    def get_hv_status(self,arglist):
        channel = int(arglist[0])
        if channel == -1:
            return self.hv_status
        else:
            return self.hv_status[channel]
    
    def set_hv_status(self,arglist):
        channel = int(arglist[0])
        status = int(arglist[1])

        self.hv_status[channel] = status

        return status



    ## ===========================================
    ## LV manipulating commands
    ## ===========================================

    # Turn on LV channel
    # ==================
    def powerOn(self,channel):

        if channel[0] ==  None:
            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
            for ich in range(0,6):
                self.mcp.digitalWrite(self.powerChMap[ich], MCP23S08.LEVEL_HIGH)

        else:
            ch = abs(channel[0])
#            self.bus.write_byte_data(0x50,0x0,ch+1)
#            self.bus.write_byte_data(0x50,0x01,0x80)

            GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
            self.mcp.digitalWrite(self.powerChMap[ch], MCP23S08.LEVEL_HIGH)

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
            GPIO.output(GLOBAL_ENABLE_PIN, GPIO.LOW)
            for ich in range(0,6):
                self.mcp.digitalWrite(self.powerChMap[ich], MCP23S08.LEVEL_LOW)

        else:
            ch = abs(channel[0])
 #           self.bus.write_byte_data(0x50,0x0,ch+1)
 #           self.bus.write_byte_data(0x50,0x01,0x0)

            #GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW) #if this is off, the I2C bus commands are disabled. At least that's what it seems... Need to look more into it
            self.mcp.digitalWrite(self.powerChMap[channel[0]], MCP23S08.LEVEL_LOW)

          

        return 0

    # Read 6V Voltage
    # ===============

    def readMonV6(self,channel):
        ret= []

        addresses = [0x14,0x16,0x26]
        LTCaddress = [0x26,0x26,0x16,0x16,0x14,0x14]
        v48map = [6,0,6,0,6,0]
        v6map = [4,3,4,3,4,3]
        i48map = [7,1,7,1,7,1]
        i6map = [5,2,5,2,5,2]
        v6scale = 0.00857905
        v48scale = 0.0012089
        i6scale = 0.010
        i48scale = 0.010
        acplscale = 8.2

        vref_local=1.24

        try:
            if channel[0] == None:
                for item in range(6):
                    address = LTCaddress[item]
                    index = v6map[item]
                    channelLTC = (0b101<<5) + index
                    self.lvbus.write_byte(address, channelLTC)

                    time.sleep(I2C_sleep_time)
                    reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                    val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                    volts = val*vref_local/max_reading
                    volts = volts/(v6scale*acplscale)  
                    time.sleep(0.2)
                    ret.append(volts)
            else:
                item = channel[0]

                address = LTCaddress[item]
                index = v6map[item]
                channelLTC = (0b101<<5) + index
                self.lvbus.write_byte(address, channelLTC)

                time.sleep(I2C_sleep_time)
                reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                volts = val*vref_local/max_reading
                volts = volts/(v6scale*acplscale)  
                time.sleep(0.2)
                ret.append(volts)
        except:
            logging.error("V48 Reading Error")

        return ret

    # Read 6V Current
    # ===============
    
    def readMonI6(self,channel):
        ret= []

        addresses = [0x14,0x16,0x26]
        LTCaddress = [0x26,0x26,0x16,0x16,0x14,0x14]
        v48map = [6,0,6,0,6,0]
        v6map = [4,3,4,3,4,3]
        i48map = [7,1,7,1,7,1]
        i6map = [5,2,5,2,5,2]
        v6scale = 0.00857905
        v48scale = 0.0012089
        i6scale = 0.010
        i48scale = 0.010
        acplscale = 8.2

        vref_local=1.24

        try:
            if channel[0] == None:
                for item in range(6):
                    address = LTCaddress[item]
                    index = i6map[item]
                    channelLTC = (0b101<<5) + index
                    self.lvbus.write_byte(address, channelLTC)

                    time.sleep(I2C_sleep_time)
                    reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                    val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                    volts = val*vref_local/max_reading
                    volts = volts/(i6scale*acplscale)  
                    time.sleep(0.2)
                    ret.append(volts)
            else:
                item = channel[0]

                address = LTCaddress[item]
                index = i6map[item]
                channelLTC = (0b101<<5) + index
                self.lvbus.write_byte(address, channelLTC)

                time.sleep(I2C_sleep_time)
                reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                volts = val*vref_local/max_reading
                volts = volts/(i6scale*acplscale)  
                time.sleep(0.2)
                ret.append(volts)
        except:
            logging.error("V48 Reading Error")

        return ret

    # Read LV channel voltage
    # =======================
    def readMonV48(self,channel):
        ret= []    

        addresses = [0x14,0x16,0x26]
        LTCaddress = [0x26,0x26,0x16,0x16,0x14,0x14]
        v48map = [6,0,6,0,6,0]
        v6map = [4,3,4,3,4,3]
        i48map = [7,1,7,1,7,1]
        i6map = [5,2,5,2,5,2]
        v6scale = 0.00857905
        v48scale = 0.0012089
        i6scale = 0.010
        i48scale = 0.010
        acplscale = 8.2

        vref_local=1.24

        try:
            if channel[0] == None:
                for item in range(6):
                    address = LTCaddress[item]
                    index = v48map[item]
                    channelLTC = (0b101<<5) + index
                    self.lvbus.write_byte(address, channelLTC)

                    time.sleep(I2C_sleep_time)
                    reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                    val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                    volts = val*vref_local/max_reading
                    volts = volts/(v48scale*acplscale)  
                    time.sleep(0.2)
                    ret.append(volts)
            else:
                item = channel[0]

                address = LTCaddress[item]
                index = v48map[item]
                channelLTC = (0b101<<5) + index
                self.lvbus.write_byte(address, channelLTC)

                time.sleep(I2C_sleep_time)
                reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                volts = val*vref_local/max_reading
                volts = volts/(v48scale*acplscale)  
                time.sleep(0.2)
                ret.append(volts)
        except:
            logging.error("V48 Reading Error")

        return ret


    # Read LV channel current
    # =======================
    def readMonI48(self,channel):
        ret = []

        addresses = [0x14,0x16,0x26]
        LTCaddress = [0x26,0x26,0x16,0x16,0x14,0x14]
        v48map = [6,0,6,0,6,0]
        v6map = [4,3,4,3,4,3]
        i48map = [7,1,7,1,7,1]
        i6map = [5,2,5,2,5,2]
        v6scale = 0.00857905
        v48scale = 0.0012089
        i6scale = 0.010
        i48scale = 0.010
        acplscale = 8.2

        vref_local=1.24



        try:
            if channel[0] == None:
                for item in range(6):
                    address = LTCaddress[item]
                    index = i48map[item]
                    channelLTC = (0b101<<5) + index
                    self.lvbus.write_byte(address, channelLTC)

                    time.sleep(I2C_sleep_time)
                    reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                    val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                    volts = val*vref_local/max_reading
                    volts = volts/(i48scale*acplscale)  
                    time.sleep(0.2)
                    ret.append(volts)

            else:
                item = channel[0]

                address = LTCaddress[item]
                index = i48map[item]
                channelLTC = (0b101<<5) + index
                self.lvbus.write_byte(address, channelLTC)

                time.sleep(I2C_sleep_time)
                reading = self.lvbus.read_i2c_block_data(address, channelLTC, 3)
                val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                volts = val*vref_local/max_reading
                volts = volts/(i48scale*acplscale)  
                time.sleep(0.2)
                ret.append(volts)

        except:
            logging.error("I48 Reading Error")

        return ret
    
    # Read LV Voltage from the blades (dangerous method)
    # ==================================================
    def readvoltage(self,channel):
        ret = []

        try:
            if channel[0] == None:
                for item in range(6):
                    self.lvbus.pec = 1
                    self.lvbus.write_byte_data(0x50,0x0,item+1)
                    reading=self.lvbus.read_i2c_block_data(0x50,0x8B,2)
                    value=float(reading[0]+256*reading[1])/256.
                    self.lvbus.pec = 0
                    time.sleep(0.2)
                    ret.append(value)
            else:
                item = channel[0]

                self.lvbus.pec = 1
                self.lvbus.write_byte_data(0x50,0x0,item+1)
                reading=self.lvbus.read_i2c_block_data(0x50,0x8B,2)
                value=float(reading[0]+256*reading[1])/256.
                self.lvbus.pec = 0
                time.sleep(0.2)
                ret.append(value)
        except:
            logging.error("readvoltage reading error")
        
        return ret


    # Read LV Current from the blades (dangerous method)
    # ==================================================
    def readcurrent(self,channel):
        ret = []

        try:
            if channel[0] == None:
                for item in range(6):
                    self.lvbus.pec = 1
                    self.lvbus.write_byte_data(0x50,0x0,item+1)
                    reading=self.lvbus.read_i2c_block_data(0x50,0x8C,2)
                    value=reading[0]+256*reading[1]
                    exponent=(value >> 11) & 0x1f
                    exponent=exponent-32
                    mantissa=value & 0x7ff
                    current=mantissa*2**exponent
                    self.lvbus.pec = 0
                    time.sleep(0.2)
                    ret.append(current)
            else:
                item = channel[0]

                self.lvbus.pec = 1
                self.lvbus.write_byte_data(0x50,0x0,item+1)
                reading=self.lvbus.read_i2c_block_data(0x50,0x8C,2)
                value=reading[0]+256*reading[1]
                exponent=(value >> 11) & 0x1f
                exponent=exponent-32
                mantissa=value & 0x7ff
                current=mantissa*2**exponent
                self.lvbus.pec = 0
                time.sleep(0.2)
                ret.append(current)
        except:
            logging.error("readvoltage reading error")
        
        return ret


    # Read LV channel temperature
    # ===========================
    def readtemp(self,channel):
        ret = []

        '''
        for ch in range(0,6):
            bus.write_byte_data(0x50,0x0,ch+1)# first is the coolpac
            reading=bus.read_byte_data(0x50,0xD0)
            reading=bus.read_i2c_block_data(0x50,0x8D,2)
            value = reading[0]+256*reading[1]
            exponent = ( value >> 11 ) & 0x1f
            mantissa = value & 0x7ff
            temp = mantissa*2**exponent
            temps.append(temp)
        '''

        try:
            if channel[0] == None:
                for ich in range(NLVCHANNELS):
                    self.lvbus.write_byte_data(0x50,0x0,ich+1)  # first is the coolpac
                    reading=self.lvbus.read_byte_data(0x50,0xD0)
                    reading=self.lvbus.read_i2c_block_data(0x50,0x8D,2)
                    value = reading[0]+256*reading[1]
                    exponent = ( value >> 11 ) & 0x1f
                    mantissa = value & 0x7ff
                    temp = mantissa*2**exponent
                    ret.append(temp)
 
            else:
                self.lvbus.write_byte_data(0x50,0x0,channel[0]+1)
                reading=self.lvbus.read_byte_data(0x50,0xD0)
                reading=self.lvbus.read_i2c_block_data(0x50,0x8D,2)
                value = reading[0]+256*reading[1]
                exponent = ( value >> 11 ) & 0x1f
                mantissa = value & 0x7ff
                temp = mantissa*2**exponent
                ret.append(temp)

        except:
            logging.error("I2C reading error")

        return ret

    # read battery capacity
    # =====================
    def readBatteryCapacity(self, args):
        ret = []
        
        try:
            read = self.batterybus.read_word_data(0x36, 4)
            swapped = struct.unpack("<H", struct.pack(">H", read))[0]
            voltage = swapped/256
            ret.append(voltage)
        except:
            logging.error("Battery Capacity Reading Error")

        return ret
    
    # read battery voltage
    # =====================
    def readBatteryVoltage(self, args):
        ret = []
        
        try:
            read = self.batterybus.read_word_data(0x36, 2)
            swapped = struct.unpack("<H", struct.pack(">H", read))[0]
            voltage = swapped * 1.25 /1000/16
            ret.append(voltage)
        except:
            logging.error("Battery Voltage Reading Error")

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
