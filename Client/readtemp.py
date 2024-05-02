import os
from ctypes import *
import time
import threading
import smbus
from smbus import SMBus
import logging

from datetime import datetime




if __name__=="__main__":
    f = open("../Data/temps.txt", "a")



    bus = SMBus(3)
    bus.pec=1

    while True:
        temps = []

        for ich in range(6):
            bus.write_byte_data(0x50,0x0,ich+1)  # first is the coolpac
            reading=bus.read_byte_data(0x50,0xD0)
            reading=bus.read_i2c_block_data(0x50,0x8D,2)
            value = reading[0]+256*reading[1]
            exponent = ( value >> 11 ) & 0x1f
            mantissa = value & 0x7ff

            temp = mantissa*2**exponent
            temps.append(temp)

        temps.append(time.time())

        print(temps)

        for i in range(6):
            f.write(str(temps[i]) + ", ")
        f.write(str(temps[6]) + '\n')
    
        time.sleep(10)