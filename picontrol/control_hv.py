from dac8164 import dac8164
from MCP23S08 import MCP23S08
import time


def initialization():
    dac = [None,None,None]

    # initialize MCP
    mcp1 = MCP23S08(bus=0x00, pin_cs=0x00, device_id=0x02)
    mcp1.open()
    mcp1._spi.max_speed_hz = 10000000

    dac[0] = dac8164(mcp1, 6, 7, 0, -1, -1)
    dac[1] = dac8164(mcp1, 3, 7, 0, -1, -1)
    dac[2] = dac8164(mcp1, 5, 7, 0, -1, -1)

    return dac



def set_hv(channel, value, dac):
    idac = int(channel/4)

    alphas = [0.9055, 0.9073, 0.9051, 0.9012, 0.9012, 0.9034,
              0.9009, 0.9027, 0.8977, 0.9012, 0.9015, 1]

    alpha = alphas[channel]

    digvalue = int(alpha*16383*value/2.5) & 0x3FFF

    dac[idac].DAC8164_writeChannel(channel, digvalue)

def ramp_hv(channel, value, nsteps, dac):
    idac = int(channel/4)

    alphas = [0.9055, 0.9073, 0.9051, 0.9012, 0.9012, 0.9034,
              0.9009, 0.9027, 0.8977, 0.9012, 0.9015, 1]
    
    current_value = value/nsteps

    alpha = alphas[channel]

    for i in range(nsteps):

        digvalue = int(alpha*16383*value/2.5) & 0x3FFF
        dac[idac].DAC8164_writeChannel(channel, digvalue)

        time.sleep(50000/(10E6))

        current_value += value/nsteps
    
    

if __name__=="__main__":
    value = 0
    nsteps = 200
    dac = initialization()

    value = value*2.3/1510

    ramp_hv(0,value,nsteps,dac)
    