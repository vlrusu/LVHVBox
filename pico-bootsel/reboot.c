// Ed Callaghan
// Force RP2040 running SmartSwitch application into BOOTSEL mode
// November 2024

#include <getopt.h>
#include <libusb-1.0/libusb.h>
#include <stdio.h>
#include "pico/stdio_usb/reset_interface.h"
#include "Pico.h"

void exit_on_error(int rc, char *msg);
void attempt_to_reboot(libusb_device *device);

int main(int argc, char** argv){
  // same (direct) addressing scheme as picotool, so as
  // not to assume that we are starting from a working state
  uint8_t bus = 0;
  uint8_t address = 0;

  // prep longopts
  struct option options[] = {
    {"bus",     1, NULL, 'b'},
    {"address", 1, NULL, 'a'},
    {0,         0,    0,   0}
  };
  int option_index;

  int c;
  while ((c = getopt_long(argc, argv, "b:a:", options, &option_index)) != -1){
    switch (c) {
      case 'b':
        bus = (uint8_t) atoi(optarg);
        break;
      case 'a':
        address = (uint8_t) atoi(optarg);
        break;
      default:
        char msg[128];
        sprintf(msg, "unexpected option code %c", c);
        exit_on_error(1, msg);
        break;
    }
  }

  // ensure that we are actively, intionally, addressing
  if ((bus == 0) || (address == 0)){
        char msg[128];
        sprintf(msg, "must supply nonzero bus and address. got %d and %d", bus, address);
        exit_on_error(1, msg);
  }

  // search for chosen device
  libusb_device *device = NULL;
  libusb_device **devices;
  libusb_init(NULL);
  size_t ndevices = libusb_get_device_list(NULL, &devices);
  for (size_t i = 0 ; i < ndevices ; i++){
    libusb_device *tmp = devices[i];
    if (libusb_get_bus_number(tmp) == bus){
      if (libusb_get_device_address(tmp) == address){
        device = tmp;
      }
    }
  }

  // dump device info
  struct libusb_device_descriptor descriptor;
  if (libusb_get_device_descriptor(device, &descriptor) != 0){
    exit_on_error(1, "LIBUSB_ERROR when getting device descriptor");
  }
  printf("found device:\n");
  printf("\tbus:        %03d\n", bus);
  printf("\taddress:    %03d\n", address);
  printf("\tproduct id: 0x%04x\n", descriptor.idProduct);
  printf("\tvendor id:  0x%04x\n", descriptor.idVendor);

  // attempt to reboot
  attempt_to_reboot(device);

  return 0;
}

void exit_on_error(int rc, char* msg){
  // TODO stderr
  printf("%s\n", msg);
  exit(1);
}

// mostly carved out of picotool
void attempt_to_reboot(libusb_device *device){
  struct libusb_config_descriptor *config;
  if (libusb_get_active_config_descriptor(device, &config) != 0){
    exit_on_error(1, "LIBUSB_ERROR when getting config descriptor");
  }
  libusb_device_handle *handle;
  if (libusb_open(device, &handle) != 0){
    exit_on_error(1, "failed to open usb device (get handle)");
  }

  // shamefully hard-coded
  int interface = 1;
  if (libusb_set_auto_detach_kernel_driver(handle, interface) != 0){
    exit_on_error(1, "failed to set kernel driver autodetach");
  }
  if (libusb_claim_interface(handle, interface) != 0){
    exit_on_error(1, "failed to claim matching usb interface");
  }

  printf("initiating reboot...\n");
  char writeable = 255;
  libusb_bulk_transfer(handle, 0x02, &writeable, 1, 0, 0);

}
