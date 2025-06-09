import serial
import gpiod  # Replacement for RPi.GPIO
import time
import struct
import json

import argparse


# RS-485 Driver Direction Control
RS485_DIR_PIN = 24  # GPIO24 for DE/RE control

#DRAC reset pin is 25

chip = gpiod.Chip('gpiochip4')

rs485_en_line = chip.get_line(RS485_DIR_PIN)
rs485_en_line.request(consumer="MYDEVICE",type=gpiod.LINE_REQ_DIR_OUT)


# UART Configuration
UART_PORT = "/dev/ttyAMA0"  # Adjust for your UART device
BAUD_RATE = 38400


def parse_args():

    parser = argparse.ArgumentParser(description="Send RS485 command and process response.")
    parser.add_argument("address", type=int, help="9-bit address (0–512)")
    parser.add_argument("--name", help="Name of the parameter to read (if omitted, reads all)")
    return parser.parse_args()



# RS-485 Direction Control
def set_rs485_transmit():
    rs485_en_line.set_value(1)

def set_rs485_receive():
    rs485_en_line.set_value(0)

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
    time.sleep(0.02)  # Small delay for DE stabilization
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
        ser= initialize()

        targets = [args.name] if args.name else list(rules.keys())

        for name in targets:
            if name not in rules:
                print(f"{name}: not found in JSON")
                continue

            rule = rules[name]
            cmdid = rule["cmdid"]
            expression = rule["expression"]

            send_rs485_data(ser, address, cmdid)
            received_data = receive_rs485_data(ser)

            if not received_data or len(received_data) < 3:
                print(f"{name}: No response or incomplete")
                continue

            if received_data[0] == 0xEF:
                lsb = received_data[1]
                msb = received_data[2]
                combined_word = (msb << 8) | lsb
                transformed = apply_transformation(combined_word, expression)
                print(f"{name:<20} = {transformed:8.2f}")
            else:
                print(f"{name}: Invalid start byte")
        

    except KeyboardInterrupt:
        print("Exiting Program")
    finally:
        ser.close()

