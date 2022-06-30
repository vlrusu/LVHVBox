import wiringpi

# import c functions for lv
from ctypes import *

# serial to acquire hv data
import serial

import time

import threading

#import plotTripTest

rampup = "/home/pi/redHVMB_test/python_connect.so"
rampup=CDLL(rampup)

def get_hv(ser):
    #print('outer')
    while True:
        #print('inner')
        line=ser.readline().decode('ascii')
        if line.startswith('Trip count'):
            pass
        elif line.startswith('Trip on'):
            pass
        else:
            print(line)
            file=open('/home/pi/redHVMB_test/redHvAutoTripTest.txt','a')
            file.write(line)
            file.close()
            time.sleep(0.5)

# initialize hv
rampup.initialization()
time.sleep(1)

# get number of trips from user
trips = input('How many total trips? ')

# open serial connection
ser = serial.Serial('/dev/ttyACM0', 115200)
time.sleep(3)
ser.write(bytes(b's'))
time.sleep(3)
ser.write(bytes(b's'))
time.sleep(3)
print('connection one established')



thread=threading.Thread(target=get_hv,args=[ser])
thread.setDaemon(True)
thread.start()

# check which channels have switches in them
channels = []

valid = False
while valid == False:
    line=ser.readline().decode('ascii')
    singleline = line.split()
    if len(singleline) == 18:
        valid = True

for ch in range(6):
    if singleline[ch] == "0.000":
        channels.append(False)
    else:
        channels.append(True)
print(channels)
#print(len(singleline))

# rampup channels with switches
for i in range(int(trips)):
    print('Ramping up HV to 1500')
    print('')
    if channels[5] == True:
        rampup.rampup_hv(0,1500)
    if channels[4] == True:
        rampup.rampup_hv(1,1500)
    if channels[3] == True:
        rampup.rampup_hv(2,1500)
    if channels[2] == True:
        rampup.rampup_hv(3,1500)
    if channels[1] == True:
        rampup.rampup_hv(4,1500)
    if channels[0] == True:
        rampup.rampup_hv(5,1500)
    print('Done ramping up HV')

    
    # hold HV at 1500 for stability
    print('Holding HV at 1500 for 60 seconds')
    print('')
    time.sleep(60)
    
    # force trip on active channels\
    print('Forcing trips on channels')
    # print('Note that channels listed below are in reverse order')
    print('')
    time.sleep(3)
    
    if channels[5] == True:
        ser.write(bytes(b'F'))
        time.sleep(0.5)
        ser.write(bytes(b'0'))
        ser.write(bytes(b'\r'))
        time.sleep(3)
    if channels[4] == True:
        ser.write(bytes(b'F'))
        time.sleep(0.5)
        ser.write(bytes(b'1'))
        ser.write(bytes(b'\r'))
        time.sleep(3)
    if channels[3] == True:
        ser.write(bytes(b'F'))
        time.sleep(0.5)
        ser.write(bytes(b'2'))
        ser.write(bytes(b'\r'))
        time.sleep(3)
    if channels[2] == True:
        ser.write(bytes(b'F'))
        time.sleep(0.5)
        ser.write(bytes(b'3'))
        ser.write(bytes(b'\r'))
        time.sleep(3)
    if channels[1] == True:
        ser.write(bytes(b'F'))
        time.sleep(0.5)
        ser.write(bytes(b'4'))
        ser.write(bytes(b'\r'))
        time.sleep(3)
    if channels[0] == True:
        ser.write(bytes(b'F'))
        time.sleep(0.5)
        ser.write(bytes(b'5'))
        ser.write(bytes(b'\r'))
        time.sleep(3)
    print('All channels forced to trip')
    print('')
    #time.sleep(10)

    """ser.write(bytes(b'T'))
    time.sleep(0.5)
    ser.write(bytes(b'300000'))
    ser.write(bytes(b'\r'))
    time.sleep(5)"""
    
    # wait time for testing
    time.sleep(10)
    
    # set rampups to zero
    print('Ramping down HV to 0')
    print('')
    if channels[5] == True:
        rampup.rampup_hv(0,0)
    if channels[4] == True:
        rampup.rampup_hv(1,0)
    if channels[3] == True:
        rampup.rampup_hv(2,0)
    if channels[2] == True:
        rampup.rampup_hv(3,0)
    if channels[1] == True:
        rampup.rampup_hv(4,0)
    if channels[0] == True:
        rampup.rampup_hv(5,0)
    print('Done ramping down HV')
    print('')

    # reset trips
    time.sleep(15)
    ser.write(bytes(b'R'))
    time.sleep(3)
    print('Trip counts reset')
    totalTrips = 'Total trips: '
    print('Total trips: ')
    print(i+1)
    file=open('/home/pi/redHVMB_test/redHvAutoTripTest.txt','a')
    file.write(totalTrips + str(i+1))
    file.close()
ser.close()   
#plotTripTest.plot()
