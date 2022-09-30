NCHANNELS = 6

def test(channel):
    
    ret = []
    
    if channel[0] == None:
        for i in range(NCHANNELS):
            ret.append(i)

    else:
        ret.append(channel[0])

    return ret

def readvoltage(channel):
    
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
