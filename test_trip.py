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
import ramphv
import rampup
import rampdown




def get_voltage(channel, inep, outep):
    voltage_string = 'V'

     # send command to get current
    outep.write(voltage_string)

    # read in and process current data
    from_device = inep.read(4*6)

    v = format(from_device[4*channel + 3], '008b') + format(from_device[4*channel + 2], '008b') + format(from_device[4*channel + 1], '008b') + format(from_device[4*channel], '008b')

    sign = (-1) ** int(v[0],2)
    exponent = int(v[1:9],2)-127
    mantissa = int(v[9::],2)
    output_value = sign * (1+mantissa*(2**-23)) * 2**exponent
    
    return float(output_value)

def get_current(channel, inep, outep):
    current_string = 'I'

     # send command to get current
    outep.write(current_string)

    # read in and process current data
    from_device = inep.read(4*6)

    v = format(from_device[4*channel + 3], '008b') + format(from_device[4*channel + 2], '008b') + format(from_device[4*channel + 1], '008b') + format(from_device[4*channel], '008b')

    sign = (-1) ** int(v[0],2)
    exponent = int(v[1:9],2)-127
    mantissa = int(v[9::],2)
    output_value = sign * (1+mantissa*(2**-23)) * 2**exponent
    
    return float(output_value)

def trip(channel, inep, outep):
    trip_strings = ['g', 'h', 'i', 'j', 'k', 'l']
    outep.write(trip_strings[channel])

def reset_trip(channel, inep, outep):
    reset_strings = ['m', 'n', 'o', 'p', 'q', 'r']
    outep.write(reset_strings[channel])
     
if __name__=="__main__":

    global adc_to_V 
    adc_to_V= 2.048/(2**15)*1000
    global adc_to_uA
    adc_to_uA = 2.048/((2**15)*8200)*1E6

    # find our device
    dev = usb.core.find(idVendor=0xcaf1, idProduct=0x4003)


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


    channel = 2

    current_data = []
    voltage_data = []
    time_data = []






    dac = ramphv.initialization()


    start = time.time()

    count = 500

    for i in range(count):
        for j in range(30):
            current_data.append(get_current(channel, inep, outep))
            voltage_data.append(get_voltage(channel, inep, outep))
            time_data.append(time.time() - start)
            time.sleep(0.01)

        trip(channel, inep, outep)

        for j in range(30):
            current_data.append(get_current(channel, inep, outep))
            voltage_data.append(get_voltage(channel, inep, outep))
            time_data.append(time.time() - start)
            time.sleep(0.01)


        # ramp hv down
        value = 0*2.3/1510
        rampdown.rampdown(channel, value, 200, dac)

        for j in range(100):
            current_data.append(get_current(channel, inep, outep))
            voltage_data.append(get_voltage(channel, inep, outep))
            time_data.append(time.time() - start)
            time.sleep(0.01)

        # reset trip
        reset_trip(channel, inep, outep)


        for j in range(30):
            current_data.append(get_current(channel, inep, outep))
            voltage_data.append(get_voltage(channel, inep, outep))
            time_data.append(time.time() - start)
            time.sleep(0.01)


        # ramp hv up
        value = 1450*2.3/1510
        rampup.rampup(channel, value, 200, dac)

        for j in range(40):
            current_data.append(get_current(channel, inep, outep))
            voltage_data.append(get_voltage(channel, inep, outep))
            time_data.append(time.time() - start)
            time.sleep(0.01)
        
        print("Finished trip number " + str(i))
    

    with open('trip_data.txt', 'w') as f:
        for i in range(len(current_data)):
            f.write(str(current_data[i]) + " " + str(voltage_data[i]) + " " + str(time_data[i]) + "\n")
        
    
    



