import usb.core
import usb.util

dev = usb.core.find(idVendor=0x2e8a, idProduct=0x000a)
if dev is None:
    raise ValueError('Device is not found')
# device is found :-)
interface = 0
endpoint = dev[0][(0,0)][0]

print(endpoint.bEndpointAddress)
print(endpoint.wMaxPacketSize)


if dev.is_kernel_driver_active(interface) is True:
    # tell the kernel to detach
    dev.detach_kernel_driver(interface)
   
    # claim the device
    usb.util.claim_interface(dev, interface)

'''
data = dev.read(endpoint.bEndpointAddress,endpoint.wMaxPacketSize)
'''


#dev.write(0x81,"hi")
dev.read(0x81,8)

'''
try:
    print("Read:", dev.read(0x81,8))
except:
    pass
'''