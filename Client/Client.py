#!/usr/bin/env python3
import argparse
import rlcompleter
import readline
import socket
import time
import struct
import subprocess
from collections import namedtuple
import ctypes
from MessagingConnection import MessagingConnection
import sys
import os
import matplotlib.pyplot as plt

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
    Command("set_hv_by_dac", "hv"),
    Command("query_hv_dac_cache", "hv", "{:d} dac"),
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
    Command("trip_currents", "pico", "Trip currents {:.2f}uA"),
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


command_dict = {}
def read_commands(path):
    file = open(path, "r")
    pre_command_list = file.readlines()
    pre_command_list = [i.split() for i in pre_command_list]

    global command_dict
    for i in pre_command_list:
        string = format(int(i[2]), "032b")
        command_dict[i[1]] = int(i[2])

    return command_dict

def command_map():
    global command_dict
    if command_dict is None:
        raise Exception("uninitialized command map")
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


HISTORY_FILENAME = "lvhvclient.remote.hist"
if os.path.exists(HISTORY_FILENAME):
    readline.read_history_file(HISTORY_FILENAME)

readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

parser = argparse.ArgumentParser()
parser.add_argument(
    "host",
    nargs="?",
    default="localhost",
    help="Hostname like psu15 or fully-qualified mu2e-trk-psu15.fnal.gov. Use localhost/127.0.0.1 to skip SSH tunnel.",
)
parser.add_argument(
    "--user",
    default="mu2e",
    help="SSH username for the remote host",
)
parser.add_argument(
    "--gateway",
    default="mu2egateway01.fnal.gov",
    help="SSH jump host",
)
parser.add_argument(
    "--local-port",
    type=int,
    default=12000,
    help="Local port to forward to the remote server",
)
parser.add_argument(
    "--remote-port",
    type=int,
    default=12000,
    help="Remote server port to forward",
)
parser.add_argument(
    "--header",
    type=str,
    default="/etc/mu2e-tracker-lvhv-tools/commands.h",
    help="Path to opcode macro header"
)
args = parser.parse_args()


def create_command_string_default():
    pass


# interpret number from format_string provided and print it
def process_response(blocks, format_str):
    values = blocks[0]
    if len(values) > 1:
        for channel, number in enumerate(values):
            print(f"Channel {channel} " + format_str.format(number))
    else:
        number = values[0]
        print(format_str.format(number))


# ship it. socket.send(command_string)
def send_command(connection, command, channel=None, val=0.0):
    command_dict = command_map()
    cmd = ctypes.c_uint(command_dict["COMMAND_" + command.name])
    typ = ctypes.c_uint(command_dict["TYPE_" + command.type_key])
    channel = channel if channel else 0
    channel = ctypes.c_char(channel)
    if command.in_val_type == float:
        if val is None:
            val = 0.0
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
            assert -1 <= channel < n_channels[command.type_key] + 1
    send_command(sock, command, channel, val)
    cmd_output = sock.recv_message()
    if command.cmd_output_str_format:
        if channel is not None and len(cmd_output[0]) == 1:
            fmt = f"Channel {channel} " + command.cmd_output_str_format
            process_response(cmd_output, fmt)
        else:
            process_response(cmd_output, command.cmd_output_str_format)


def current_burst(sock, keys):
    channel = int(keys[1])

    command_dict = command_map()

    assert 0 <= channel <= 11

    cmd = ctypes.c_uint(command_dict["COMMAND_current_burst"])
    typ = ctypes.c_uint(command_dict["TYPE_pico"])
    channel = ctypes.c_char(channel)
    padding = ctypes.c_float(0.0)

    num_cycles = int(current_buffer_len / full_current_chunk)
    full_currents = []

    sock.send_message(cmd, typ, channel, padding)
    time.sleep(1)
    full_currents = sock.recv_message()

    full_currents = list(full_currents[0])
    filename = "full_currents_" + str(int(time.time())) + ".txt"
    f = open(filename, "w")
    for i in full_currents:
        f.write(str(i) + "\n")
    f.close()

    time_step = 0.2  # change this if your interval is different
    time_series = [i * time_step for i in range(len(full_currents))]
    plt.figure(figsize=(10, 4))
    print(full_currents)
    plt.plot(time_series, full_currents,  marker='o', linestyle='-')
    plt.title("Full Currents Time Series")
    plt.xlabel("Sample Index")
    plt.ylabel("Current (µA)")  # update unit accordingly
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    

def normalize_host(hostname):
    if hostname in ("localhost", "127.0.0.1"):
        return hostname
    if "." in hostname:
        return hostname
    return f"mu2e-trk-{hostname}.fnal.gov"


def local_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def ensure_tunnel(host, user, gateway, local_port, remote_port):
    if local_port_open(local_port):
        local_port = find_free_port()
        print(f"Local port in use, using {local_port} instead")
    ssh_cmd = [
        "ssh",
        "-f",
        "-KX",
        "-N",
        "-L",
        f"{local_port}:localhost:{remote_port}",
        f"{user}@{host}",
        "-J",
        gateway,
    ]
    result = subprocess.run(ssh_cmd)
    if result.returncode != 0:
        raise RuntimeError("Failed to establish SSH tunnel")
    for _ in range(10):
        if local_port_open(local_port):
            return local_port
        time.sleep(0.2)
    raise RuntimeError("SSH tunnel did not become ready")


# parse user input and issue a command
def process_command(line):
    keys = line.split(" ")  # command <channel> <input_value>
    keys = [k for k in keys if 0 < len(k)]

    command = next((c for c in commands if c.name == keys[0]), None)

    if command == None:
        print("Unknown command")
        return

    if command.name == "current_burst":
        return current_burst(connection, keys)

    if command.is_channel_cmd:
        channel = None
        in_val = 0.0
        if len(keys) < 2:
            channel = -1
        elif command.name in ("set_trip", "set_hv_by_dac"):
            if keys[1] == "all":
                channel = -1
                try:
                    in_val = keys[2]
                except IndexError:
                    in_val = 0.0
            else:
                try:
                    channel = int(keys[1])
                except (IndexError, ValueError):
                    channel = -1
                try:
                    in_val = keys[2]
                except IndexError:
                    in_val = 0.0
        else:
            try:
                channel = int(keys[1])
            except IndexError:
                channel = -1
            except ValueError:
                channel = -1
            try:
                in_val = keys[2]
            except IndexError:
                in_val = 0.0
        if channel == -1:  # Handle all channels
            if command.name == "powerOff":
                execute_command(connection, command, 6, in_val)
                return
            if command.name in ("readMonV48", "readMonI48", "readMonV6", "readMonI6"):
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
    host = normalize_host(args.host)
    if host in ("localhost", "127.0.0.1"):
        connection = MessagingConnection(host, args.remote_port)
    else:
        port = ensure_tunnel(
            host, args.user, args.gateway, args.local_port, args.remote_port
        )
        connection = MessagingConnection("127.0.0.1", port)

    path = args.header
    read_commands(path)

    try:
        while True:
            line = input("Input Command: ")
            if line:
                process_command(line)
    except KeyboardInterrupt:
        exit(0)
    except AssertionError:
        print("Ensure that all arguments are valid")
    except EOFError:
        exit(0)
    except Exception as e:
        print((type(e), e))
    finally:
        print("Ending...")
        readline.write_history_file(HISTORY_FILENAME)
