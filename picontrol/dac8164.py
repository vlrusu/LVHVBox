from MCP23S08 import MCP23S08
import time
import copy

class dac8164:
    def __init__(self,MCP,sync,sclk,sdi,enable_pin=-1,ldac_pin=-1):
        self.MCP = MCP
        self.sync_pin = sync
        self.sclk_pin = sclk
        self.sdi_pin = sdi
        self.enable_pin = enable_pin
        self.ldac_pin = ldac_pin

        DAC8164DELAY = 2

        DAC_REFERENCE_ALWAYS_POWERED_DOWN = 0x2000
        DAC_REFERENCE_POWERED_TO_DEFAULT = 0x0000
        DAC_REFERENCE_ALWAYS_POWERED_UP = 0x1000
        DAC_DATA_INPUT_REGISTER = 0x011000
        DAC_MASK_LD1 = 0x200000
        DAC_MASK_LD0 = 0x100000
        DAC_MASK_DACSEL1 = 0x040000
        DAC_MASK_DACSEL0 = 0x020000
        DAC_MASK_PD0 = 0x010000
        DAC_MASK_PD1 = 0x008000
        DAC_MASK_PD2 = 0x004000
        DAC_MASK_DATA = 0x00FFF0
        DAC_MASK_0 = 0x0
        DAC_MASK_1 = 0x400000
        DAC_MASK_2 = 0x800000

        DAC_SINGLE_CHANNEL_STORE = 0
        DAC_SINGLE_CHANNEL_UPDATE = DAC_MASK_LD1
        DAC_SIMULTANEOUS_UPDATE = DAC_MASK_LD1
        DAC_BROADCAST_UPDATE = DAC_MASK_LD1 | DAC_MASK_LD0

        DAC_CHANNEL_A = 1
        DAC_CHANNEL_B = 2
        DAC_CHANNEL_C = 3
        DAC_CHANNEL_D = 4
        DAC_CHANNEL_ALL = 5
        DAC_MAX_SCALE = 4096

        GPIO.setmode(GPIO.BOARD)

        if self.enable_pin != -1:
            self.MCP.setDirection(self.enable_pin,MCP23S08.DIR_OUTPUT)
            self.MCP.digitalWrite(self.enable_pin,MCP23S08.LEVEL_LOW)
        

        # LDAC to low
        if self.ldac_pin != -1:
            self.MCP.setDirection(self.ldac_pin,MCP23S08.DIR_OUTPUT)
            self.MCP.digitalWrite(self.ldac_pin,MCP23S08.LEVEL_LOW)
        
        # set sync pin
        self.MCP.setDirection(self.sync_pin,MCP23S08.DIR_OUTPUT)
        self.MCP.digitalWrite(self.sync_pin,MCP23S08.LEVEL_LOW)
        
        # set sclk pin
        self.MCP.setDirection(self.sclk_pin,MCP23S08.DIR_OUTPUT)
        self.MCP.digitalWrite(self.sclk_pin,MCP23S08.LEVEL_LOW)

        # set mcp pin
        self.setDirection(self.sdi_pin,MCP23S08.DIR_OUTPUT)
        self.MCP.digitalWrite(self.sdi_pin,MCP23S08.LEVEL_LOW)



    def DAC8164_write(self, data):

        if self.enable_pin != -1:
            self.MCP.digitalWrite(self.enable_pin,GPIO.LOW)

        self.MCP.digitalWrite(self.sclk_pin,GPIO.LOW)
        self.MCP.digitalWrite(self.sync_pin,GPIO.LOW)
        time.usleep(dac8164.DAC8164DELAY)

        
        i = 23
        while i >= 0:
            if (0x1<<i) & data:
                thisbit = 1
            else:
                thisbit = 0
            i-=1

            self.MCP.digitalWrite(self.sdi_pin,thisbit)
            time.usleep(dac8164.DAC8164DELAY)
            self.MCP.digitalWrite(self.sclk_pin,1)
            time.usleep(dac8164.DAC8164DELAY)
            self.MCP.digitalWrite(self.sclk_pin,0)
            time.usleep(dac8164.DAC8164DELAY)
        
        self.MCP.digitalWrite(self.sync_pin,0)

        if self.enable_pin != -1:
            self.MCP.digitalWrite(self.enable_pin,1)



    def DAC8164_setReference(self, reference):

        data = copy.copy(dac8164.DAC_MASK_PD0)

        data |= reference

        self.DAC8164_write(data)

    
    def DAC8164_writeChannel(self, channel, value):

        mod_channel = channel % 4

        if (channel - mod_channel) == 8:
            dac_mask = dac8164.DAC_MASK_2
        elif (channel - mod_channel) == 4:
            dac_mask = dac8164.DAC_MASK_1
        else:
            dac_mask = dac8164.DAC_MASK_0

        mod_channel = mod_channel + 1

        if mod_channel == dac8164.DAC_CHANNEL_A:
            data = dac8164.DAC_MASK_LD0 | dac_mask
        elif mod_channel == dac8164.DAC_CHANNEL_B:
            data = dac8164.DAC_MASK_LD0 | dac8164.DAC_MASK_DACSEL0 | dac_mask
        elif mod_channel == dac8164.DAC_CHANNEL_C:
            data = dac8164.DAC_MASK_LD0 | dac8164.DAC_MASK_DACSEL1 | dac_mask
        elif mod_channel == dac8164.DAC_CHANNEL_D:
            data = dac8164.DAC_MASK_LD0 | dac8164.DAC_MASK_DACSEL1 | dac8164.DAC_MASK_DACSEL0 | dac_mask
        elif mod_channel == dac8164.DAC_CHANNEL_ALL:
            data = dac8164.DAC_BROADCAST_UPDATE | dac8164.DAC_MASK_DACSEL1
        else:
            return False
        
        data |= value << 2
        self.DAC8164_write(data)