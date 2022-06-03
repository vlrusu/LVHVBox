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
from RPiMCP23S17.MCP23S17 import MCP23S17


cmds = ['readMon','powerOn','powerOff','readvoltage', 'readcurrent','readtemp']


mcp1 = MCP23S17(bus=0x00, pin_cs=0x01, device_id=0x00)

mcp1.open()
mcp1._spi.max_speed_hz = 10000000


for x in range(8, 16):
    mcp1.setDirection(x, mcp1.DIR_OUTPUT)
    mcp1.digitalWrite(x, MCP23S17.LEVEL_LOW)



I2C_sleep_time = 0.5 # seconds to sleep between each channel reading
bus = SMBus(1)

max_reading = 8388608.0
vref = 2.048

pins = ["P9_15","P9_15","P9_15","P9_27","P9_41","P9_12"]
GLOBAL_ENABLE_PIN =  15
RESET_PIN = 32

#for pin in pins:
#    GPIO.setup(pin, GPIO.OUT)
#    GPIO.output(pin, GPIO.LOW)

if "libedit" in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")


    
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
    if keys[0] == "readMon":
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
 #           print(reading)
            val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
            volts = val*vref/max_reading
 #           print (volts)
            vvolts = volts / 0.01964
            ivolts = volts / 0.4
            v12volts = volts /0.074588


            if (ch == 0):
            
                if (index%2 == 0):
                    if ( index % 4 == 0):
                        print ("Voltage on channel " + str(ch) + "=" + str(round(vvolts,3))  + "V")
                    else:
                        print ("Voltage on channel " + str(ch) + "=" + str(round(v12volts,3))  + "V")

                else:
                    print ("Current on channel " + str(ch) + "=" + str(round(ivolts,3))  + "A")

            else:
                if (index%2 == 1):
                    if ( index % 4 == 3):
                        print ("Voltage on channel " + str(ch) + "=" + str(round(vvolts,3))  + "V")
                    else:
                        print ("Voltage on channel " + str(ch) + "=" + str(round(v12volts,3))  + "V")

                else:
                    print ("Current on channel " + str(ch) + "=" + str(round(ivolts,3))  + "A")

                
    elif keys[0] == "powerOn":
        channel = int(get_key_value(keys,"c",-1))
# flip because the board is wrong, check the schematics
        channel = abs (channel - 5)
        
        if channel ==  -1:
       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
             for ich in range(0,6):
                 mcp1.digitalWrite(ich+8, MCP23S17.LEVEL_HIGH)
                              
        else:
       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
             mcp1.digitalWrite(channel+8, MCP23S17.LEVEL_HIGH)

    elif keys[0] == "powerOff":
        channel = int(get_key_value(keys,"c",-1))
        channel = abs(channel -5)
        if channel ==  -1:
       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
             for ich in range(0,6):
                 mcp1.digitalWrite(ich+8, MCP23S17.LEVEL_LOW)

        else:
#       	     GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
             mcp1.digitalWrite(channel+8, MCP23S17.LEVEL_LOW)

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
        bus.write_byte_data(0x50,0x0,0)
        reading=bus.read_byte_data(0x50,0xD0)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,1)
        reading=bus.read_byte_data(0x50,0xD0)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,2)
        reading=bus.read_byte_data(0x50,0xD0)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,3)
        reading=bus.read_byte_data(0x50,0xD0)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,4)
        reading=bus.read_byte_data(0x50,0xD0)
        print(hex(reading))
        bus.write_byte_data(0x50,0x0,5)
        reading=bus.read_byte_data(0x50,0xD0)
        print(hex(reading))

            
    else:
      print ("Unknown command")
      
  except ((ValueError, struct.error), e):
    print ("Bad Input:",e)




        

# keyboard input loop
try:
    print ("Starting mon...")
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(GLOBAL_ENABLE_PIN,GPIO.OUT)
    GPIO.output(GLOBAL_ENABLE_PIN,GPIO.LOW)
    GPIO.setup(RESET_PIN,GPIO.OUT)
    GPIO.output(RESET_PIN,GPIO.HIGH)
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
