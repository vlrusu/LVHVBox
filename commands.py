from tqdm.auto import tqdm
import time
import threading
#from RPiMCP23S17.MCP23S17 import MCP23S17


NCHANNELS = 6

# def test(channel):
    
#     ret = []
    
#     if channel[0] == None:
#         for i in range(NCHANNELS):
#             ret.append(i)

#     else:
#         ret.append(channel[0])

#     return ret

hvlock = threading.Lock()

class LVHVBox:
    def __init__ (self,cmdapp):
        self.mcp = 0#MCP23S17(bus=0x00, pin_cs=0x00, device_id=0x00)
        self.cmdapp = cmdapp
    

    def ramp(self,channel):
        hvlock.acquire() 
        for i in tqdm(range(10)):
            time.sleep(3)
        self.cmdapp.async_alert('Channel '+str(channel)+' done ramping')
        hvlock.release()
        
    def rampup(self,channel):
        """spi linux driver is thread safe but the exteder operations are not. However, I 
        only need to worry about the HV, since other LV stuff is on different pins and the MCP writes should 
        not affect them"""

        rampThrd = threading.Thread(target=self.ramp,args=channel)
        rampThrd.start()
        return [0]


    # def powerOn(self,channel):
    #     if channel ==  None:
    #         GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
    #         for ich in range(0,6):
    #             self.mcp1.digitalWrite(ich+8, MCP23S17.LEVEL_HIGH)


    #     else:
    #          channel = abs (channel)
    #          GPIO.output(GLOBAL_ENABLE_PIN,GPIO.HIGH)
    #          mcp1.digitalWrite(channel+8, MCP23S17.LEVEL_HIGH)
    

    def test(self,channel):

        ret = []

        if channel[0] == None:
            for i in range(NCHANNELS):
                ret.append(i)

        else:

    #        for i in range(10):
    #            app.async_alert("Testing " + str(i))
    #            time.sleep(1)
            ret.append(channel[0])

        return ret



    def readvoltage(self,channel):

        ret = []




        if channel[0] == None:
            for ich in range(NCHANNELS):
                bus.write_byte_data(0x50,0x0,ich+1)# first is the coolpac
                reading=bus.read_byte_data(0x50,0xD0)
                reading=bus.read_i2c_block_data(0x50,0x8B,2)
                value = float(reading[0]+256*reading[1])/256.

                ret.append(value)

        else:
            bus.write_byte_data(0x50,0x0,channel[0]+1)# first is the coolpac
            reading=bus.read_byte_data(0x50,0xD0)
            reading=bus.read_i2c_block_data(0x50,0x8B,2)
            value = float(reading[0]+256*reading[1])/256.

            ret.append(value)


        return ret
