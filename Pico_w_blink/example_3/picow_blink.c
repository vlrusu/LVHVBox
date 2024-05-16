#include "pico/stdlib.h"
#include "tusb.h"
#include "bsp/board.h"

// CDC task to handle incoming and outgoing data
void cdc_task(void) {
  if (tud_cdc_connected() && tud_cdc_available()) {
    char buf[64];
    uint32_t count = tud_cdc_read(buf, sizeof(buf));
    tud_cdc_write(buf, count);
    tud_cdc_write_flush();
  }
}

int main() {
  stdio_init_all();
  board_init();
  tusb_init();

  printf("Pico USB CDC initialized\n"); // Print a message on startup

  while (true) {
    tud_task(); // TinyUSB device task
    cdc_task(); // Custom CDC task
  }

  return 0;
}
