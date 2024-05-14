#include "tusb.h"

#define BULK_IN_ENDPOINT 0x81
#define BULK_OUT_ENDPOINT 0x01
#define BUF_SIZE 64

uint8_t buffer[BUF_SIZE];

void tud_mount_cb(void) {
  // Invoked when the device is mounted
}

void tud_umount_cb(void) {
  // Invoked when the device is unmounted
}

void tud_suspend_cb(bool remote_wakeup_en) {
  // Invoked when usb bus is suspended
}

void tud_resume_cb(void) {
  // Invoked when usb bus is resumed
}

void tud_task(void) {
  if (tud_cdc_connected() && tud_cdc_available()) {
    uint32_t count = tud_cdc_read(buffer, BUF_SIZE);

    // Flip the first byte and send it back
    if (count > 0) {
      buffer[0] = !buffer[0];
      tud_cdc_write(buffer, count);
      tud_cdc_write_flush();
    }
  }
}

int main(void) {
  board_init();
  tusb_init();

  while (1) {
    tud_task();
  }

  return 0;
}
