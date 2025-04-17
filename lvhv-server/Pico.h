// Ed Callaghan
// Factoring out pico identity as a standalone struct
// October 2024

#ifndef PICO_H
#define PICO_H

// magic numbers to differentiate lower/upper channels
#define PICO_VENDOR_ID_0 0xcaf0
#define PICO_VENDOR_ID_1 0xcaf1
#define PICO_PRODUCT_ID 0x4003

#include <stdlib.h>
#include <libusb-1.0/libusb.h>

typedef struct libusb_device_handle* usb_handle_t;

typedef struct {
  size_t id;
  usb_handle_t handle;
  size_t channel_offset;
} Pico_t;

void pico_init(Pico_t*, uint16_t, size_t, size_t);
// void pico_destroy(Pico_t*);

#endif
