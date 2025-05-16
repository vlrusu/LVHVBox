/*============================================================================
 * File:     SmartSwitch.c
 * Author:   Vadim Rusu
 * Created:  2025-05-15
 *============================================================================*/

#include "daq.h"
#include "usb_comm.h"
#include "init.h"

#include <stdio.h>
#include <inttypes.h>
#include <stdlib.h>

#include "bsp/board.h"
#include <bsp/board_api.h>
#include "channel.pio.h"
#include "csel.pio.h"
#include "clock.pio.h"
#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/sync.h"
#include "pico/platform.h"
#include "pico/stdlib.h"
#include "pico/types.h"
#include "string.h"
#include "tusb.h"
#include "pico/bootrom.h"




int main() {
  stdio_init_all();
  board_init();
  if (board_init_after_tusb) board_init_after_tusb();

  adc_init();
  adc_gpio_init(28);
  adc_select_input(2);

  variable_init();
  port_init();


  set_sys_clock_khz(280000, true);  // Overclocking is necessary to keep up with reading PIO
  
  //  float clkdiv = 45;
  //72 PIO clock cycles for full pass
  // 280E6/39/72 = 99715 Hz 
    float clkdiv = 39;



  // start channel 0 state machine
  uint sm_channel_0 = pio_claim_unused_sm(pio0, true);
  uint offset_channel_0 = pio_add_program(pio0, &clock_program);
  clock_program_init(pio0, sm_channel_0, offset_channel_0,
		     all_pins.sclk_0,all_pins.idata0, clkdiv);


  // start channel 1 state machine
  uint sm_channel_1 = pio_claim_unused_sm(pio0, true);
  uint offset_channel_1 = pio_add_program(pio0, &csel_program);
  csel_program_init(pio0, sm_channel_1, offset_channel_1,
		    all_pins.csPin_0,all_pins.vdata0, clkdiv);

  // start channel 2 state machine
  uint sm_channel_2 = pio_claim_unused_sm(pio0, true);
  uint offset_channel_2 = pio_add_program(pio0, &channel_program);
  channel_program_init(pio0, sm_channel_2, offset_channel_2,
                       all_pins.idata1, clkdiv);
  

  // start channel 3 state machine
  uint sm_channel_3 = pio_claim_unused_sm(pio0, true);
  uint offset_channel_3 = pio_add_program(pio0, &channel_program);
  channel_program_init(pio0, sm_channel_3, offset_channel_3,
                       all_pins.vdata1, clkdiv);
  



  //////////////////////////////////

  // start channel 0 state machine
  uint sm_channel_4 = pio_claim_unused_sm(pio1, true);
  uint offset_channel_4 = pio_add_program(pio1, &clock_program);
  clock_program_init(pio1, sm_channel_4, offset_channel_4,
		     all_pins.sclk_1,all_pins.idata2, clkdiv);


  // start channel 1 state machine
  uint sm_channel_5 = pio_claim_unused_sm(pio1, true);
  uint offset_channel_5 = pio_add_program(pio1, &csel_program);
  csel_program_init(pio1, sm_channel_5, offset_channel_5,
		    all_pins.csPin_1,all_pins.vdata2, clkdiv);

  // start channel 2 state machine
  uint sm_channel_6 = pio_claim_unused_sm(pio1, true);
  uint offset_channel_6 = pio_add_program(pio1, &channel_program);
  channel_program_init(pio1, sm_channel_6, offset_channel_6,
                       all_pins.idata3, clkdiv);
  

  // start channel 3 state machine
  uint sm_channel_7 = pio_claim_unused_sm(pio1, true);
  uint offset_channel_7 = pio_add_program(pio1, &channel_program);
  channel_program_init(pio1, sm_channel_7, offset_channel_7,
                       all_pins.vdata3, clkdiv);
  
  
  //////////////////////////////////////




  // start channel 0 state machine
  uint sm_channel_8 = pio_claim_unused_sm(pio2, true);
  uint offset_channel_8 = pio_add_program(pio2, &clock_program);
  clock_program_init(pio2, sm_channel_8, offset_channel_8,
		     all_pins.sclk_2,all_pins.idata4, clkdiv);


  // start channel 1 state machine
  uint sm_channel_9 = pio_claim_unused_sm(pio2, true);
  uint offset_channel_9 = pio_add_program(pio2, &csel_program);
  csel_program_init(pio2, sm_channel_9, offset_channel_9,
		    all_pins.csPin_2,all_pins.vdata4, clkdiv);

  // start channel 2 state machine
  uint sm_channel_10 = pio_claim_unused_sm(pio2, true);
  uint offset_channel_10 = pio_add_program(pio2, &channel_program);
  channel_program_init(pio2, sm_channel_10, offset_channel_10,
                       all_pins.idata5, clkdiv);
  

  // start channel 3 state machine
  uint sm_channel_11 = pio_claim_unused_sm(pio2, true);
  uint offset_channel_11 = pio_add_program(pio2, &channel_program);
  channel_program_init(pio2, sm_channel_11, offset_channel_11,
                       all_pins.vdata5, clkdiv);
  
  

  

  // create array of state machines
  // this is used to acquire data from DAQ state machines in other areas of this
  // code
  uint sm_array[SM_COUNT];
  sm_array[0] = sm_channel_0;
  sm_array[1] = sm_channel_1;
  sm_array[2] = sm_channel_2;
  sm_array[3] = sm_channel_3;
  sm_array[4] = sm_channel_4;
  sm_array[5] = sm_channel_5;
  sm_array[6] = sm_channel_6;
  sm_array[7] = sm_channel_7;
  sm_array[8] = sm_channel_8;
  sm_array[9] = sm_channel_9;
  sm_array[10] = sm_channel_10;
  sm_array[11] = sm_channel_11;


    
  pio_enable_sm_mask_in_sync(pio0, 0b1111);
  pio_enable_sm_mask_in_sync(pio1, 0b1111);
  pio_enable_sm_mask_in_sync(pio2, 0b1111);

  for (uint8_t i = 0; i < mChn; i++) gpio_put(all_pins.crowbarPins[i], 1);
  gpio_put(all_pins.PedPin, 1);
  sleep_ms(2000);

  tud_init(BOARD_TUD_RHPORT);

  for (uint32_t i = 0; i < 4; i++) {
    pio_sm_clear_fifos(pio0, sm_array[i]);
    pio_sm_clear_fifos(pio1, sm_array[i + 4]);
    pio_sm_clear_fifos(pio2, sm_array[i + 8]);
  }
    
  while (true) {
    
    for (uint32_t i = 0; i < 1000; i++) {
      get_all_averaged_currents(pio0, pio1, pio2, sm_array);
      store_average_currents();
      tud_task();
      cdc_task(sm_array);
    }

  }
  return 0;
}
