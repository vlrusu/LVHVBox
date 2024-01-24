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
#define nAdc  6		// Number of SmartSwitches
#define mChn  6		// Number of channels for trip processing

#define pico 0

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

PIO pio_0 = pio0; // pio block 0 reference
PIO pio_1 = pio1; // pio block 1 reference

uint8_t trip_mask = -1; // tracks which channels have trips enabled/disabled
// all channels start out with trips enabled

uint8_t trip_status = 0; // no channels start out tripped

uint16_t num_trigger[6] = {0, 0, 0, 0, 0, 0}; // increments/decrements based upon whether trip_currents are exceeded
float trip_currents[6] = {172, 172, 172, 172, 172, 172}; // tripping threshold currents

const float adc_to_V  = 2.048 / pow(2, 15) * 1000;			// ADC full-scale voltage / ADC full scale reading * divider ratio
const float adc_to_uA = (2.048 / pow(2, 15)) / (24.7 * 475) * 1.E6;

uint32_t average_current_history_length = 2000;
#define full_current_history_length 8000
uint8_t current_buffer_run = 1;
uint16_t full_position = 0;

uint32_t full_current_array[6][full_current_history_length];

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
  for (int channel=0; channel<6; channel++) {
    for (int index=0; index<full_current_history_length; index++) {
      full_current_array[channel][index] = 0;
    }
  }

  // pinouts/ins same for both picos
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

void cdc_task(float channel_current_averaged[6], float channel_voltage[6], uint sm[6], uint16_t *burst_position, float trip_currents[6], uint8_t* trip_mask, uint8_t* trip_status, float average_current_history[6][average_current_history_length], uint16_t* average_store_position, uint32_t full_current_history[6][full_current_history_length], uint16_t* full_position, uint8_t* current_buffer_run)
{
  if ( tud_cdc_available() )
    {
      // read in commands from Server on Pi
      uint8_t receive_chars[5];
      tud_cdc_read(&receive_chars, sizeof(receive_chars)); // acquire 5 chars from tinyUSB input buffer
      tud_cdc_read_flush(); // clear tinyUSB input buffer

      // determine response based upon Server command
      if (102 < receive_chars[0] && receive_chars[0] < 109) { // ----- Trip ----- //
        uint8_t tripPin = all_pins.crowbarPins[receive_chars[0] - 103];
        if (*trip_mask & (1 << (receive_chars[0]-103))) {
          gpio_put(tripPin, 1);
          *trip_status = *trip_status | (1 << (receive_chars[0]-103));
        }

      } else if (108 < receive_chars[0] && receive_chars[0] < 115) { // ----- Reset Trip ----- //
        uint8_t tripPin = all_pins.crowbarPins[receive_chars[0] - 109]; // acquire proper crowbar pin
        gpio_put(tripPin, 0); // set relevant crowbar pin low
        *trip_status = *trip_status & ~(1 << receive_chars[0] - 109); // store information that channel is no longer tripped
      
      } else if (114 < receive_chars[0] && receive_chars[0] < 121) { // ----- Disable Trip ----- //
        *trip_mask = *trip_mask & ~(1 << (receive_chars[0]-115)); // store that channel is no longer capable of tripping

      } else if (120 < receive_chars[0] && receive_chars[0] < 127) { // ----- Enable Trip ----- //
        *trip_mask = *trip_mask | (1 << (receive_chars[0]-121)); // store that channel is now capable of tripping

      } else if (receive_chars[0] == 33) { // ----- Send Trip Statuses ----- //
        tud_cdc_write(&*trip_status,sizeof(&*trip_status));
        tud_cdc_write_flush(); // flushes write buffer, data will not actually be sent without this command

      } else if (75 < receive_chars[0] && receive_chars[0] < 82) { // ----- Set new trip value ----- //
        
        // join receive_chars into a single 16 bit unsigned integer
        uint16_t one = receive_chars[1] << 8;
        uint16_t two = receive_chars[2] + one;

        trip_currents[receive_chars[0] - 76] = (float)two/ 65535 * 1000; // 1000 is the max value, probably change later
        
      } else if (receive_chars[0] == 37) { // ----- Put Pedestal High ----- //
        gpio_put(all_pins.P1_0,1);
      
      } else if (receive_chars[0] == 38) { // ----- Put Pedestal Low ----- //
        gpio_put(all_pins.P1_0,0);
      
      } else if (receive_chars[0] == 86) { // ----- Send Voltages ----- //
        for (uint8_t i=0; i<6; i++) {
          tud_cdc_write(&channel_voltage[i],sizeof(&channel_voltage[i]));
        }
        tud_cdc_write_flush(); // flushes write buffer, data will not actually be sent without this command

      } else if (receive_chars[0] == 73) { // ----- Send Averaged Currents ----- //
        for (uint8_t i=0; i<6; i++) {
          tud_cdc_write(&channel_current_averaged[i],sizeof(&channel_current_averaged[i]));
        }
        tud_cdc_write_flush(); // flushes write buffer, data will not actually be sent without this command

      } else if (receive_chars[0] == 87) { // ----- start current buffer ----- //
        *current_buffer_run = 1;

      } else if (receive_chars[0] == 88) { // ----- stop current buffer ----- //
        *current_buffer_run = 0;

      } else if (receive_chars[0] > 88 && receive_chars[0] < 95) { // ----- Send chunk of current buffer ----- //
        uint16_t temp_currents[10];

        uint16_t crc_val[10];
        
        uint32_t crc_div = 11;
        int channel = receive_chars[0] - 89;

        *current_buffer_run = 0;
        float check_val;
       
       for (int i=0; i<10; i++) {
        temp_currents[i] = (uint16_t) full_current_history[channel][*full_position + i];
       }

        tud_cdc_write(temp_currents,20);
        tud_cdc_write(crc_val, sizeof(crc_val));
        tud_cdc_write_flush();


      } else if (receive_chars[0] == 95) { // Send current buffer status ----- //
          tud_cdc_write(&*current_buffer_run,sizeof(&*current_buffer_run));
          tud_cdc_write_flush(); // flushes write buffer, data will not actually be sent without this command
      } else if (receive_chars[0] == 96) { // move full position forward 10 //
        *full_position += 10;
        if (*full_position >= full_current_history_length) {
          *full_position -= full_current_history_length;
        }
      } else if (receive_chars[0] == 72) { // Send chunk of average currents ----- //
        // check if data needs to be sent
        if (*average_store_position > 1)
        {

          for (uint8_t time_index=0; time_index<2; time_index++) {
            for (uint8_t channel_index=0; channel_index<6; channel_index++) {

              // write to usb buffer
              tud_cdc_write(&average_current_history[channel_index][time_index],sizeof(&average_current_history[channel_index][time_index]));
            }
          }
          tud_cdc_write_flush(); // tinyUSB formality

          // update average current_list
          for (uint16_t i=0; i<(*average_store_position-2); i++) {
            for (uint16_t channel=0; channel<6; channel++) {
              average_current_history[channel][i] = average_current_history[channel][i+2];
            }
          }
          // update store position
          *average_store_position -= 2;
        } else {
          float none_var = -100;
          tud_cdc_write(&none_var,sizeof(&none_var));
          tud_cdc_write_flush(); // tinyUSB formality
        }

      }
    }
}

float get_single_voltage(PIO pio, uint sm) // obtains a single non-averaged voltage measurement
{
  uint32_t temp = pio_sm_get_blocking(pio, sm);
  float voltage = ((int16_t) temp) * adc_to_V;
  return voltage;
}

void get_all_averaged_currents(PIO pio_0, PIO pio_1, uint sm[], float current_array[6], uint32_t full_current_array[6][full_current_history_length], uint16_t* full_position, uint8_t* current_buffer_run) {
 for (uint32_t channel = 0; channel < 6; channel++) // initializes each element of current array to zero
 {
  current_array[channel] = 0;
 }

 float latest_current_0;
 float latest_current_1;

 for (uint32_t i = 0; i < 200; i++) // adds current measurements to current_array
 {
  for (uint32_t channel = 0; channel < 3; channel++)
  {
    // NOTE: with an average of 200, overflow does not occur
    // However, if this average is increased later on, it may be necessary to divide earlier/increase to 32 bit integers
    latest_current_0 = (int16_t) pio_sm_get_blocking(pio_0, sm[channel]);
    latest_current_1 = (int16_t) pio_sm_get_blocking(pio_1, sm[channel+3]);
    
    current_array[channel] += latest_current_0;
    current_array[channel+3] += latest_current_1;

    
    
    if (*current_buffer_run == 1) {
      // update latest full current, along with its position in rotating buffer
      full_current_array[channel][*full_position] = (uint32_t) latest_current_0;
      full_current_array[channel+3][*full_position] = (uint32_t) latest_current_1;
      
    }
    
  }

  
  if (*current_buffer_run == 1) {
    *full_position += 1;
    if (*full_position >= full_current_history_length) {
      *full_position -= full_current_history_length;
    }
  }

 }

  
 for (uint32_t channel=0; channel<6; channel++) // divide & multiply summed current values by appropriate factors
 {
  current_array[channel] = current_array[channel]*adc_to_uA/200;
 }


  for (uint32_t i=0; i<6; i++) {
        // check if trip is required

        if ((current_array[i] > trip_currents[i]) && ((trip_mask & (1 << i)))) {



          if (num_trigger[i] > 20) {
            *current_buffer_run = 0;
            gpio_put(all_pins.crowbarPins[i],1);
            trip_status = trip_status | (1 << i);
            num_trigger[i] = 0;
          } else {
            num_trigger[i] += 1;
          }
        } else if (num_trigger[i] > 0) {
          num_trigger[i] -= 1;
        }
        
      }
  
}

//******************************************************************************
// Standard loop function, called repeatedly
int main(){
  #define PICO_XOSC_STARTUP_DELAY_MULTIPLIER 64

  
  stdio_init_all();

  set_sys_clock_khz(210000, true); // Overclocking just to be sure that pico keeps up with everything
  // not aware of any real drawbacks, SmartSwitch can probably keep up even without overclocking
  // So if it becomes an issue, overclocking is probably unecessary

  board_init(); // tinyUSB formality
  
  float clkdiv = 13; // set clock divider for PIO
  uint32_t pio_start_mask = -1; // mask to select which state machines in each PIO block are started

  adc_init();
  adc_gpio_init(28);
  adc_select_input(2);

  variable_init();
  port_init();

  float channel_current_averaged[6] = {0, 0, 0, 0, 0, 0};
  float channel_voltage[6] = {0, 0, 0, 0, 0, 0};
  uint16_t burst_position = 0;


  float average_current_history[6][average_current_history_length];
  uint16_t average_position = 0;
  uint16_t average_store_position = 0;


  // Start clock state machine for PIO block 0
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
  
  
  // Start clock state machien for PIO block 1
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
// this is used to acquire data from DAQ state machines in other areas of this code
uint sm_array[6];
sm_array[0] = sm_channel_0;
sm_array[1] = sm_channel_1;
sm_array[2] = sm_channel_2;
sm_array[3] = sm_channel_3;
sm_array[4] = sm_channel_4;
sm_array[5] = sm_channel_5;

// start all state machines in pio block in sync
pio_enable_sm_mask_in_sync(pio_0, pio_start_mask);
pio_enable_sm_mask_in_sync(pio_1, pio_start_mask);




for (uint8_t i=0; i<6; i++) // ensure that all crowbar pins are initially off
{
  gpio_put(all_pins.crowbarPins[i],0);
}

gpio_put(all_pins.P1_0, 1); // put pedestal pin high

  tud_init(BOARD_TUD_RHPORT); // tinyUSB formality

  while (true) // DAQ & USB communication Loop, runs forever
  {
    // ----- Collect averaged current measurements ----- //

    gpio_put(all_pins.enablePin, 0); // set mux to current
    sleep_ms(1); // delay is longer than ideal, but seems to be necessary, or current data will be polluted

    // clear rx fifos
    for (uint32_t i=0; i<3; i++) {
      pio_sm_clear_fifos(pio_0, sm_array[i]);
      pio_sm_clear_fifos(pio_1, sm_array[i+3]);
    }

    // acquire averaged current values
    for (uint32_t i=0; i<10; i++) {
      get_all_averaged_currents(pio_0, pio_1, sm_array, channel_current_averaged, full_current_array, &full_position, &current_buffer_run); // get average of 200 full speed current measurements

      // store averaged currents
      if (average_store_position < 1999) // check that current buffer size has not been exceeded
      {
        for (uint8_t i=0; i<6; i++) {
          average_current_history[i][average_store_position] = channel_current_averaged[i];
        }
        average_store_position += 1; // increment pointer to current storage position
      } else { // begin overwriting current data, starting
        average_store_position = 0; // set pointer to beginning of current storage buffer
        for (uint8_t i=0; i<6; i++) {
          memset(average_current_history[i],0,sizeof(average_current_history[i]));
        }
      }
      
  
      // cdc_task reads in commands from PI via usb and responds appropriately
      cdc_task(channel_current_averaged, channel_voltage, sm_array, &burst_position, trip_currents, &trip_mask, &trip_status, average_current_history, &average_store_position, full_current_array, &full_position, &current_buffer_run);
      tud_task(); // tinyUSB formality
    }

    // ----- Collect single voltage measurements ----- //

    gpio_put(all_pins.enablePin, 1); // set mux to voltage
    sleep_ms(1); // delay is longer than ideal, but seems to be necessary, or voltage data will be polluted


    cdc_task(channel_current_averaged, channel_voltage, sm_array, &burst_position, trip_currents, &trip_mask, &trip_status, average_current_history, &average_store_position, full_current_array, &full_position, &current_buffer_run);
    tud_task();

    // clear rx fifos, otherwise data can be polluted by previous current measurements
    for (uint32_t i=0; i<3; i++) {
      pio_sm_clear_fifos(pio_0, sm_array[i]);
      pio_sm_clear_fifos(pio_1, sm_array[i+3]);
    }

    for (uint32_t channel = 0; channel < 3; channel++) // read in a single voltage value for each of 6 channels
    {
      channel_voltage[channel] = get_single_voltage(pio_0, sm_array[channel]);

      channel_voltage[channel+3] = get_single_voltage(pio_1, sm_array[channel+3]);
    }

  }
  return 0;
}