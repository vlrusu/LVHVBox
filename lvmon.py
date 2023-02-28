import sys
import glob
import os
import json
import struct
import time
import threading
import readline
#import matplotlib
#import matplotlib.pyplot as plt
import math
import rlcompleter
from pprint import pprint
import smbus
from smbus import SMBus
#import Adafruit_BBIO.GPIO as GPIO
import RPi.GPIO as GPIO
import spidev


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



def get_key_value(keys, flag, default = "0"):
  index = 1
  while True:
    if index >= len(keys) - 1:
      return default
    if keys[index] == ("-" + flag):
      return keys[index+1]
    index += 1

def completer(text, state):
    options = [x for x in cmds if x.startswith(text)]
    try:
        return options[state]
    except IndexError:
        return None

HISTORY_FILENAME = 'mu2e_lvmon.hist'


if os.path.exists(HISTORY_FILENAME):
    print ('reading')
    readline.read_history_file(HISTORY_FILENAME)


readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

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

def process_command(line):
  global output_queue
  global lastrun
  global fout
  global mode
  global calibhisto
  global samples
  global triggers


#  ch = int(sys.argv[1]

  keys = line.split(" ")
  try:



    if keys[0] == "readMonV6":
      realchannel = int(get_key_value(keys,"c",-1))
      address = LTCaddress[realchannel]
      index = v6map[realchannel]
      channelLTC = (0b101<<5) + index
      bus.write_byte(address, channelLTC)

      time.sleep(I2C_sleep_time)
      reading = bus.read_i2c_block_data(address, channelLTC, 3)
      val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
      volts = val*vref/max_reading
      volts = volts/(v6scale*acplscale)
      print (volts,0.03*volts)      

    elif keys[0] == "readMonV48":
      realchannel = int(get_key_value(keys,"c",-1))
      address = LTCaddress[realchannel]
      index = v48map[realchannel]
      channelLTC = (0b101<<5) + index
      bus.write_byte(address, channelLTC)

      time.sleep(I2C_sleep_time)
      reading = bus.read_i2c_block_data(address, channelLTC, 3)
      val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
      volts = val*vref/max_reading
      volts = volts/(v48scale*acplscale)
      print (volts,0.03*volts)      

    elif keys[0] == "readMonI6":
      realchannel = int(get_key_value(keys,"c",-1))
      address = LTCaddress[realchannel]
      index = i6map[realchannel]
      channelLTC = (0b101<<5) + index
      bus.write_byte(address, channelLTC)

      time.sleep(I2C_sleep_time)
      reading = bus.read_i2c_block_data(address, channelLTC, 3)
      val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
      volts = val*vref/max_reading
      volts = volts/(i6scale*acplscale)
      print (volts,0.03*volts)      

    elif keys[0] == "readMonI48":
      realchannel = int(get_key_value(keys,"c",-1))
      address = LTCaddress[realchannel]
      index = i48map[realchannel]
      channelLTC = (0b101<<5) + index
      bus.write_byte(address, channelLTC)

      time.sleep(I2C_sleep_time)
      reading = bus.read_i2c_block_data(address, channelLTC, 3)
      val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
      volts = val*vref/max_reading
      volts = volts/(i48scale*acplscale)
      print (volts,0.03*volts)      
      

      
    elif keys[0] == "readMon":
#        address = 0x16
        # 0x16, 0x26
        realchannel = int(get_key_value(keys,"c",-1))

        address = addresses[int(realchannel/2)]
        print(hex(address))
        ch = realchannel%2

#        print (ch)

        for index in range(4):
            time.sleep(1) # need this otherwise get bus errors. FIXME!
            channelLTC = (0b101<<5) + 4*ch + index
            boardchannel = int((4*ch+index)/2)
            bus.write_byte(address, channelLTC)

            time.sleep(I2C_sleep_time)
            reading = bus.read_i2c_block_data(address, channelLTC, 3)
            print("channel LTC: " + str(channelLTC))
            print("channel: " + str(realchannel))
            print("address: " + str(address))
            print(reading)
            val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
            print(index,val)
            volts = val*vref/max_reading
 #           print (volts)
#            vvolts = volts / 0.01964
            vvolts = volts
            ivolts = volts
#            ivolts = volts 
#            v12volts = volts * V5DIVIDER
            v12volts = volts


            if (ch == 0):

                if (index%2 == 0):
                    if ( index % 4 == 0):
                        print ("Voltage on channel " + str(ch) + "=" + str(round(vvolts,3))  + "V" + " 1")
                    else:
                        print ("Voltage on channel " + str(ch) + "=" + str(round(v12volts,3))  + "V" + " 2")

                else:
                    print ("Current on channel " + str(ch) + "=" + str(round(ivolts,3))  + "A" + " 3")

            else:
                if (index%2 == 1):
                    if ( index % 4 == 3):
                        print ("Voltage on channel " + str(ch) + "=" + str(round(vvolts,3))  + "V" + " 4")
                    else:
                        print ("Voltage on channel " + str(ch) + "=" + str(round(v12volts,3))  + "V" + " 5")

                else:
                    print ("Current on channel " + str(ch) + "=" + str(round(ivolts,3))  + "A" + " 6")


    elif keys[0] == "powerOn":
        channel = int(get_key_value(keys,"c",-1))
# flip because the board is wrong, check the schematics

        if channel ==  -1:
       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
             for ich in range(0,6):
                 mcp1.digitalWrite(powerChMap[ich], MCP23S08.LEVEL_HIGH)


        else:
             channel = abs (channel)
             print( hex(mcp1.readGPIO()))
       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
             mcp1.digitalWrite(powerChMap[channel], MCP23S08.LEVEL_HIGH)
             print( hex(mcp1.readGPIO()))


    elif keys[0] == "powerOff":
        channel = int(get_key_value(keys,"c",-1))
        if channel ==  -1:
       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
             for ich in range(0,6):
                 mcp1.digitalWrite(powerChMap[ich], MCP23S08.LEVEL_LOW)

        else:
             channel = abs(channel)

#       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
             mcp1.digitalWrite(powerChMap[channel], MCP23S08.LEVEL_LOW)

    elif keys[0] == "readvoltage":
        channel = int(get_key_value(keys,"c",-1))
        print("channel=",channel)
        bus.write_byte_data(0x50,0x0,channel+1)# first is the coolpac
        print("done writing")
        reading=bus.read_byte_data(0x50,0xD0)
        print("Module ID:",hex(reading))
        reading=bus.read_i2c_block_data(0x50,0x8B,2)
        print ('[{}]'.format(', '.join(hex(x) for x in reading)))
        value = float(reading[0]+256*reading[1])/256.
        print("Voltage=",value)

    elif keys[0] == "readtemp":
        channel = int(get_key_value(keys,"c",-1))
        bus.write_byte_data(0x50,0x0,channel+1)# first is the coolpac
        reading=bus.read_byte_data(0x50,0xD0)
        print("Module ID:",hex(reading))
        reading=bus.read_i2c_block_data(0x50,0x8D,2)
        print ('[{}]'.format(', '.join(hex(x) for x in reading)))
        value = reading[0]+256*reading[1]
        exponent = ( value >> 11 ) & 0x1f
        mantissa = value & 0x7ff
        temp = mantissa*2**exponent
        print("Temp=",temp)

    elif keys[0] == "readcurrent":
        channel = int(get_key_value(keys,"c",-1))
        bus.write_byte_data(0x50,0x0,channel+1)# first is the coolpac
        reading=bus.read_byte_data(0x50,0xD0)
        print("Module ID:",hex(reading))
        reading=bus.read_i2c_block_data(0x50,0x8C,2)
        print ('[{}]'.format(', '.join(hex(x) for x in reading)))
        value = reading[0]+256*reading[1]
        exponent = ( value >> 11 ) & 0x1f
        exponent = exponent-32
        mantissa = value & 0x7ff
        current = mantissa*2**exponent
        print("Current=",current)


    elif keys[0] == "test":
        reading = bus.read_i2c_block_data(0x50, 0x99, 10)
        print ('[{}]'.format(', '.join(hex(x) for x in reading)))
        print ('[{}]'.format(', '.join(chr(x) for x in reading)))
        bus.write_byte_data(0x50,0x0,1)
        reading=bus.read_byte_data(0x50,0x01)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,2)
        reading=bus.read_byte_data(0x50,0x01)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,3)
        reading=bus.read_byte_data(0x50,0x01)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,4)
        reading=bus.read_byte_data(0x50,0x01)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,5)
        reading=bus.read_byte_data(0x50,0x01)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,6)
        reading=bus.read_byte_data(0x50,0x01)
        print(hex(reading))

    # enables a channel
    elif keys[0] == "enable":
        channel = int(get_key_value(keys,"c",-1))
        bus.write_byte_data(0x50,0x0,channel+1)
        bus.write_byte_data(0x50,0x01,0x80)
        bus.write_byte_data(0x50,0x0,0)        
    elif keys[0] == "readenable":
        channel = int(get_key_value(keys,"c",-1))
        bus.write_byte_data(0x50,0x0,channel+1)
        reading  = bus.read_byte_data(0x50,0x01)
        bus.write_byte_data(0x50,0x0,0)                
        print(hex(reading))
        
    # disables a channel
    elif keys[0] == "disable":
        channel = int(get_key_value(keys,"c",-1))
        bus.write_byte_data(0x50,0x0,channel+1)
        bus.write_byte_data(0x50,0x01,0x0)

    # enables a channel
    elif keys[0] == "testvout":
        channel = int(get_key_value(keys,"c",-1))

        bus.write_byte_data(0x50,0x0,channel+1)
        reading=bus.read_byte_data(0x50,0x20)
        print(hex(reading))
        bus.write_byte_data(0x50,0x21,0x00)
        bus.write_byte_data(0x50,0x21,0x24)

    # enables a channel
    elif keys[0] == "pmbus":
        bus.write_byte_data(0x50,0xD4,0x0)
        reading=bus.read_byte_data(0x50,0xD4)
        print(hex(reading))
        
        
    # prints out any fault conditions
    elif keys[0] == "status":
        channel = int(get_key_value(keys,"c",-1))
        bus.write_byte_data(0x50,0x0,channel+1)
        reading=bus.read_word_data(0x50,0x79)
        print(hex(reading))
        

    # prints the intput voltage
    elif keys[0] == "readvin":
        channel = int(get_key_value(keys,"c",-1))
        bus.write_byte_data(0x50,0x0,channel+1)
        reading=bus.read_word_data(0x50,0x88)
        print(hex(reading))


    elif keys[0] == "readmcp":        

      print(hex(mcp1._readRegister(MCP23S08.MCP23S08_GPIOA)))
      print(hex(mcp1._readRegister(MCP23S08.MCP23S08_GPIOB)))
        


    else:
      print ("Unknown command")

  except ((ValueError, struct.error), e):
    print ("Bad Input:",e)



cmds = ['readMon','powerOn','powerOff','readvoltage', 'readcurrent','readtemp', 'readMonV48', 'readMonV6', 'readMonI48', 'readMonI6']

GLOBAL_ENABLE_PIN =  12
RESET_PIN = 13

powerChMap = [5,6,7,2,3,4]

print ("Starting mon...")
GPIO.setmode(GPIO.BOARD)    
GPIO.setup(RESET_PIN,GPIO.OUT)    
GPIO.output(RESET_PIN,GPIO.LOW)
time.sleep(1)

GPIO.setup(GLOBAL_ENABLE_PIN,GPIO.OUT)
GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
GPIO.output(RESET_PIN,GPIO.HIGH)


mcp1 = MCP23S08(bus=0x00, pin_cs=0x00, device_id=0x01)

mcp1.open()
mcp1._spi.max_speed_hz = 10000000


for x in range(0, 8):
    mcp1.setDirection(x, mcp1.DIR_OUTPUT)
    mcp1.digitalWrite(x, MCP23S08.LEVEL_LOW)


    

I2C_sleep_time = 0.5 # seconds to sleep between each channel reading
bus = SMBus(22)

max_reading = 8388608.0
vref = 1.24 #this is only for the second box
V5DIVIDER = 10


#for pin in pins:
#    GPIO.setup(pin, GPIO.OUT)
#    GPIO.output(pin, GPIO.LOW)

if "libedit" in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")




# keyboard input loop
try:
    while True:
        line = input()
        if line:
            process_command(line)
except KeyboardInterrupt:
    stored_exception=sys.exc_info()
except Exception as e:
    print (type(e),e)

finally:
    print ('Ending...')
    readline.write_history_file(HISTORY_FILENAME)
