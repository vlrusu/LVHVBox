// Ed Callaghan
// Factoring out pico identity as a standalone struct
// October 2024

#include "Pico.h"

void pico_init(Pico_t* pico, uint16_t vid, size_t id, size_t offset){
  // below call is bad practice, should replace with dedicated selection
  pico->handle = libusb_open_device_with_vid_pid(NULL, vid, PICO_PRODUCT_ID);
  if (pico->handle != NULL){
    libusb_set_auto_detach_kernel_driver(pico->handle, 1);
    libusb_claim_interface(pico->handle, 1);
  }

  // assign id and channel offset, either 0 or 6
  pico->id = id;
  pico->channel_offset = offset;
}
