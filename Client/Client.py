import socket
import cmd2
import json
import readline
import os
import atexit
import threading
import struct
import time


current_buffer_len = 8000 # must be divisible by 10
full_current_chunk = 10

# list order is:
#   -command name
#   -command type
#   -num char args
#   -num float args
#   -read bytes
#   -allow 0 input vars
#   -return value type: int 0 float 1 none 2 special 3

valid_commands = {"get_vhv": ["a","a",1,0,4,0,1],
                "get_ihv": ["b","a",1,0,4,0,1],
                "current_burst": ["(", "a", 1, 0, 100, 0, 3],
                "current_start": [")", "a", 1, 0, 0, 0, 2],
                "current_stop": ["*", "a", 1, 0, 0, 0, 2],
                "current_buffer_run": ["+", "a", 1, 0, 4, 0, 0],
                "ramp_hv": ["c","a",1,1,0,0,2],
                "down_hv": ["d","a",1,0,0,0,2],
                "trip": ["k","c",1,0,0,0,2],
                "reset_trip": ["l","c",1,0,0,0,2],
                "disable_trip": ["m","c",1,0,0,0,2],
                "enable_trip": ["n","c",1,0,0,0,2],
                "trip_status": ["o","c",1,0,4,0,0],
                "set_trip": ["p","c",1,1,0,0,2],
                "powerOn": ["e","b",1,0,0,1,2],
                "powerOff": ["f","b",1,0,0,1,2],
                "readMonV48": ["g","b",1,0,4,0,1],
                "readMonI48": ["h","b",1,0,4,0,1],
                "readMonV6": ["i","b",1,0,4,0,1],
                "readMonI6": ["j","b",1,0,4,0,1],
                "enable_ped": ['%',"c",1,0,0,0,2],
                "disable_ped": ["&", "c",1,0,0,0,2]
}



def process_float(input):
    v = format(input[3], '008b') + format(input[2], '008b') + format(input[1], '008b') + format(input[0], '008b')

    sign = (-1) ** int(v[0],2)
    exponent = int(v[1:9],2)-127
    mantissa = int(v[9::],2)
    float_val = sign * (1+mantissa*(2**-23)) * 2**exponent
    
    return float_val


def process_input(input):
    # list order is:
    #   -command name
    #   -command type
    #   -num char args
    #   -num float args
    #   -read bytes
    
    # parse input into components
    split_command = input.split(" ")


    # check if command is valid
    if split_command[0] not in valid_commands.keys():
        return 0

    # check if args are numeric
    for item in split_command[1::]:
        try:
            temp = float(item)
        except:
            return 0
    
    # check if there's a valid number of args
    desired_args = valid_commands[split_command[0]][2] + valid_commands[split_command[0]][3]
    if desired_args != len(split_command[1::]):
        if valid_commands[split_command[0]][5] == 0:
            return 0
        else:
            split_command.append(6)
        
    # check if channel arg is within proper range
    if valid_commands[split_command[0]][1] in ['a','c']:
        if int(split_command[1]) not in list(range(6)):
            return 0
    
    if valid_commands[split_command[0]][1] == 'b':
        if int(split_command[1]) not in list(range(7)):
            return 0
    
    # check if float is in valid range
    if valid_commands[split_command[0]][3] != 0:
        if float(split_command[2]) >= 10000:
            return 0
    


    # create output list of command and args

    try:
        arg_list = [int(arg) for arg in split_command[1::]]
        return_list = [split_command[0]] + arg_list
        return return_list
    except:
        return 0

def handle_current_burst():
    num_cycles = int(current_buffer_len/full_current_chunk)
    full_currents = []

    for cycle in range(num_cycles):
        print("cycle: " + str(cycle))
        #time.sleep(0.2) # put into config.txt later
        sock.send(bytes(command_string,"utf-8"))
        temp = sock.recv(64)

        print("length of full currents: " + str(len(temp)))

        for i in range(full_current_chunk):
            byte_loop = []
            for j in range(4):
                byte_loop.append(temp[4*i+j])
            print("current index: " + str(byte_loop))
            full_currents.append(process_float(byte_loop))
        
    print(full_currents)
    print("length of full currents: " + str(len(full_currents)))

    # write into new file
    filename = "full_currents_" + str(int(time.time())) + ".txt"
    f = open(filename, "w")
    for i in full_currents:
        f.write(str(i) + "\n")
    f.close()





if __name__=="__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = "127.0.0.1"
    port = 12000
    sock.connect((host,port))


    while True:
        # list order is:
        #   -command name
        #   -command type
        #   -num char args
        #   -num float args
        #   -read bytes
        
        command_input = input("Please input command: ")
        processed_input = process_input(command_input)

        if processed_input == 0:
            print("Check that input is valid")
        else:
            # create command string
            required_filler = 7 - valid_commands[processed_input[0]][2] - 6*valid_commands[processed_input[0]][3]
            command_string = valid_commands[processed_input[0]][0]
            command_string += valid_commands[processed_input[0]][1]

            if valid_commands[processed_input[0]][2] == 1:
                command_string += chr(processed_input[1]+97)
    
            else:
                command_string += 'a'

            
            if valid_commands[processed_input[0]][3] != 0:
                float_val = float(processed_input[2])



                len_float_string = len(str(float_val))
                pad = 6-len_float_string
                command_string += ''.join("0" for i in range(pad))

                command_string += str(float_val)
            else:
                command_string += ''.join("0" for i in range(6))

            command_string += ''.join(chr(0) for i in range(required_filler))


            


            return_val_type = valid_commands[processed_input[0]][6]
 
      
            if return_val_type == 3:
                # if return value requires special considerations
                print(command_string)
                if command_string[0:2] == """(a""":
                    handle_current_burst()
            elif return_val_type == 1:
                sock.send(bytes(command_string,"utf-8"))
    
                

                temp = sock.recv(1024)

                # if return value is float
                return_val = process_float(temp)
                print(return_val)
            elif return_val_type == 0:
                sock.send(bytes(command_string,"utf-8"))
                

                temp = sock.recv(1024)

                # if return value is int
                return_val = int(temp[0])
                print(return_val)
            else:
                sock.send(bytes(command_string,"utf-8"))

            

                
             


