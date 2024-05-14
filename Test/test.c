#include <libusb-1.0/libusb.h>
#include <stdio.h>

#define VENDOR_ID 0xcaf0
#define PRODUCT_ID 0x4003
#define CDC_INTERFACE 0
#define CDC_ENDPOINT_IN 0x82
#define CDC_ENDPOINT_OUT 0x02
#define TIMEOUT 1000

int main() {
  libusb_context *ctx = NULL;
  libusb_device_handle *handle = NULL;
  uint8_t data_out = 1;
  uint8_t data_in;
  int transferred;

  if (libusb_init(&ctx) < 0) {
    fprintf(stderr, "libusb init failed\n");
    return 1;
  }

  handle = libusb_open_device_with_vid_pid(ctx, VENDOR_ID, PRODUCT_ID);
  if (!handle) {
    fprintf(stderr, "Failed to open device\n");
    libusb_exit(ctx);
    return 1;
  }

  // Enable auto kernel driver detachment
  libusb_set_auto_detach_kernel_driver(handle, 1);

  if (libusb_claim_interface(handle, CDC_INTERFACE) < 0) {
    fprintf(stderr, "Failed to claim interface\n");
    libusb_close(handle);
    libusb_exit(ctx);
    return 1;
  }

  // Send data
  if (libusb_bulk_transfer(handle, CDC_ENDPOINT_OUT, &data_out,
                           sizeof(data_out), &transferred, TIMEOUT) < 0) {
    fprintf(stderr, "Failed to send data\n");
  }

  // Receive data
  if (libusb_bulk_transfer(handle, CDC_ENDPOINT_IN, &data_in, sizeof(data_in),
                           &transferred, TIMEOUT) < 0) {
    fprintf(stderr, "Failed to receive data\n");
  } else {
    printf("Received: %d\n", data_in);
  }

  libusb_release_interface(handle, CDC_INTERFACE);
  libusb_close(handle);
  libusb_exit(ctx);

  return 0;
}
