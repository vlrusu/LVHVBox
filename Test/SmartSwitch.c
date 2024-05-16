#include "pico/stdlib.h"
#include "bsp/board.h"
#include "pico/stdlib.h"
//#include "tusb.h"
#include "hardware/gpio.h"

#define BUF_SIZE 64
#define LED_PIN 25 

uint8_t buffer[BUF_SIZE];

void cdc_task(void) {
  //if( !tud_cdc_connected() || !tud_cdc_available() ) return;

  if (!tud_cdc_connected()) {
      printf("CDC not connected\n");
      return;
  }
  if (!tud_cdc_available()) {
      printf("No data available\n");
      return;
  }

  gpio_put(LED_PIN, 1);
  sleep_ms(1000);
  gpio_put(LED_PIN, 0);
  sleep_ms(1000);

  //uint32_t count = tud_cdc_read(buffer, sizeof(buffer));
  //if (count > 0) {
  //    printf("Received %d bytes\n", count);
  //    buffer[0] = !buffer[0];  // Flip the first byte
  //    tud_cdc_write(buffer, count);
  //    printf("Sent %d bytes\n", count);
  //}

  //uint32_t count = tud_cdc_read(buffer, sizeof(buffer));
  //if (count > 0) {
  //  buffer[0] = !buffer[0]; // flip
  //  tud_cdc_write(buffer, count);
  //}
}

int main(void) {
#define PICO_XOSC_STARTUP_DELAY_MULTIPLIER 64
  stdio_init_all();
  board_init();
  //tusb_init();
  tud_init(BOARD_TUD_RHPORT);  // tinyUSB formality
  gpio_init(LED_PIN);
  gpio_set_dir(LED_PIN, GPIO_OUT);

  while (1) {
    gpio_put(LED_PIN, 1);
    sleep_ms(1000);
    gpio_put(LED_PIN, 0);
    sleep_ms(1000);
    //tud_task();
    //cdc_task();
  }

  return 0;
}

