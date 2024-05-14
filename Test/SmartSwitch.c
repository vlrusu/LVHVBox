#include "bsp/board.h"
#include "pico/stdlib.h"
#include "tusb.h"

#define BUF_SIZE 64

uint8_t buffer[BUF_SIZE];

void cdc_task(void) {
  if( !tud_cdc_connected() || !tud_cdc_available() ) return;

  uint32_t count = tud_cdc_read(buffer, sizeof(buffer));
  if (count > 0) {
    buffer[0] = !buffer[0]; // flip
    tud_cdc_write(buffer, count);
  }
}

int main(void) {
#define PICO_XOSC_STARTUP_DELAY_MULTIPLIER 64
  stdio_init_all();
  board_init();
  //tusb_init();
  tud_init(BOARD_TUD_RHPORT);  // tinyUSB formality

  while (1) {
    tud_task();
    cdc_task();
  }

  return 0;
}
