import serial

# import c file
from ctypes import *
import time

"""
def save_txt(self):
    output=''
    for i in range(0,6):
        output+='ch'+str(i)
        output+=','+str(self.voltage[i])
        output+=','+str(self.current[i])
        output+=','+str(self.temperature[i])
        output+=','+str(self.five_voltage[i])
        output+=','+str(self.five_current[i])
        output+=','+str(self.cond_voltage[i])
        output+=','+str(self.cond_current[i])
    output+=','+str(time.time())
    output+='\n'

    file1=open("logfile.txt", "a")
    file1.write(output)
    file1.close()
"""


if __name__=="__main__":
    so_file = "/home/pi/python_connect.so"
    functions = CDLL(so_file)
    functions.initialization()
    functions.set_hv(100,100)

    while True:
        ser = serial.Serial('/dev/ttyUSB0')  # open serial port
        print(str(ser.readline() + ' - ' + str(datetime))
        ser.close()             # close port
