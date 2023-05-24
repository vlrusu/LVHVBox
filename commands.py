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

from datetime import datetime

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import numpy as np

import control_hv


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


class MCP23S08(object):
    """This class provides an abstraction of the GPIO expander MCP23S17
    for the Raspberry Pi.
    It is depndent on the Python packages spidev and RPi.GPIO, which can
    be get from https://pypi.python.org/pypi/RPi.GPIO/0.5.11 and
    https://pypi.python.org/pypi/spidev.
    """
    PULLUP_ENABLED = 0
    PULLUP_DISABLED = 1

    DIR_INPUT = 0
    DIR_OUTPUT = 1

    LEVEL_LOW = 0
    LEVEL_HIGH = 1

    """Register addresses as documentined in the technical data sheet at
    http://ww1.microchip.com/downloads/en/DeviceDoc/21952b.pdf
    """
    MCP23S08_IODIR = 0x00
    MCP23S08_IPOL  = 0x01
    MCP23S08_GPINTEN  = 0x02
    MCP23S08_DEFVAL  = 0x03
    MCP23S08_INTCON  = 0x04
    MCP23S08_IOCON  = 0x05
    MCP23S08_GPPU  = 0x06
    MCP23S08_INTF  = 0x07
    MCP23S08_INTCAP  = 0x08
    MCP23S08_GPIO  = 0x09
    MCP23S08_OLAT  = 0x0A    
    """Bit field flags as documentined in the technical data sheet at
    http://ww1.microchip.com/downloads/en/DeviceDoc/21952b.pdf
    """
    IOCON_UNUSED = 0x01
    IOCON_INTPOL = 0x02
    IOCON_ODR = 0x04
    IOCON_HAEN = 0x08
    IOCON_DISSLW = 0x10
    IOCON_SPREAD = 0x20

    IOCON_INIT = 0x28  # IOCON_SEQOP and IOCON_HAEN from above

    MCP23S08_CMD_WRITE = 0x40
    MCP23S08_CMD_READ = 0x41

    def __init__(self, bus=0, pin_cs=0, pin_reset=-1, device_id=0x00):
        """
        Constructor
        Initializes all attributes with 0.

        Keyword arguments:
        device_id -- The device ID of the component, i.e., the hardware address (default 0)
        pin_cs -- The Chip Select pin of the MCP, default 0
        pin_reset -- The Reset pin of the MCP
        """
        self.device_id = device_id
        self._GPIO = 0
        self._IODIR = 0
        self._GPPU = 0
        self._pin_reset = pin_reset
        self._bus = bus
        self._pin_cs = pin_cs
        self._spimode = 0b00
        self._spi = spidev.SpiDev()
        self.isInitialized = False

    def open(self):
        """Initializes the MCP23S08 with hardware-address access
        and sequential operations mode.
        """
        self._setupGPIO()
        self._spi.open(self._bus, self._pin_cs)
        self.isInitialized = True
        self._writeRegister(MCP23S08.MCP23S08_IOCON, MCP23S08.IOCON_INIT)

        # set defaults
        for index in range(0, 7):
            self.setDirection(index, MCP23S08.DIR_INPUT)
            self.setPullupMode(index, MCP23S08.PULLUP_ENABLED)

    def close(self):
        """Closes the SPI connection that the MCP23S08 component is using.
        """
        self._spi.close()
        self.isInitialized = False

    def setPullupMode(self, pin, mode):
        """Enables or disables the pull-up mode for input pins.

        Parameters:
        pin -- The pin index (0 - 7)
        mode -- The pull-up mode (MCP23S08.PULLUP_ENABLED, MCP23S08.PULLUP_DISABLED)
        """

        assert pin < 8
        assert (mode == MCP23S08.PULLUP_ENABLED) or (mode == MCP23S08.PULLUP_DISABLED)
        assert self.isInitialized


        register = MCP23S08.MCP23S08_GPPU
        data = self._GPPU
        noshifts = pin

        if mode == MCP23S08.PULLUP_ENABLED:
            data |= (1 << noshifts)
        else:
            data &= (~(1 << noshifts))

        self._writeRegister(register, data)


        self._GPPU = data

    def setDirection(self, pin, direction):
        """Sets the direction for a given pin.

        Parameters:
        pin -- The pin index (0 - 7)
        direction -- The direction of the pin (MCP23S08.DIR_INPUT, MCP23S08.DIR_OUTPUT)
        """

        assert (pin < 8)
        assert ((direction == MCP23S08.DIR_INPUT) or (direction == MCP23S08.DIR_OUTPUT))
        assert self.isInitialized

        register = MCP23S08.MCP23S08_IODIR
        data = self._IODIR
        noshifts = pin

        if direction == MCP23S08.DIR_INPUT:
            data |= (1 << noshifts)
        else:
            data &= (~(1 << noshifts))

        self._writeRegister(register, data)


        self._IODIR = data

    def digitalRead(self, pin):
        """Reads the logical level of a given pin.

        Parameters:
        pin -- The pin index (0 - 7)
        Returns:
         - MCP23S08.LEVEL_LOW, if the logical level of the pin is low,
         - MCP23S08.LEVEL_HIGH, otherwise.
        """

        assert self.isInitialized
        assert (pin < 8)

        self._GPIO = self._readRegister(MCP23S08.MCP23S08_GPIO)
        if (self._GPIO & (1 << pin)) != 0:
          return MCP23S08.LEVEL_HIGH
        else:
          return MCP23S08.LEVEL_LOW

    def digitalWrite(self, pin, level):
        """Sets the level of a given pin.
        Parameters:
        pin -- The pin index (0 - 7)
        level -- The logical level to be set (LEVEL_LOW, LEVEL_HIGH)
        """

        assert self.isInitialized
        assert (pin < 8)
        assert (level == MCP23S08.LEVEL_HIGH) or (level == MCP23S08.LEVEL_LOW)

        register = MCP23S08.MCP23S08_GPIO
        data = self._GPIO
        noshifts = pin

        if level == MCP23S08.LEVEL_HIGH:
            data |= (1 << noshifts)
        else:
            data &= (~(1 << noshifts))

        self._writeRegister(register, data)


        self._GPIO = data

    def writeGPIO(self, data):
        """Sets the data port value for all pins.
        Parameters:
        data - The 8-bit value to be set.
        """

        assert self.isInitialized

        self._GPIO = (data & 0xFF)
        self._writeRegisterWord(MCP23S08.MCP23S08_GPIO, data)

    def readGPIO(self):
        """Reads the data port value of all pins.
        Returns:
         - The 8-bit data port value
        """

        assert self.isInitialized
        data = self._readRegisterWord(MCP23S08.MCP23S08_GPIO)
        self._GPIO = (data & 0xFF)
        return data

    def _writeRegister(self, register, value):
        assert self.isInitialized
        command = MCP23S08.MCP23S08_CMD_WRITE | (self.device_id << 1)
        self._setSpiMode(self._spimode)
        self._spi.xfer2([command, register, value])

    def _readRegister(self, register):
        assert self.isInitialized
        command = MCP23S08.MCP23S08_CMD_READ | (self.device_id << 1)
        self._setSpiMode(self._spimode)
        data = self._spi.xfer2([command, register, 0])
        return data[2]

    def _readRegisterWord(self, register):
        assert self.isInitialized
        buffer = [0, 0]
        buffer[0] = self._readRegister(register)
        buffer[1] = self._readRegister(register + 1)
        return (buffer[1] << 8) | buffer[0]

    def _writeRegisterWord(self, register, data):
        assert self.isInitialized
        self._writeRegister(register, data & 0xFF)
        self._writeRegister(register + 1, data >> 8)

    def _setupGPIO(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)

        if self._pin_reset != -1:
            GPIO.setup(self._pin_reset, GPIO.OUT)
            GPIO.output(self._pin_reset, True)

    def _setSpiMode(self, mode):
        if self._spi.mode != mode:
            self._spi.mode = mode
            self._spi.xfer2([0])  # dummy write, to force CLK to correct level



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

        self.powerChMap = [5,6,7,2,3,4]

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

                six_voltages = self.read_six_voltage([None])
                self.v6 = [0]*NLVCHANNELS

                six_currents = self.read_six_current([None])
                self.i6 = [0]*NLVCHANNELS
                  
                voltages = self.readvoltage([None])
                self.v48 = [0]*NLVCHANNELS

                currents = self.readcurrent([None])
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
            ret['v6']=self.get_v6(channel)
            ret['i6']=self.get_v6(channel)
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

        value = voltage*2.3/1510
        nsteps = 200
        control_hv.ramp_hv(channel,value,nsteps,self.hv_dac)

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

        value = voltage*2.3/1510
        nsteps = 200
        control_hv.set_hv(channel,value,self.hv_dac)

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

    def read_six_voltage(self,channel):
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
    
    def read_six_current(self,channel):
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
    def readvoltage(self,channel):
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
    def readcurrent(self,channel):
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
