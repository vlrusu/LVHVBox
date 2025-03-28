import argparse
import rlcompleter
import readline
import socket
import time
import struct
from collections import namedtuple
import ctypes
from Connection import Connection

HISTORY_REQUEST_MAX = 100
current_buffer_len = 8000  # must be divisible by 10
full_current_chunk = 10
COMMAND_BYTE_LENGTH = 13

parser = argparse.ArgumentParser()


Command = namedtuple(
    "Command",
    "name type_key cmd_output_str_format in_val_type is_channel_cmd",
    defaults=[None, float, True],
)


commands = [
    Command("current_buffer_run", "pico", "Current buffer status, {:}"),
    Command("current_burst", "pico"),  # Not like the others. Handled differently.
    Command("current_start", "pico"),
    Command("current_stop", "pico"),
    Command("disable_ped", "pico"),
    Command("disable_trip", "pico"),
    Command("down_hv", "hv"),
    Command("enable_ped", "pico"),
    Command("enable_trip", "pico"),
    Command("get_ihv", "pico", "{:.2f} uA"),
    Command("get_slow_read", "pico", "Slow read {:}"),
    Command("get_vhv", "pico", "{:.2f} V"),
    Command("powerOff", "lv"),
    Command("powerOn", "lv"),
    Command("ramp_hv", "hv"),
    Command("readMonI48", "lv", "{:.2f} A"),
    Command("readMonI6", "lv", "{:.2f} A"),
    Command("readMonV48", "lv", "{:.2f} V"),
    Command("readMonV6", "lv", "{:.2f} V"),
    Command("reset_trip", "pico"),
    Command("set_trip", "pico"),
    Command("set_trip_count", "pico", in_val_type=int),
    Command("start_usb", "pico"),
    Command("stop_usb", "pico"),
    Command("trip", "pico"),
    Command("trip_status", "pico", "Trip status {:d}"),
    Command("trip_enabled", "pico", "Trip enabled {:d}"),
    Command("update_ped", "pico"),
    Command("pcb_temp", "pico", "PCB Temperature, {:.2f} C", is_channel_cmd=False),
    Command("pico_current", "pico", "Pico Current, {:.2f} A", is_channel_cmd=False),
]


# there are 12 (0-11) hv and 6 (0-5) lv channels.  issuing a command with idx
# -1 will issue the command for all channels in sequence.
n_channels = {"pico": 12, "hv": 12, "lv": 6}


if "libedit" in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")


def binary(num):
    return "".join("{:0>8b}".format(c) for c in struct.pack("!f", num))


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
        # command_dict[i[1]] = format(int(i[2]), '032b')
        # command_dict[i[1]] = struct.pack('<I', int(i[2])).decode('utf-8')
        string = format(int(i[2]), "032b")
        # print(string)

        # command_dict[i[1]] = bstring_to_chars(string)
        command_dict[i[1]] = int(i[2])

    # print(str(command_dict))
    return command_dict


def process_float(input):
    v = (
        format(input[3], "008b")
        + format(input[2], "008b")
        + format(input[1], "008b")
        + format(input[0], "008b")
    )

    sign = (-1) ** int(v[0], 2)
    exponent = int(v[1:9], 2) - 127
    mantissa = int(v[9::], 2)
    float_val = sign * (1 + mantissa * (2**-23)) * 2**exponent

    return float_val


def float_to_bytes(input):
    pass


def bitstring_to_bytes(s):
    return int(s, 2).to_bytes(4, byteorder="big")


def completer(text, state):
    options = [x.name for x in commands if x.name.startswith(text)]
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


# interpret number from format_string provided and print it
def process_response(blocks, format_str):
    number = blocks[0][0]
    print(format_str.format(number))


# ship it. socket.send(command_string)
def send_command(connection, command, channel=None, val=0.0):
    command_dict = read_commands()
    cmd = ctypes.c_uint(command_dict["COMMAND_" + command.name])
    typ = ctypes.c_uint(command_dict["TYPE_" + command.type_key])
    channel = channel if channel else 0
    channel = ctypes.c_char(channel)
    if command.in_val_type == float:
        value = ctypes.c_float(float(val))
    else:
        value = ctypes.c_int(int(val))

    connection.send_message(cmd, typ, channel, value)


# wrap command execution in a try except to keep it clean
def safe_command_execution(func):
    def wrapper(sock, command, channel=None, val=None):
        try:
            return func(sock, command, channel, val)
        except ValueError as e:
            print("Bad Input:", e)
        except AssertionError:
            print("Channel number is out of allowed range")
        except TypeError:
            print("Pico not found")

    return wrapper


# sanity check -> send command -> process response
@safe_command_execution
def execute_command(sock, command, channel, val):
    if channel is not None:
        if command.type_key != "lv":
            assert -1 <= channel < n_channels[command.type_key]
        else:
            assert -1 <= channel < n_channels[command.type_key]+1
    send_command(sock, command, channel, val)
    cmd_output = sock.recv_message()
    if command.cmd_output_str_format:
        if channel is not None:
            fmt = f"Channel {channel} " + command.cmd_output_str_format
            process_response(cmd_output, fmt)
        else:
            process_response(cmd_output, command.cmd_output_str_format)


def current_burst(keys):
    channel = int(keys[1])

    command_dict = read_commands()

    assert 0 <= channel <= 11

    cmd = ctypes.c_uint(command_dict["COMMAND_current_burst"])
    typ = ctypes.c_uint(command_dict["TYPE_pico"])
    channel = ctypes.c_char(channel)
    padding = ctypes.c_float(0.0)
    command_string = command_current_burst + type_pico + bits_channel + padding

    num_cycles = int(current_buffer_len / full_current_chunk)
    full_currents = []

    for cycle in range(num_cycles):
        print("cycle: " + str(cycle))
        # time.sleep(0.2) # put into config.txt later
        # sock.send(bytes(command_string,"utf-8"))

        sock.send_message(cmd, typ, channel, padding)
        samples = socks.recv_message()
        for sample in samples:
            full_currents.append(sample)

    # write into new file
    filename = "full_currents_" + str(int(time.time())) + ".txt"
    f = open(filename, "w")
    for i in full_currents:
        f.write(str(i) + "\n")
    f.close()


# parse user input and issue a command
def process_command(line):
    keys = line.split(" ")  # command <channel> <input_value>

    command = next((c for c in commands if c.name == keys[0]), None)

    if command == None:
        print("Unknown command")
        return

    if command.name == "current_burst":
        return current_burst(keys)

    if command.is_channel_cmd:
        channel = None
        in_val = 0.0
        try:
            channel = int(keys[1])
        except IndexError:
            channel = -1
        try:
            in_val = keys[2]
        except IndexError:
            in_val = 0.0
        # channel = -1 if len(keys) != 2 else int(keys[1])
        # in_val = None if len(keys) != 3 else keys[2]
        if channel == -1:  # Handle all channels
            # Server expects special channel arg for powering off all channels.
            # This works, or we could change how the server works.
            if command.name == "powerOff":
                execute_command(connection, command, 6, in_val)
                return
            for channel in range(n_channels[command.type_key]):
                execute_command(connection, command, channel, in_val)
                time.sleep(0.05)
        else:
            execute_command(connection, command, channel, in_val)
    else:
        execute_command(connection, command)


if __name__ == "__main__":
    host = '127.0.0.1'
    port = 12000
    connection = Connection(host, port)

    while True:
        try:
            line = input("Input Command: ")
            if line:
                process_command(line)
        except AssertionError:
            print("Ensure that all arguments are valid")
        # ejc: no cleanup == bad
        except EOFError:
            exit(0)
        except Exception as e:
            print((type(e), e))
