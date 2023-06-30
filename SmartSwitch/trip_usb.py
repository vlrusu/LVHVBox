#!/usr/bin/env python3

#
# Copyright (c) 2020 Raspberry Pi (Trading) Ltd.
#
# SPDX-License-Identifier: BSD-3-Clause
#

# sudo pip3 install pyusb

import usb.core
import usb.util
import time
import struct



global adc_to_V 
adc_to_V= 2.048/(2**15)*1000
global adc_to_uA
adc_to_uA = 2.048/((2**15)*8200)*1E6

# find our device
dev = usb.core.find(idVendor=0xcaff, idProduct=0x4003)


# was it found?
if dev is None:
    raise ValueError('Device not found')

# get an endpoint instance
cfg = dev.get_active_configuration()
intf = cfg[(1, 0)]

if dev.is_kernel_driver_active(1):
        try:
            dev.detach_kernel_driver(1)
        except:
             print('error')

usb.util.claim_interface(dev, 1)


outep = usb.util.find_descriptor(
    intf,
    # match the first OUT endpoint
    custom_match= \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)

inep = usb.util.find_descriptor(
    intf,
    # match the first IN endpoint
    custom_match= \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)

assert inep is not None
assert outep is not None

#test_string = "Hello World!"
test_string = b'\x00'
#test_string += 'h'.encode('utf-8')
#for i in range(64):
#     test_string += 'h'.encode('utf-8')


'''
def convert_values(from_device):
    voltages = []
    currents = []


    for i in range(0,30,2):
        v = format(from_device[i+1], '008b') + format(from_device[i], '008b')
        voltages.append(int(v,2)*adc_to_V)


    for j in range(0,60,2):
        i = format(from_device[j+1], '008b') + format(from_device[j], '008b')
        currents.append(int(i,2)*adc_to_uA)

    return voltages, currents


channel_1_voltages = []
channel_1_currents = []

start_time = time.time()
count = 2
'''


'''
for i in range(count):
    outep.write(test_string)
    #channel_1_currents.append(inep.read(60))
    from_device = inep.read(60)

    voltages,currents = convert_values(from_device)
    print(currents[0])
    
    


    from_device = inep.read(60)

    #print("Device Says: {}".format(''.join([chr(x) for x in from_device])))


    temp_voltages, temp_currents = convert_values(from_device)
    channel_1_voltages.append(temp_voltages)
    channel_1_currents.append(temp_currents)
    





elapsed_time = time.time() - start_time
#print(count/elapsed_time*30)



raw_data = [0 for i in range(60*count)]
#from_device = inep.read(60*count)

#print(len(from_device))
'''




output_data=[]
test_string = 'g'
count = 1
channel_count = 6
start = time.time()

for i in range(count):
    outep.write(test_string)
   


     

