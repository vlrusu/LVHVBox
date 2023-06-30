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




output_data = []
burst_string = 'a'
read_string = 's'

outep.write(burst_string)

for i in range(2):
    outep.write(read_string)
    from_device = inep.read(4*15)

    for item in range(15):
        v = format(from_device[4*item + 3], '008b') + format(from_device[4*item + 2], '008b') + format(from_device[4*item + 1], '008b') + format(from_device[4*item], '008b')

        sign = (-1) ** int(v[0],2)
        exponent = int(v[1:9],2)-127
        mantissa = int(v[9::],2)
        output_value = sign * (1+mantissa*(2**-23)) * 2**exponent


        print(output_value)


'''
output_data=[]
test_string = 'I'
count = 1
channel_count = 6


for i in range(count):
    outep.write(test_string)
    from_device = inep.read(4*channel_count)
    print(from_device)
   
    for channel in range(channel_count):
        v = format(from_device[4*channel + 3], '008b') + format(from_device[4*channel + 2], '008b') + format(from_device[4*channel + 1], '008b') + format(from_device[4*channel], '008b')

        sign = (-1) ** int(v[0],2)
        exponent = int(v[1:9],2)-127
        mantissa = int(v[9::],2)
        output_value = sign * (1+mantissa*(2**-23)) * 2**exponent
        print("Channel " + str(channel) + ": " + str(output_value))
        print("\n")
'''



     

