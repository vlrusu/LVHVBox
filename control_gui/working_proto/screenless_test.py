import wiringpi

# import c functions for lv
from ctypes import *

import RPi.GPIO as GPIO
from RPiMCP23S17.MCP23S17 import MCP23S17
import time
import threading
import smbus
from smbus import SMBus
import serial

class Test:
    def __init__(self):
        self.initialize_data()

    def initialize_lv(self,test):
        if not test:
            self.mcp1 = MCP23S17(bus=0x00, pin_cs=0x01, device_id=0x00)
            self.mcp1.open()
            self.mcp1._spi.max_speed_hz = 10000000

            for x in range(8, 16):
                self.mcp1.setDirection(x, self.mcp1.DIR_OUTPUT)
                self.mcp1.digitalWrite(x, MCP23S17.LEVEL_LOW)

            self.I2C_sleep_time = 0.25 # seconds to sleep between each channel reading
            self.bus = SMBus(1)

            # sleep to keep i2c from complaining
            time.sleep(1)

            # setup GPIO pins
            GPIO.setup(self.GLOBAL_ENABLE_PIN,GPIO.OUT)
            GPIO.setup(self.RESET_PIN,GPIO.OUT)
            GPIO.output(self.GLOBAL_ENABLE_PIN,GPIO.LOW)
            GPIO.output(self.RESET_PIN,GPIO.HIGH)


        else:
            self.save_error("Error initializing low voltage connection.")


    def initialize_hv(self,test):
        if not test:
            self.rampup.initialization()
        else:
            self.save_error("Error initializing high voltage connection.")

    # called within a thread to actuate hv rampup
    def hv_rampup_on_off(self):
        self.is_ramping=True

        # depending on the "on" arg, actuate the hv channel
        if self.rampup_list[0][1] == True:
            self.rampup.rampup_hv(self.rampup_list[0][0],1500)
        else:
            self.rampup.rampup_hv(self.rampup_list[0][0],0)

        temp=[]
        for i in range(1,len(self.rampup_list)):
            temp.append(self.rampup_list[i])
        self.rampup_list=temp

        self.is_ramping=False

    def call_hv_data(self):
        try:
            hv_thread=threading.Thread(target=self.get_hv_data,args=[False])
            hv_thread.setDaemon(True)
            hv_thread.start()

        except:
            self.save_error("problem with call hv data")


    # acquires hv data from pico via pyserial connection
    def get_hv_data(self,test):
        # acquire hv current and voltage
        hv_voltage_1=[]
        hv_current_1=[]

        hv_voltage_2=[]
        hv_current_2=[]
        if not test:
            try:
                # make serial connection and close as soon as most recent line of data is acquired

                ser = serial.Serial('/dev/ttyACM0', 115200, timeout=2)
                line = ser.readline().decode('ascii')

                ser1 = serial.Serial('/dev/ttyACM1', 115200, timeout=2)
                line1 = ser1.readline().decode('ascii')

                # break apart the acquired pyserial output line and parse
                processed_line = line.split(" ")
                processed_line1 = line1.split(" ")

                # determine which pico is first
                picocheck1=line.split("|")[3][1]
                picocheck2=line1.split("|")[3][1]

                on_voltage=False
                end=False
                for i in processed_line:
                    if i != '' and i != '|' and on_voltage is False:
                        hv_current_1.append(float(i))
                    elif i != '' and i != '|' and on_voltage is True and end is False:
                        hv_voltage_1.append(float(i))
                    elif end is False and i == '|':
                        if on_voltage is False:
                            on_voltage = True
                        else:
                            end = True

                on_voltage=False
                end=False
                for i in processed_line1:
                    if i != '' and i != '|' and on_voltage is False:
                        hv_current_2.append(float(i))
                    elif i != '' and i != '|' and on_voltage is True and end is False:
                        hv_voltage_2.append(float(i))
                    elif end is False and i == '|':
                        if on_voltage is False:
                            on_voltage = True
                        else:
                            end = True

                # based on picocheck results, form main hv lists
                if picocheck1 == '2':
                    hv_voltage = hv_voltage_1 + hv_voltage_2
                    hv_current = hv_current_1 + hv_current_2
                else:
                    hv_voltage = hv_voltage_2 + hv_voltage_1
                    hv_current = hv_current_2 + hv_current_1



                # returned lists are flipped
                hv_current.reverse()
                hv_voltage.reverse()

                # round hv voltage
                temp=[]
                for i in hv_voltage:
                    temp.append(round(int(i),1))
                hv_voltage=temp

                assert len(hv_current) == 12
                assert len(hv_voltage) == 12
                # todo ensure proper length of hv current and voltage

            except:
                self.save_error("Error acquiring hv data")
        else:
            # if data acquisition function is in test mode, populate with bogus data for testing purposes
            for i in range(0,12):
                hv_voltage.append(round(random.uniform(1450,1550),3))
                hv_current.append(round(random.uniform(20,30),3))

        # save data lists for hv

        try:
            if len(hv_voltage) == 12 and len(hv_current) == 12:
                self.hv_voltage=hv_voltage
                self.hv_current=hv_current
        except:
            self.save_error("hv data is of improper length")



    # used to acquire assorted data from exelcys blade modules via I2C protocol
    def get_blade_data(self,test):
        # acquire Voltage
        #self.bus.pec=1
        try:
            voltage_values=[]
            if not test:
                for i in range(0,6):
                    time.sleep(self.I2C_sleep_time)
                    try:
                        self.bus.pec=1
                        # acquire the voltage measurement for each of the six blades
                        self.bus.write_byte_data(0x50,0x0,i+1)
                        reading=self.bus.read_i2c_block_data(0x50,0x8B,2)
                        value=float(reading[0]+256*reading[1])/256.

                        # append acquired voltage measurement to output list
                        voltage_values.append(round(value,3))
                        self.bus.pec=0
                    except:
                        self.bus.pec=0
                        self.save_error("Error acquiring blade voltage data on channel " + str(i))
            else:
                # for testing purposes, autopopulate with bogus data
                for i in range(0,6):
                    voltage_values.append(round(random.uniform(35,45),3))
                    # ensure delay between channel readings

            # acquire Current
            current_values=[]
            if not test:
                for i in range(0,6):
                    time.sleep(self.I2C_sleep_time)
                    try:
                        self.bus.pec=1
                        # acquire the current measurement for each of the six blades
                        self.bus.write_byte_data(0x50,0x0,i+1)
                        reading=self.bus.read_i2c_block_data(0x50,0x8C,2)
                        value=reading[0]+256*reading[1]
                        exponent=(value >> 11) & 0x1f
                        exponent=exponent-32
                        mantissa=value & 0x7ff
                        current=mantissa*2**exponent

                        # append acquired current measurement to output list
                        current_values.append(round(current,3))
                        self.bus.pec=0
                    except:
                        self.bus.pec=0
                        self.save_error("Error acquiring blade current data on channel " + str(i))
            else:
                # for testing purposes, autopopulate with bogus data
                for i in range(0,6):
                    current_values.append(round(random.uniform(10,15),3))
                    # ensure delay between channel readings

            # acquire Temperature
            temperature_values=[]
            if not test:
                for i in range(0,6):
                    time.sleep(self.I2C_sleep_time)
                    try:
                        self.bus.pec=1
                        # acquire the temperature measurement for each of the six blades
                        self.bus.write_byte_data(0x50,0x0,i+1)
                        reading=self.bus.read_i2c_block_data(0x50,0x8D,2)
                        value=reading[0]+256*reading[1]
                        exponent=(value >> 11) & 0x1f
                        mantissa = value & 0x7ff
                        temp=mantissa*2**exponent

                        # append acquired temperature measurement to output list
                        temperature_values.append(round(temp,3))
                        self.bus.pec=0
                    except:
                        self.bus.pec=0
                        self.save_error("Error acquiring blade temperature data on channel " + str(i))
            else:
                for i in range(0,6):
                    temperature_values.append(round(random.uniform(28,35),3))
                    # ensure delay between channel readings

            # save data lists for blades
            self.voltage=voltage_values
            self.current=current_values
            self.temperature=temperature_values
        except:
            self.save_error("Bus Busy")

    def get_lv_data(self,test):
        self.accessing_lv = True
        # call blade data initially
        try:
            self.get_blade_data(False)
        except:
            self.save_error("Error acquiring blade data inside get lv data.")

        # acquire readMon data
        five_voltage=[]
        five_current=[]
        cond_voltage=[]
        cond_current=[]
        # iterates through all six lv channels to acquire readMon data
        for channel in reversed(range(0,6)):
            try:
                address=self.addresses[int(channel/2)]
                ch=channel%2

                temp_vals=[]
                for index in range(4):
                    time.sleep(self.I2C_sleep_time)
                    channelLTC = (0b101<<5) + 4*ch + index
                    self.bus.write_byte(address, channelLTC)

                    time.sleep(self.I2C_sleep_time)
                    reading = self.bus.read_i2c_block_data(address, channelLTC, 3)

                    # convert I2C reading to legitimate data
                    val = ((((reading[0]&0x3F))<<16))+((reading[1]<<8))+(((reading[2]&0xE0)))
                    volts = val*self.vref/self.max_reading

                    vvolts = volts / 0.01964
                    ivolts = volts / 0.4
                    v12volts = volts * 10

                    if (ch == 0):
                        if (index%2 == 0):
                            if ( index % 4 == 0):
                                temp_vals.append(round(vvolts,3))
                            else:
                                temp_vals.append(round(v12volts,3))
                        else:
                            temp_vals.append(round(ivolts,3))
                    else:
                        if (index%2 == 1):
                            if ( index % 4 == 3):
                                temp_vals.append(round(vvolts,3))
                            else:
                                temp_vals.append(round(v12volts,3))
                        else:
                            temp_vals.append(round(ivolts,3))

                if channel%2 == 0:
                    cond_voltage.append(temp_vals[0])
                    cond_current.append(temp_vals[1])
                    five_voltage.append(temp_vals[2])
                    five_current.append(temp_vals[3])
                else:
                    cond_voltage.append(temp_vals[3])
                    cond_current.append(temp_vals[2])
                    five_voltage.append(temp_vals[1])
                    five_current.append(temp_vals[0])
            except:
                self.save_error("Error acquiring board data on channel " + str(channel))

    def save_txt(self):
        output=''
        for i in range(0,6):
            output+='ch'+str(i)
            output+=','+str(self.voltage[i])
            output+=','+str(self.current[i])
            output+=','+str(self.temperature[i])
            output+=','+str(self.five_voltage[i])
            output+=','+str(self.five_current[i])
            output+=','+str(self.cond_voltage[i])
            output+=','+str(self.cond_current[i])+','
        for i in range(0,12):
            output+='ch'+str(i)
            output+=','+str(self.hv_voltage[i])
            output+=','+str(self.hv_current[i])+','

        output+=str(time.time())
        output+='\n'

        file1=open("/home/pi/working_proto/screenless_logfile.txt", "a")
        file1.write(output)
        file1.close()

    def save_error(self,text):
        file2=open("/home/pi/working_proto/screenless_error_logfile.txt","a")
        file2.write(text)
        file2.write(str(time.time()) + "\n")
        file2.close()


    def initialize_data(self):
        # set vars to control timers
        self.board_time=20000
        self.hv_time=2500
        self.save_time=60000
        self.hv_display_time=2000

        self.max_reading = 8388608.0
        self.vref = 3.3
        self.pins = ["P9_15","P9_15","P9_15","P9_27","P9_41","P9_12"]
        self.GLOBAL_ENABLE_PIN =  15
        self.RESET_PIN = 32
        self.addresses = [0x14,0x16,0x26]

        # set vars to track hardware connections in threads
        self.acquiring_hv = False
        self.accessing_lv = False
        self.hv_lock_time=time.time()
        self.hv_threadlist=[]

        # keeps lv screen update from occuring until data is acquired
        self.initial_lv_display=True

        # initialize lists of data
        self.blade_voltage_plot=[[500]*10]*6
        self.blade_current_plot=[[500]*10]*6
        self.blade_temperature_plot=[[500]*10]*6

        self.board_5v_voltage_plot=[[500]*10]*6
        self.board_5v_current_plot=[[500]*10]*6
        self.board_cond_voltage_plot=[[500]*10]*6
        self.board_cond_current_plot=[[500]*10]*6

        self.hv_voltage_plot=[[10000]*10]*12
        self.hv_current_plot=[[10000]*10]*12

        self.stability_blade_voltage_plot=[[500]*48]*6
        self.stability_blade_current_plot=[[500]*48]*6
        self.stability_blade_temperature_plot=[[500]*48]*6

        self.stability_board_5v_voltage_plot=[[500]*48]*6
        self.stability_board_5v_current_plot=[[500]*48]*6
        self.stability_board_cond_voltage_plot=[[500]*48]*6
        self.stability_board_cond_current_plot=[[500]*48]*6

        self.stability_hv_voltage_plot=[[10000]*48]*12
        self.stability_hv_current_plot=[[10000]*48]*12

        # fill blade table with entries and set background color
        self.blade_voltage_entries=[]
        self.blade_current_entries=[]
        self.blade_temperature_entries=[]

        # keeps track of blade power statuses
        self.blade_power=[False]*6

        # keeps track of hv power statuses
        self.hv_power=[False]*12

        # vars to keep track of hv ramping
        self.is_ramping = False
        self.rampup_list=[]

        self.hv_voltage = [0]*12
        self.hv_current = [0]*12

        self.voltage = [0]*6
        self.current = [0]*6
        self.temperature = [0]*6
        self.five_voltage = [0]*6
        self.five_current = [0]*6
        self.cond_voltage = [0]*6
        self.cond_current = [0]*6

    def call_lv_data(self):
        try:
            if not self.accessing_lv:
                threading.Thread(target=self.get_lv_data,args=[False]).start()
        except:
            self.save_error("Error calling lv data")

    def power_on(self,channel):
        channel=abs(channel-5)
        GPIO.output(self.GLOBAL_ENABLE_PIN,GPIO.HIGH)
        self.mcp1.digitalWrite(channel+8, MCP23S17.LEVEL_HIGH)

    def power_off(self,channel):
        channel=abs(channel-5)
        self.mcp1.digitalWrite(channel+8, MCP23S17.LEVEL_LOW)




if __name__=="__main__":
    window = Test()

    window.initialize_lv(False)

    try:
        window.initialize_lv(False)
        window.initialize_lv(False)
        window.initialize_lv(False)
    except:
        window.save_error("Error initializing LV in main")

    # import c functions for hv
    rampup = "/home/pi/working_proto/python_connect.so"
    window.rampup=CDLL(rampup)
    window.test = False

    window.initialize_data()

    try:
        window.initialize_hv(False)
        print("high voltage initialized")
    except:
        window.save_error("Error intializing HV in main")

    # power on all lv channels
    for i in range(0,6):
        window.power_on(i)
    print("lv channels powered on")

    # power on all hv channels
    for i in range(0,12):
        window.rampup.rampup_hv(i,1500)
    print("hv channels powered on")

    while True:
        window.call_lv_data()
        time.sleep(20)
        window.call_hv_data()
        time.sleep(10)
        window.save_txt()
        time.sleep(2)
