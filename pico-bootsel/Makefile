# Ed Callaghan
# Force RP2040 running SmartSwitch application into BOOTSEL mode
# November 2024

CFLAGS		:= $(CFLAGS)  -I../lv-server
CFLAGS		:= $(CFLAGS)  -I$(PICO_SDK_PATH)/src/rp2_common/pico_stdio_usb/include
CFLAGS		:= $(CFLAGS)  -I$(PICO_SDK_PATH)/src/common/pico_usb_reset_interface/include
CFLAGS		:= $(CFLAGS)  $(shell pkg-config libusb-1.0 --cflags)
LDFLAGS		:= $(LDFLAGS) $(shell pkg-config libusb-1.0 --libs)

reboot: reboot.c
	$(CC) -o $@ $(CFLAGS) $< $(LDFLAGS)

clean:
	-rm -f reboot

.PHONY: clean
