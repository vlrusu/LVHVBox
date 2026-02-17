


import serial
import gpiod  # Replacement for RPi.GPIO
import time
import struct
import json

import argparse


import gpiod
from gpiod.line import Direction, Value

GPIOCHIP = "/dev/gpiochip0"   # might be /dev/gpiochip4 on Pi 5; see note below
RS485_DIR_PIN = 24            # this must be the LINE OFFSET on that chip

rs485_req = gpiod.request_lines(
    GPIOCHIP,
    consumer="LVHVBox-rs485-dir",
    config={
        RS485_DIR_PIN: gpiod.LineSettings(
            direction=Direction.OUTPUT,
            output_value=Value.INACTIVE,  # start low
        )
    },
)

def set_rs485_transmit():
    rs485_req.set_value(RS485_DIR_PIN, Value.ACTIVE)    # high

def set_rs485_receive():
    rs485_req.set_value(RS485_DIR_PIN, Value.INACTIVE)  # low



# UART Configuration
UART_PORT = "/dev/ttyAMA0"  # Adjust for your UART device
BAUD_RATE = 38400


def parse_args():

    parser = argparse.ArgumentParser(description="Send RS485 command and process response.")
    parser.add_argument("address", type=int, help="9-bit address (0–512)")
    parser.add_argument("--name", help="Name of the parameter to read (if omitted, reads all)")
    return parser.parse_args()




# Initialize GPIO and UART
def initialize():
    set_rs485_transmit()  # Default to receive mode

    ser = serial.Serial(
        port=UART_PORT,
        baudrate=BAUD_RATE,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=5,
    )
    return ser

def compose_cmd(address,cmd):

    data = b""


    msb = (address >> 8) & 0x01        # extract bit 8
    lsbs = 0b1011010                   # fixed pattern

    byte1 = (msb << 7) | lsbs         # MSB + fixed LSBs
    byte2 = address & 0xFF            # lower 8 bits

    data += struct.pack('B',byte1)
    data += struct.pack('B',byte2)
    data += struct.pack('B',cmd)
    return data
    
# Send Data
def send_rs485_data(ser,address,cmd):
    data = compose_cmd(address,cmd)
    set_rs485_transmit()  # Set to transmit mode
    time.sleep(0.1)  # Small delay for DE stabilization
    ser.write(data)  # Send data
    ser.flush()  # Wait for data to be sent

# Receive Data
def receive_rs485_data(ser):
    set_rs485_receive()  # Default to receive mode
    data = ser.read(3)  # Read up to 100 bytes (adjust as needed)
    set_rs485_transmit()  # Set to transmit mode
    return data


def apply_transformation(x,expression):


    local_vars = {"x": x}
    result = eval(expression, {"__builtins__": {}}, local_vars)

    return result


# Main
if __name__ == "__main__":


    args = parse_args()
    address = args.address
    name = args.name


    
    json_path = "transformations.json"
    with open(json_path, 'r') as f:
        rules = json.load(f)


    
    try:

        targets = [args.name] if args.name else list(rules.keys())

        for name in targets:
            if name not in rules:
                print(f"{name}: not found in JSON")
                continue

            time.sleep(0.5)
            rule = rules[name]
            cmdid = rule["cmdid"]
            expression = rule["expression"]
            format_spec = rule.get("format", "float")  # default to "float" if not present

            time.sleep(0.2)

            ser= initialize()

            time.sleep(0.2)
            
            send_rs485_data(ser, address, cmdid)

            received_data = receive_rs485_data(ser)
#            print(len(received_data))
#            print(received_data)
            if not received_data or len(received_data) < 3:
                print(f"{name}: No response or incomplete")
                continue

            if received_data[0] == 0xEF:
                lsb = received_data[1]
                msb = received_data[2]
                combined_word = (msb << 8) | lsb
                transformed = apply_transformation(combined_word, expression)
                if format_spec == "int":
                    print(f"{name:<20} = {transformed:8d}")
                elif format_spec == "hex":
                    print(f"{name:<20} = {int(transformed):#010x}")
                else:
                    print(f"{name:<20} = {transformed:8.4f}")
            else:
                print(f"{name}: Invalid start byte")

            ser.close()

    except KeyboardInterrupt:
        print("Exiting Program")
