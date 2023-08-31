import socket
import cmd2
import json
import readline
import os
import atexit
import threading
import struct

# list order is:
#   -command name
#   -command type
#   -num char args
#   -num float args
#   -read bytes

valid_commands = {"get_vhv": ["a","a",1,0,4],
                "get_ihv": ["b","a",1,0,4],
                "ramp_hv": ["c","a",1,1,0],
                "down_hv": ["d","a",1,0,0],
                "trip": ["k","c",1,0,0],
                "reset_trip": ["l","c",1,0,0],
                "disable_trip": ["m","c",1,0,0],
                "enable_trip": ["n","c",1,0,0],
                "trip_status": ["o","c",1,0,4],
                "set_trip": ["p","c",1,1,0],
                "powerOn": ["e","b",1,0,0],
                "powerOff": ["f","b",1,0,0],
                "readMonV48": ["g","b",1,0,4],
                "readMonI48": ["h","b",1,0,4],
                "readMonV6": ["i","b",1,0,4],
                "readMonI6": ["j","b",1,0,4],
                "enable_ped": ['%',"c",1,0,0],
                "disable_ped": ["&", "c",1,0,0]
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
        return 0
        
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


            sock.send(bytes(command_string,"utf-8"))

            # if applicable, read return value
            if valid_commands[processed_input[0]][4] > 0:
                temp = sock.recv(1024)
                return_val = process_float(temp)
                
                print(return_val)


