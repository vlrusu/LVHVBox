#include <libusb-1.0/libusb.h>
#include <stdio.h>

#define VENDOR_ID 0x2E8A
#define PRODUCT_ID 0x000A
#define BULK_IN_ENDPOINT 0x81
#define BULK_OUT_ENDPOINT 0x01
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

  if (libusb_claim_interface(handle, 0) < 0) {
    fprintf(stderr, "Failed to claim interface\n");
    libusb_close(handle);
    libusb_exit(ctx);
    return 1;
  }

  if (libusb_bulk_transfer(handle, BULK_OUT_ENDPOINT, &data_out,
                           sizeof(data_out), &transferred, TIMEOUT) < 0) {
    fprintf(stderr, "Failed to send data\n");
  }

  if (libusb_bulk_transfer(handle, BULK_IN_ENDPOINT, &data_in, sizeof(data_in),
                           &transferred, TIMEOUT) < 0) {
    fprintf(stderr, "Failed to receive data\n");
  } else {
    printf("Received: %d\n", data_in);
  }

  libusb_release_interface(handle, 0);
  libusb_close(handle);
  libusb_exit(ctx);

  return 0;
}
