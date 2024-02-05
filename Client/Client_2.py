import argparse
import rlcompleter
import readline
import socket
import time

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
    'set_trip',
    'powerOn',
    'powerOff',
    'readMonV48',
    'readMonI48',
    'readMonV6',
    'readMonI6',
    'enable_ped',
    'disable_ped'}



if "libedit" in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")

def process_float(input):
    v = format(input[3], '008b') + format(input[2], '008b') + format(input[1], '008b') + format(input[0], '008b')

    sign = (-1) ** int(v[0],2)
    exponent = int(v[1:9],2)-127
    mantissa = int(v[9::],2)
    float_val = sign * (1+mantissa*(2**-23)) * 2**exponent
    
    return float_val

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
    
    keys = line.split(" ")

    try:
        if keys[0] == "get_vhv":
            channel = int(keys[1])
            assert 0 <= channel <= 12

            command_string = "aa" + chr(channel+97) + "      "

            sock.send(bytes(command_string,"utf-8"))
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)
            print("Channel " + str(channel) + " voltage: " + str(return_val) + " V")

        elif keys[0] == "get_ihv":
            channel = int(keys[1])
            assert 0 <= channel <= 12

            command_string = "ba" + chr(channel+97) + "      "

            sock.send(bytes(command_string,"utf-8"))
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)
            print("Channel " + str(channel) + " current: " + str(return_val) + " uA")

        elif keys[0] == "readMonV48":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_string = "gb" + chr(channel+97) + "      "
            sock.send(bytes(command_string,"utf-8"))
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)
            print("Channel " + str(channel) + " current: " + str(return_val) + " V")
        
        elif keys[0] == "readMonI48":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_string = "hb" + chr(channel+97) + "      "
            sock.send(bytes(command_string,"utf-8"))
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)
            print("Channel " + str(channel) + " current: " + str(return_val) + " A")
        
        elif keys[0] == "readMonV6":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_string = "ib" + chr(channel+97) + "      "
            sock.send(bytes(command_string,"utf-8"))
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)
            print("Channel " + str(channel) + " voltage: " + str(return_val) + " V")

        elif keys[0] == "readMonI6":
            channel = int(keys[1])
            assert 0 <= channel <= 5

            command_string = "jb" + chr(channel+97) + "      "
            sock.send(bytes(command_string,"utf-8"))
            temp = sock.recv(1024)
            return_val = round(process_float(temp),2)
            print("Channel " + str(channel) + " current: " + str(return_val) + " A")

        elif keys[0] == "current_buffer_run":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "+a" + chr(channel+97) + "         "
            sock.send(bytes(command_string,"utf-8"))
        
            temp = sock.recv(1024)
            return_val = int(temp[0])
            print("Current buffer run: " + str(return_val))
        
        elif keys[0] == "trip_status":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "oc" + chr(channel+97) + "         "
            sock.send(bytes(command_string,"utf-8"))

            temp = sock.recv(1024)
            return_val = int(temp[0])
            print("Trip status: " + str(return_val))
        
        elif keys[0] == "get_slow_read":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "ya" + chr(channel+97) + "         "
            sock.send(bytes(command_string,"utf-8"))

            temp = sock.recv(1024)
            return_val = int(temp[0])
            print("Slow read: " + str(return_val))

        elif keys[0] == "current_start":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = ")a" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))

        elif keys[0] == "current_stop":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "*a" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))

        elif keys[0] == "down_hv":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "da" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))
        
        elif keys[0] == "trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "kc" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))
        
        elif keys[0] == "reset_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "lc" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))
        
        elif keys[0] == "disable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "mc" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))

        elif keys[0] == "enable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "nc" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))
        
        elif keys[0] == "powerOn":
            if len(keys) == 2:
                channel = int(keys[1])
            else:
                channel = 6
            assert 0 <= channel <= 5
            
            command_string = "eb" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))
        
        elif keys[0] == "powerOff":
            if len(keys) == 2:
                channel = int(keys[1])
            else:
                channel = 6
            assert 0 <= channel <= 5
            
            command_string = "fb" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))

        elif keys[0] == "enable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "nc" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))

        elif keys[0] == "disable_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "mc" + chr(channel+97) + "          "
            sock.send(bytes(command_string,"utf-8"))

        elif keys[0] == "set_trip":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "pc" + chr(channel+97) + str(float(keys[2]))
            sock.send(bytes(command_string,"utf-8"))
        
        elif keys[0] == "ramp_hv":
            channel = int(keys[1])
            assert 0 <= channel <= 11

            command_string = "ca" + chr(channel+97) + str(float(keys[2]))
            sock.send(bytes(command_string,"utf-8"))
        
        elif keys[0] == "current_burst":
            channel = int(keys[1])
            assert 0 <= channel <= 11
            
            command_string = "(a" + chr(channel+97) + "         "

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








        else:
            print("Unknown command")
    except (ValueError) as e:
        print(("Bad Input:",e))





if __name__=="__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = "127.0.0.1"
    port = 12000
    sock.connect((host,port))

    try:
        while True:
            line = input("Input Command: ")
            if line:
                process_command(line)
    except Exception as e:
        print((type(e),e))
    finally:
        print('Ending...')
