import argparse
import rlcompleter
import readline
import socket
import time
import struct

HISTORY_REQUEST_MAX = 100
current_buffer_len = 8000 # must be divisible by 10
full_current_chunk = 10

parser = argparse.ArgumentParser()
cmds = {'get_vhv',
    'get_ihv',
    'current_burst',
    'current_start',
    'current_stop',
    'current_buffer_run',
    'ramp_hv',
    'down_hv',
    'trip',
    'reset_trip',
    'disable_trip',
    'enable_trip',
    'trip_status',
    'pcb_temp',
    'pico_current',
    'set_trip',
    'powerOn',
    'powerOff',
    'readMonV48',
    'readMonI48',
    'readMonV6',
    'readMonI6',
    'enable_ped',
    'disable_ped',
    'start_usb',
    'stop_usb'}



if "libedit" in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")

def binary(num):
    return ''.join('{:0>8b}'.format(c) for c in struct.pack('!f', num))

def bstring_to_chars(string):
    char0 = chr(int(string[0:8], 2))
    char1 = chr(int(string[8:16], 2))
    char2 = chr(int(string[16:24], 2))
    char3 = chr(int(string[24::], 2))

    ret_val = char0 + char1 + char2 + char3
    return ret_val


def read_commands():
    file = open("../commands.h", "r")
    pre_command_list = file.readlines()
    pre_command_list = [i.split() for i in pre_command_list]

    command_dict = {}
    for i in pre_command_list:
        #command_dict[i[1]] = format(int(i[2]), '032b')
        #command_dict[i[1]] = struct.pack('<I', int(i[2])).decode('utf-8')
        string = format(int(i[2]), '032b')
        #print(string)


        #command_dict[i[1]] = bstring_to_chars(string)
        command_dict[i[1]] = string

    

    #print(str(command_dict))
    return command_dict

def process_float(input):
    v = format(input[3], '008b') + format(input[2], '008b') + format(input[1], '008b') + format(input[0], '008b')

    sign = (-1) ** int(v[0],2)
    exponent = int(v[1:9],2)-127
    mantissa = int(v[9::],2)
    float_val = sign * (1+mantissa*(2**-23)) * 2**exponent
    
    return float_val

def float_to_bytes(input):
    pass

def bitstring_to_bytes(s):
    return int(s, 2).to_bytes(4, byteorder='big')

def completer(text, state):
    options = [x for x in cmds if x.startswith(text)]
    try:
        return options[state]
    except IndexError:
        return None

readline.set_completer(completer)        
readline.parse_and_bind("tab: complete")

parser = argparse.ArgumentParser()
args = parser.parse_args()

def create_command_string_default():
    pass

def process_command(line):
    command_dict = read_commands()
    
    keys = line.split(" ")

    try:
        if keys[0] == "get_vhv":

            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_get_vhv = bitstring_to_bytes(command_dict["COMMAND_get_vhv"])
            type_hv = bitstring_to_bytes(command_dict["TYPE_hv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_get_vhv + type_hv + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)
            print("Channel " + str(channel) + " voltage: " + str(return_val) + " V")

        elif keys[0] == "get_ihv":
        

            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_get_ihv = bitstring_to_bytes(command_dict["COMMAND_get_ihv"])
            type_hv = bitstring_to_bytes(command_dict["TYPE_hv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_get_ihv + type_hv + bits_channel + padding

            sock.send(command_string)
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)

            print("Channel " + str(channel) + " current: " + str(return_val) + " uA")


        elif keys[0] == "readMonV48":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_readMonV48 = bitstring_to_bytes(command_dict["COMMAND_readMonV48"])
            type_lv = bitstring_to_bytes(command_dict["TYPE_lv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonV48 + type_lv + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)

            print("Channel " + str(channel) + " voltage: " + str(return_val) + " V")
        
        elif keys[0] == "readMonI48":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_readMonI48 = bitstring_to_bytes(command_dict["COMMAND_readMonI48"])
            type_lv = bitstring_to_bytes(command_dict["TYPE_lv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonI48 + type_lv + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)

            print("Channel " + str(channel) + " current: " + str(return_val) + " A")
        
        
        elif keys[0] == "readMonV6":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_readMonV6 = bitstring_to_bytes(command_dict["COMMAND_readMonV6"])
            type_lv = bitstring_to_bytes(command_dict["TYPE_lv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonV6 + type_lv + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)

            print("Channel " + str(channel) + " voltage: " + str(return_val) + " V")
        

        elif keys[0] == "readMonI6":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_readMonI6 = bitstring_to_bytes(command_dict["COMMAND_readMonI6"])
            type_lv = bitstring_to_bytes(command_dict["TYPE_lv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_readMonI6 + type_lv + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)

            print("Channel " + str(channel) + " current: " + str(return_val) + " A")
        

        elif keys[0] == "current_buffer_run":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_current_buffer_run = bitstring_to_bytes(command_dict["COMMAND_current_buffer_run"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_current_buffer_run + type_pico + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = int(temp[0])

            print("Current buffer status: " + str(return_val))
        
        elif keys[0] == "trip_status":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_current_buffer_run = bitstring_to_bytes(command_dict["COMMAND_trip_status"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_current_buffer_run + type_pico + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = int(temp[0])

            print("Trip status: " + str(return_val))

        elif keys[0] == "pcb_temp":
        
            command_pcb_temp = bitstring_to_bytes(command_dict["COMMAND_pcb_temp"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            padding = bytearray(5)
            command_string = command_pcb_temp + type_pico + padding

            sock.send(command_string)
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)

            print("PCB Temperature: " + str(return_val) + " C")

        elif keys[0] == "pico_current":
            command_pico_current = bitstring_to_bytes(command_dict["COMMAND_pico_current"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            padding = bytearray(5)
            command_string = command_pico_current + type_pico + padding
            
            sock.send(command_string)
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)

            print("Pico Current: " + str(return_val) + " A")
        
        
        elif keys[0] == "get_slow_read":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_get_slow_read = bitstring_to_bytes(command_dict["COMMAND_get_slow_read"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_get_slow_read + type_pico + bits_channel + padding

            sock.send(command_string)

            temp = sock.recv(1024)
            return_val = int(temp[0])

            print("Slow read: " + str(return_val))
        

        elif keys[0] == "current_start":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_current_start = bitstring_to_bytes(command_dict["COMMAND_current_start"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_current_start + type_pico + bits_channel + padding

            sock.send(command_string)


        elif keys[0] == "current_stop":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_current_stop = bitstring_to_bytes(command_dict["COMMAND_current_stop"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_current_stop + type_pico + bits_channel + padding

            sock.send(command_string)

        elif keys[0] == "update_ped":

            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_update_ped = bitstring_to_bytes(command_dict["COMMAND_update_ped"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_update_ped + type_pico + bits_channel + padding
            
            sock.send(command_string)
        

        elif keys[0] == "down_hv":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_down_hv = bitstring_to_bytes(command_dict["COMMAND_down_hv"])
            type_hv = bitstring_to_bytes(command_dict["TYPE_hv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_down_hv + type_hv + bits_channel + padding

            sock.send(command_string)
        
        
        elif keys[0] == "trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_trip = bitstring_to_bytes(command_dict["COMMAND_trip"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_trip + type_pico + bits_channel + padding

            sock.send(command_string)

        
        elif keys[0] == "reset_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_reset_trip = bitstring_to_bytes(command_dict["COMMAND_reset_trip"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_reset_trip + type_pico + bits_channel + padding

            sock.send(command_string)

        
        elif keys[0] == "disable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_disable_trip = bitstring_to_bytes(command_dict["COMMAND_disable_trip"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_disable_trip + type_pico + bits_channel + padding

            sock.send(command_string)
        

        elif keys[0] == "enable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_enable_trip = bitstring_to_bytes(command_dict["COMMAND_enable_trip"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_enable_trip + type_pico + bits_channel + padding

            sock.send(command_string)

        
        elif keys[0] == "enable_ped":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_enable_ped = bitstring_to_bytes(command_dict["COMMAND_enable_ped"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_enable_ped + type_pico + bits_channel + padding

            sock.send(command_string)

        
        elif keys[0] == "disable_ped":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_disable_ped = bitstring_to_bytes(command_dict["COMMAND_disable_ped"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_disable_ped + type_pico + bits_channel + padding

            sock.send(command_string)

        
        elif keys[0] == "powerOn":
            if len(keys) == 2:
                channel = int(keys[1])
                assert 0 <= channel <= 5
            else:
                channel = 6

            command_powerOn = bitstring_to_bytes(command_dict["COMMAND_powerOn"])
            type_lv = bitstring_to_bytes(command_dict["TYPE_lv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_powerOn + type_lv + bits_channel + padding

            sock.send(command_string)

        
        elif keys[0] == "powerOff":
            if len(keys) == 2:
                channel = int(keys[1])
                assert 0 <= channel <= 5
            else:
                channel = 6
    
            command_powerOff = bitstring_to_bytes(command_dict["COMMAND_powerOff"])
            type_lv = bitstring_to_bytes(command_dict["TYPE_lv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_powerOff + type_lv + bits_channel + padding

            sock.send(command_string)


        elif keys[0] == "enable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_enable_trip = bitstring_to_bytes(command_dict["COMMAND_enable_trip"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_enable_trip + type_pico + bits_channel + padding

            sock.send(command_string)


        elif keys[0] == "disable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_disable_trip = bitstring_to_bytes(command_dict["COMMAND_disable_trip"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            padding = bytearray(4)
            command_string = command_disable_trip + type_pico + bits_channel + padding

            sock.send(command_string)

        elif keys[0] == "set_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_set_trip = bitstring_to_bytes(command_dict["COMMAND_set_trip"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            floatval = bytearray(struct.pack("f", float(keys[2])))
            command_string = command_set_trip + type_pico + bits_channel + floatval

            sock.send(command_string)
        

        elif keys[0] == "set_trip_count":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_set_trip = bitstring_to_bytes(command_dict["COMMAND_set_trip_count"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            print("keys[2]: " + str(int(keys[2])))
            floatval = bytearray(struct.pack("I", int(keys[2])))
            command_string = command_set_trip + type_pico + bits_channel + floatval

            sock.send(command_string)

        
        elif keys[0] == "ramp_hv":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_ramp_hv = bitstring_to_bytes(command_dict["COMMAND_ramp_hv"])
            type_hv = bitstring_to_bytes(command_dict["TYPE_hv"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            floatval = bytearray(struct.pack("f", float(keys[2])))
            command_string = command_ramp_hv + type_hv + bits_channel + floatval

            sock.send(command_string)
        
        elif keys[0] == "current_burst":
            # send command to stop usb
            command_stop_usb = bitstring_to_bytes(command_dict["COMMAND_stop_usb"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            padding_0 = bytearray(5)
            command_string = command_stop_usb + type_pico + padding_0
            sock.send(command_string)

            time.sleep(0.2)
 

            channel = int(keys[1])
            assert 0 <= channel <= 11

            padding = bytearray(4)
            command_current_burst = bitstring_to_bytes(command_dict["COMMAND_current_burst"])
            bits_channel = (channel).to_bytes(1, byteorder='big')
            command_string = command_current_burst + type_pico + bits_channel + padding

            num_cycles = int(current_buffer_len/full_current_chunk)
            full_currents = []

      

    
            for cycle in range(num_cycles):
                print("cycle: " + str(cycle))
                #time.sleep(0.2) # put into config.txt later
                #sock.send(bytes(command_string,"utf-8"))
                
                
                sock.send(command_string)
                temp = sock.recv(64)
                


                for i in range(full_current_chunk):
                    byte_loop = []
                    for j in range(4):
                        byte_loop.append(temp[4*i+j])
                    full_currents.append(process_float(byte_loop))


            # send command to start usb
            time.sleep(0.5)
            command_start_usb = bitstring_to_bytes(command_dict["COMMAND_start_usb"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            padding_0 = bytearray(5)
            command_string = command_start_usb + type_pico + padding_0
            sock.send(command_string)
            
            
        

            # write into new file
            filename = "full_currents_" + str(int(time.time())) + ".txt"
            f = open(filename, "w")
            for i in full_currents:
                f.write(str(i) + "\n")
            f.close()

        elif keys[0] == "start_usb":
            # send command to stop usb
            command_start_usb = bitstring_to_bytes(command_dict["COMMAND_start_usb"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            padding_0 = bytearray(5)
            command_string = command_start_usb + type_pico + padding_0
            sock.send(command_string)
        
        elif keys[0] == "stop_usb":
            # send command to stop usb
            command_stop_usb = bitstring_to_bytes(command_dict["COMMAND_stop_usb"])
            type_pico = bitstring_to_bytes(command_dict["TYPE_pico"])
            padding_0 = bytearray(5)
            command_string = command_stop_usb + type_pico + padding_0
            sock.send(command_string)

        else:
            print("Unknown command")
    except (ValueError) as e:
        print(("Bad Input:",e))




if __name__=="__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #sock.connect('/tmp/serversock')
    host = "127.0.0.1"
    port = 12000
    sock.connect((host,port))

    while True:
        try:
            line = input("Input Command: ")
            if line:
                process_command(line)
        except AssertionError:
            print("Ensure that all arguments are valid")
        except Exception as e:
            print((type(e),e))
