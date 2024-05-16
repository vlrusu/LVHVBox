// Blink pico led AND repeatedly print hello world.
// 
// Blink the led on a pico "w" (aka wifi-enabled) is different than on a
// non-wifi pico. Pin access is different.
#include "pico/cyw43_arch.h"
#include "pico/stdlib.h"

int main() {
  stdio_init_all();
  if (cyw43_arch_init()) {
    printf("Wi-Fi init failed"); // Don't think wifi is actually used tho.
    return -1;
  }
  while (true) {
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
    sleep_ms(250);
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
    sleep_ms(250);
    printf("Hello World\n");
  }
}
