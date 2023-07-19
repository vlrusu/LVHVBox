#include <stdio.h>
#include <math.h>
#include "string.h"
#include "pico/stdlib.h"
#include "pico/types.h"
#include "pico/platform.h"
#include "hardware/gpio.h"
#include <stdlib.h>
#include "pico/stdlib.h"
#include "hardware/sync.h"
#include "hardware/adc.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"

#include "clock.pio.h"
#include "channel.pio.h"

#include <pico/platform.h>
#include <inttypes.h>

#include "bsp/board.h"
#include "tusb.h"







// Channel count
#define mAdc  12		// Maximum number of ADCs to read
#define nAdc  6		// Number of SmartSwitches
#define mChn  6		// Number of channels for trip processing

#define pico 1

struct Pins {
  uint8_t crowbarPins[mChn];
  uint8_t headerPins[nAdc];
  uint8_t P1_0;
  uint8_t sclk_0;
  uint8_t sclk_1;
  uint8_t csPin_0;
  uint8_t csPin_1;
  uint8_t enablePin;
} all_pins;




PIO pio_0 = pio0;
PIO pio_1 = pio1;



// Converstion from ADC to microamps
const float adc_to_V  = 2.048 / pow(2, 15) * 1000;			// ADC full-scale voltage / ADC full scale reading * divider ratio
//const float adc_to_uA = 2.048 / pow(2, 15) / 8200.0 * 1.E6;	// ADC full-scale voltage / ADC full scale reading / shunt resistance * uA per amp

const float adc_to_uA_1 = (2.048 / pow(2, 15)) / 8200 * 1.E6;
const float adc_to_uA_2 = (2.048 / pow(2, 15)) / (22.56* 470.0) * 1.E6;	// dev
const float adc_to_uA_3 = (2.048 / pow(2, 15)) / 9676 * 1.E6;

const uint8_t switch_type[6] = {3, 1, 1, 1, 1, 1};

void port_init() {

  uint8_t port;
  // Reset all trips
  for (uint8_t i = 0; i < sizeof(all_pins.crowbarPins); i++) {
    gpio_init(all_pins.crowbarPins[i]);
    gpio_set_dir(all_pins.crowbarPins[i], GPIO_OUT);
  }
  // Pedestal/data line
  gpio_init(all_pins.P1_0);
  gpio_set_dir(all_pins.P1_0, GPIO_OUT);

  // enable pin
  gpio_init(all_pins.enablePin);
  gpio_set_dir(all_pins.enablePin, GPIO_OUT);

}

// Variables
void variable_init() {

  if (pico == 1) {
    //all_pins.crowbarPins = (uint8_t []){ 2, 5, 8, 11, 14, 21 };			// crowbar pins
      //  { 21, 26, 22, 16, 4, 5 };     //Channels in data are upside down, FIXME!!!
    uint8_t crowbarPins[6] = { 2, 5, 8, 11, 14, 21};
    uint8_t headerPins[6] = { 1, 3, 6, 10, 12, 9};

    for (int i = 0; i < 6; i++) {
      all_pins.crowbarPins[i] = crowbarPins[i];
      all_pins.headerPins[i] = headerPins[i];
    }

    all_pins.P1_0 = 20;					// Offset
    all_pins.sclk_0 = 18;						// SPI clock
    all_pins.csPin_0 = 16;					// SPI Chip select for I
    all_pins.sclk_1 = 26;						// SPI clock
    all_pins.csPin_1 = 15;					// SPI Chip select for I
    all_pins.enablePin = 7;     // enable pin for MUX
  }
  else {
    uint8_t crowbarPins[6] = { 2, 5, 8, 11, 14, 21};
    uint8_t headerPins[6] = { 1, 3, 6, 10, 12, 9};
    
    all_pins.P1_0 = 20;					// Offset
    all_pins.sclk_0 = 18;						// SPI clock
    all_pins.csPin_0 = 16;					// SPI Chip select for I
    all_pins.sclk_1 = 26;						// SPI clock
    all_pins.csPin_1 = 15;					// SPI Chip select for I
    all_pins.enablePin = 7;     // enable pin for MUX
  }
}

void get_current_burst(PIO pio, uint sm, int16_t current_array[60000]) {
  for (uint32_t i=0; i<60000; i++) {
    current_array[i] = (int16_t) pio_sm_get_blocking(pio, sm);
  }
}

void cdc_task(float channel_current_averaged[6], float channel_voltage[6], int16_t burst_current[60000], uint sm[6], uint16_t *burst_position, float trip_currents[6], uint8_t* trip_mask, uint8_t* trip_status, float average_current[6][2000], uint16_t* average_store_position)
{
  if ( tud_cdc_available() )
    {
      uint8_t receive_chars[3];
      for (uint8_t i=0; i<3; i++) {
        tud_cdc_read(&receive_chars[i], sizeof(receive_chars[i]));
      }
      tud_cdc_read_flush();

      // respond properly to request
      if (102 < receive_chars[0] && receive_chars[0] < 109) { // ----- Trip ----- //
        uint8_t tripPin = all_pins.crowbarPins[receive_chars[0] - 103];
        if (*trip_mask & (1 << (receive_chars[0]-103))) {
          gpio_put(tripPin, 1);
          *trip_status = *trip_status | (1 << (receive_chars[0]-103));
        }

      } else if (108 < receive_chars[0] && receive_chars[0] < 115) { // ----- Reset Trip ----- //
        uint8_t tripPin = all_pins.crowbarPins[receive_chars[0] - 109];
        gpio_put(tripPin, 0);
        *trip_status = *trip_status & ~(1 << (receive_chars[0]-109));

      
      } else if (114 < receive_chars[0] && receive_chars[0] < 121) { // ----- Disable Trip ----- //
        uint8_t tripPin = all_pins.crowbarPins[receive_chars[0] - 115];
        *trip_mask = *trip_mask & ~(1 << (receive_chars[0]-115));
        //trip_pins[receive_chars[0] - 115] = 0;
      } else if (120 < receive_chars[0] && receive_chars[0] < 127) { // ----- Enable Trip ----- //
        uint8_t tripPin = all_pins.crowbarPins[receive_chars[0] - 121];
        *trip_mask = *trip_mask | (1 << (receive_chars[0]-121));
        //trip_pins[receive_chars[0] - 121] = 1;
      
      } else if (receive_chars[0] == 33) { // ----- Send Trip Statuses ----- //
        tud_cdc_write(&*trip_status,sizeof(&*trip_status));
        tud_cdc_write_flush();

      } else if (75 < receive_chars[0] && receive_chars[0] < 82) { // ----- Set new trip value ----- //
        uint16_t trip_bits = ((uint16_t)receive_chars[2]) + ((uint16_t)receive_chars[1]) << 8;

        // max trip value is 1000 nA
        // set trip_current to proper value
        trip_currents[receive_chars[0] - 76] = trip_bits / 65535 * 1000;

      } else if (receive_chars[0] == 86) { // ----- Send Voltages ----- //
        for (uint8_t i=0; i<6; i++) {
          tud_cdc_write(&channel_voltage[i],sizeof(&channel_voltage[i]));
        }
        tud_cdc_write_flush();
      } else if (receive_chars[0] == 73) { // ----- Send Averaged Currents ----- //
        for (uint8_t i=0; i<6; i++) {
          tud_cdc_write(&channel_current_averaged[i],sizeof(&channel_current_averaged[i]));
        }
        tud_cdc_write_flush();
      } else if (receive_chars[0] > 96 && receive_chars[0] < 103) { // ----- Get Current Burst ----- //

        // Acquire current data
        if (receive_chars[0] < 100) {
          get_current_burst(pio_0, sm[receive_chars[0] - 97], burst_current);
        } else {
          get_current_burst(pio_1, sm[receive_chars[0] - 97], burst_current);
        }
        burst_position = 0;
      } else if (receive_chars[0] == 115) { // ----- Send chunk of current burst ----- //
        float temp_current;

        for (uint8_t i=0; i<15; i++) {
          temp_current = burst_current[*burst_position + i] * adc_to_uA_2;
          tud_cdc_write(&temp_current,sizeof(&temp_current));
        }
        tud_cdc_write_flush();
        if (*burst_position < 60000) {
          *burst_position += 15;
        }
      } else if (receive_chars[0] == 72) { // Send chunk of average currents ----- //
        // check if data needs to be sent
        if (*average_store_position > 1) {

       

          for (uint8_t time_index=0; time_index<2; time_index++) {
            for (uint8_t channel_index=0; channel_index<6; channel_index++) {

              // write to usb buffer
              tud_cdc_write(&average_current[channel_index][time_index],sizeof(&average_current[channel_index][time_index]));
            }
          }
          tud_cdc_write_flush();

          // update average current_list
          for (uint16_t i=0; i<(*average_store_position-2); i++) {
            for (uint16_t channel=0; channel<6; channel++) {
              average_current[channel][i] = average_current[channel][i+2];
            }
          }
          // update store position
          *average_store_position -= 2;
        } else {
          uint8_t none_var = -1;
          tud_cdc_write(&none_var,sizeof(&none_var));
          tud_cdc_write_flush();
        }

      }
    }
}

/*

  float average_current[6][2000];
  uint16_t average_position = 0;
  uint16_t average_store_position = 0;

*/


float get_single_voltage(PIO pio, uint sm) {
  uint32_t temp = pio_sm_get_blocking(pio, sm);
  float voltage = ((int16_t) temp) * adc_to_V;
  return voltage;
}

void get_all_averaged_currents(PIO pio_0, PIO pio_1, uint sm[], float current_array[6]) {
 for (uint32_t channel = 0; channel < 6; channel++){
  current_array[channel] = 0;
 }

 for (uint32_t i = 0; i < 200; i++) {
  for (uint32_t channel = 0; channel < 3; channel++){
    current_array[channel] += (int16_t) pio_sm_get_blocking(pio_0, sm[channel]);
    current_array[channel+3] += (int16_t) pio_sm_get_blocking(pio_1, sm[channel+3]);
  }
 }

 for (uint32_t channel = 0; channel < 6; channel++) {
    if (switch_type[channel] == 1) {
      current_array[channel] = current_array[channel]*adc_to_uA_1/200 + 8.3;
    } else if (switch_type[channel] == 2) {
      current_array[channel] = current_array[channel]*adc_to_uA_2/200;
    } else {
      current_array[channel] = current_array[channel]*adc_to_uA_3/200;
    }

  }
}

//******************************************************************************
// Standard loop function, called repeatedly
int main(){
  float trip_currents[6] = {900, 900, 900, 900, 900, 900};
  
  stdio_init_all();
  set_sys_clock_khz(210000, true);

  board_init();
  //board_led_write(true);
  
  float clkdiv = 11;
  uint32_t start_mask = -1;

  adc_init();
  adc_gpio_init(28);
  adc_select_input(2);



  variable_init();
  port_init();



  float channel_current_averaged[6] = {0, 0, 0, 0, 0, 0};
  float channel_voltage[6] = {0, 0, 0, 0, 0, 0};
  int16_t burst_current[60000];
  uint16_t burst_position = 0;

  float average_current[6][2000];
  uint16_t average_position = 0;
  uint16_t average_store_position = 0;


 






  // Start clock state machine
  uint sm_clock = pio_claim_unused_sm(pio_0, true);
  uint offset_clock = pio_add_program(pio_0, &clock_program);
  clock_0_program_init(pio_0,sm_clock,offset_clock,all_pins.csPin_0,all_pins.sclk_0,clkdiv);


  // start channel 0 state machine
  uint sm_channel_0 = pio_claim_unused_sm(pio_0, true);
  uint offset_channel_0 = pio_add_program(pio_0, &channel_program);
  channel_program_init(pio_0,sm_channel_0,offset_channel_0,all_pins.headerPins[0],clkdiv);

  // start channel 1 state machine
  uint sm_channel_1 = pio_claim_unused_sm(pio_0, true);
  uint offset_channel_1 = pio_add_program(pio_0, &channel_program);
  channel_program_init(pio_0,sm_channel_1,offset_channel_1,all_pins.headerPins[1],clkdiv);

  
  // start channel 2 state machine
  uint sm_channel_2 = pio_claim_unused_sm(pio_0, true);
  uint offset_channel_2 = pio_add_program(pio_0, &channel_program);
  channel_program_init(pio_0,sm_channel_2,offset_channel_2,all_pins.headerPins[2],clkdiv);
  
  
  // Start clock 1 state machine
  uint sm_clock_1 = pio_claim_unused_sm(pio_1, true);
  uint offset_clock_1 = pio_add_program(pio_1, &clock_program);
  clock_1_program_init(pio_1,sm_clock_1,offset_clock_1,all_pins.csPin_1,all_pins.sclk_1,clkdiv);


  // start channel 3 state machine
  uint sm_channel_3 = pio_claim_unused_sm(pio_1, true);
  uint offset_channel_3 = pio_add_program(pio_1, &channel_program);
  channel_program_init(pio_1,sm_channel_3,offset_channel_3,all_pins.headerPins[3],clkdiv);

  // start channel 4 state machine
  uint sm_channel_4 = pio_claim_unused_sm(pio_1, true);
  uint offset_channel_4 = pio_add_program(pio_1, &channel_program);
  channel_program_init(pio_1,sm_channel_4,offset_channel_4,all_pins.headerPins[4],clkdiv);

  
  // start channel 5 state machine
  uint sm_channel_5 = pio_claim_unused_sm(pio_1, true);
  uint offset_channel_5 = pio_add_program(pio_1, &channel_program);
  channel_program_init(pio_1,sm_channel_5,offset_channel_5,all_pins.headerPins[5],clkdiv);
  





// create array of state machines
uint sm_array[6];
sm_array[0] = sm_channel_0;
sm_array[1] = sm_channel_1;
sm_array[2] = sm_channel_2;
sm_array[3] = sm_channel_3;
sm_array[4] = sm_channel_4;
sm_array[5] = sm_channel_5;

// start all state machines in pio block
pio_enable_sm_mask_in_sync(pio_0, start_mask);
pio_enable_sm_mask_in_sync(pio_1, start_mask);

//uint8_t trip_pins[6] = {1,1,1,1,1,1};
//uint8_t trip_pins[6] = {0,0,0,0,0,0};
uint8_t trip_mask = -1;
uint8_t trip_status = 0;

uint32_t enable_mask = 1 << 7;



for (uint8_t i=0; i<6; i++) {
  gpio_put(all_pins.crowbarPins[i],0);
}

gpio_put(all_pins.P1_0, 1);

  tud_init(BOARD_TUD_RHPORT);
  while (true) {
    //absolute_time_t start = get_absolute_time();

    // ----- Collect averaged current measurements ----- //

    // set mux to current

    gpio_put(all_pins.enablePin, 0);
    //gpio_clr_mask(enable_mask);
    sleep_ms(1);

    // clear rx fifos
    for (uint32_t i=0; i<3; i++) {
      pio_sm_clear_fifos(pio_0, sm_array[i]);
      pio_sm_clear_fifos(pio_1, sm_array[i+3]);
    }


    // acquire averaged current values
    for (uint32_t i=0; i<10; i++) {
      get_all_averaged_currents(pio_0, pio_1, sm_array, channel_current_averaged);

      
      for (uint32_t i=0; i<6; i++) {
        // check if trip is required
        if ((channel_current_averaged[i] > trip_currents[i]) && ((trip_mask & (1 << i)))) {
          gpio_put(all_pins.crowbarPins[i],1);
          trip_status = trip_status | (1 << i);
        }
      }

      // store averaged currents
      if (average_store_position < 1999) {
        for (uint8_t i=0; i<6; i++) {
          average_current[i][average_store_position] = channel_current_averaged[i];
          
        }
        average_store_position += 1;
      }
      
  
      
      
      cdc_task(channel_current_averaged, channel_voltage, burst_current, sm_array, &burst_position, trip_currents, &trip_mask, &trip_status, average_current, &average_store_position);
      tud_task();
    }


  
    // ----- Collect single voltage measurements ----- //

    // set mux to voltage

    gpio_put(all_pins.enablePin, 1);
    //gpio_set_mask(enable_mask);
    sleep_ms(1);


    cdc_task(channel_current_averaged, channel_voltage, burst_current, sm_array, &burst_position, trip_currents, &trip_mask, &trip_status, average_current, &average_store_position);
    tud_task();

    // clear rx fifos
    for (uint32_t i=0; i<3; i++) {
      pio_sm_clear_fifos(pio_0, sm_array[i]);
      pio_sm_clear_fifos(pio_1, sm_array[i+3]);
    }

    for (uint32_t channel = 0; channel < 3; channel++) {
      channel_voltage[channel] = get_single_voltage(pio_0, sm_array[channel]);

      channel_voltage[channel+3] = get_single_voltage(pio_1, sm_array[channel+3]);
    }

  }
  return 0;
}