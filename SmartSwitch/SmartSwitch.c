#include <inttypes.h>
#include <math.h>
#include <pico.h>
#include <stdio.h>
#include <stdlib.h>

#include "bsp/board.h"
#include "channel.pio.h"
#include "csel.pio.h"
#include "clock.pio.h"
#include "hardware/adc.h"
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


// Channel count
#define nAdc 6  // Number of SmartSwitches
#define mChn 6  // Number of channels for trip processing

#define pico 1  // which pico (1 or 2)

struct Pins {
  uint8_t crowbarPins[mChn];
  uint8_t PedPin;
  uint8_t sclk_0;
  uint8_t sclk_1;
  uint8_t sclk_2;
  uint8_t csPin_0;
  uint8_t csPin_1;
  uint8_t csPin_2;  
  uint8_t idata0;
  uint8_t vdata0;
  uint8_t idata1;
  uint8_t vdata1;
  uint8_t idata2;
  uint8_t vdata2;
  uint8_t idata3;
  uint8_t vdata3;
  uint8_t idata4;
  uint8_t vdata4;
  uint8_t idata5;
  uint8_t vdata5;
  
} all_pins;

PIO pio_0 = pio0;  // pio block 0 reference
PIO pio_1 = pio1;  // pio block 1 reference
PIO pio_2 = pio2;  // pio block 1 reference

uint8_t trip_mask = -1;  // tracks which channels have trips enabled/disabled
// all channels start out with trips enabled

// tracks if any state machines are reading data faster than they're being read
uint8_t slow_read = 0;

uint8_t trip_status = -1;  // all channels start out tripped

uint16_t num_trigger[6] = {0, 0, 0, 0,
                           0, 0};  // increments/decrements based upon whether
                                   // trip_currents are exceeded
float trip_currents[6] = {20, 20, 20,
                          20, 20, 20};  // tripping threshold currents

const float adc_to_V =
  2.5 / pow(2, 15) *
  1000;  // ADC full-scale voltage / ADC full scale reading * divider ratio
const float adc_to_uA = (2.5 / pow(2, 15)) / (100 * 101) * 1.E6;

uint32_t average_current_history_length = 2000;
#define full_current_history_length 8000
uint8_t current_buffer_run = 1;
uint16_t full_position = 0;
int before_trip_allowed = 0;

int trip_requirement[6] = {100, 100, 100, 100, 100, 100};
int remaining_buffer_iterations = 4000;

uint32_t full_current_array[12][full_current_history_length];

float ped_subtraction[6] = {0, 0, 0, 0, 0, 0};
float ped_subtraction_stored[6] = {0, 0, 0, 0, 0, 0};
int ped_on = 1;

void port_init() {
  uint8_t port;
  // Reset all trips
  for (uint8_t i = 0; i < sizeof(all_pins.crowbarPins); i++) {
    gpio_init(all_pins.crowbarPins[i]);
    gpio_set_dir(all_pins.crowbarPins[i], GPIO_OUT);
  }
  // Pedestal/data line
  gpio_init(all_pins.PedPin);
  gpio_set_dir(all_pins.PedPin, GPIO_OUT);



}

// Variables
void variable_init() {
  for (int channel = 0; channel < 6; channel++) {
    for (int index = 0; index < full_current_history_length; index++) {
      full_current_array[channel][index] = 0;
    }
  }

  // pinouts for old muxers/hv board
  // pinouts/ins same for both picos
  /*
    uint8_t crowbarPins[6] = { 2, 5, 8, 11, 14, 21};
    uint8_t headerPins[6] = { 1, 3, 6, 10, 12, 9};
    for (int i = 0; i < 6; i++) {
    all_pins.crowbarPins[i] = crowbarPins[i];
    all_pins.headerPins[i] = headerPins[i];
    }

    all_pins.P1_0 = 20;      // Offset
    all_pins.sclk_0 = 18;    // SPI clock
    all_pins.csPin_0 = 16;   // SPI Chip select for I
    all_pins.sclk_1 = 26;    // SPI clock
    all_pins.csPin_1 = 15;   // SPI Chip select for I
    all_pins.enablePin = 7;  // enable pin for MUX
  */

  // pico1 pinout
  if (pico == 1) {
    uint8_t crowbarPins[6] = {7, 0, 8, 15, 18};

    for (int i = 0; i < 6; i++) {
      all_pins.crowbarPins[i] = crowbarPins[i];
    }

    all_pins.PedPin = 20;  // Offset
    all_pins.sclk_0 = 5;      // SPI clock for PIO0
    all_pins.csPin_0 = 2;    // SPI Chip select for PIO0
    all_pins.idata0 = 9;       //I data 0
    all_pins.vdata0 = 10;       //V data 0
    all_pins.idata1 = 1;       //I data 2
    all_pins.vdata1 = 4;       //V data 2
    all_pins.sclk_1 = 11;     // SPI clock
    all_pins.csPin_1 = 13;     // SPI Chip select for PIO1
    all_pins.idata2 = 6;       //I data 3
    all_pins.vdata2 = 3;       //V data 3
    all_pins.idata3 = 14;       //I data 4
    all_pins.vdata3 = 12;       //V data 4
    all_pins.sclk_2 = 19;     // SPI clock
    all_pins.csPin_2 = 26;     // SPI Chip select for PIO2
    all_pins.idata4 = 17;       //I data 5
    all_pins.vdata4 = 16;       //V data 5
    all_pins.idata5 = 27;       //I data 6
    all_pins.vdata5 = 21;       //V data 6


    
  } else {
    // pico2 pinout
    int8_t crowbarPins[6] = {7,2,9,16,22,17};

    for (int i = 0; i < 6; i++) {
      all_pins.crowbarPins[i] = crowbarPins[i];
    }


    all_pins.PedPin = 15;  // Offset
    all_pins.sclk_0 = 4;      // SPI clock for PIO0
    all_pins.csPin_0 = 0;    // SPI Chip select for PIO0
    all_pins.idata0 = 8;       //I data 0
    all_pins.vdata0 = 10;       //V data 0
    all_pins.idata1 = 1;       //I data 1
    all_pins.vdata1 = 3;       //V data 1
    all_pins.sclk_1 = 20;     // SPI clock
    all_pins.csPin_1 = 13;     // SPI Chip select for I
    all_pins.idata2 = 6;       //I data 0
    all_pins.vdata2 = 5;       //V data 0
    all_pins.idata3 = 14;       //I data 1
    all_pins.vdata3 = 12;       //V data 1
    all_pins.sclk_2 = 11;     // SPI clock
    all_pins.csPin_2 = 19;     // SPI Chip select for I
    all_pins.idata4 = 26;       //I data 0
    all_pins.vdata4 = 27;       //V data 0
    all_pins.idata5 = 18;       //I data 1
    all_pins.vdata5 = 21;       //V data 1

  }
}

void cdc_task(float channel_current_averaged[12],
              uint sm[12], uint16_t* burst_position, float trip_currents[6],
              uint8_t* trip_mask, uint8_t* trip_status,
              float average_current_history[12][average_current_history_length],
              uint16_t* average_store_position,
              uint32_t full_current_history[12][full_current_history_length],
              uint16_t* full_position, uint8_t* current_buffer_run,
              uint8_t* slow_read, int* before_trip_allowed, uint sm_array[6],
              int trip_requirement[6]) {
  if (tud_cdc_available()) {
    // read in commands from Server on Pi
    uint8_t receive_chars[5];
    tud_cdc_read(
		 &receive_chars,
		 sizeof(receive_chars));  // acquire 5 chars from tinyUSB input buffer
    tud_cdc_read_flush();        // clear tinyUSB input buffer

    // determine response based upon Server command
    if (102 < receive_chars[0] &&
        receive_chars[0] < 109) {  // ----- Trip ----- //
      uint8_t tripPin = all_pins.crowbarPins[receive_chars[0] - 103];

      if (*trip_mask &
          (1 << (receive_chars[0] -
                 103))) {  // store ped subtract values from time of trip
        *current_buffer_run = 0;
        *before_trip_allowed = 20;

        memcpy(ped_subtraction_stored, ped_subtraction,
               sizeof(ped_subtraction));
        gpio_put(tripPin, 1);
        *trip_status = *trip_status | (1 << (receive_chars[0] - 103));

        // store ped subtract values from time of trip
        memcpy(ped_subtraction_stored, ped_subtraction,
               sizeof(ped_subtraction));
      }

    } else if (108 < receive_chars[0] &&
               receive_chars[0] < 115) {  // ----- Reset Trip ----- //
      *current_buffer_run = 1;
      remaining_buffer_iterations = floor(full_current_history_length / 2);

      uint8_t tripPin =
	all_pins.crowbarPins[receive_chars[0] -
			     109];  // acquire proper crowbar pin

      if (*trip_mask & (1 << (receive_chars[0] - 109))) {
        *trip_mask = *trip_mask & ~(1 << (receive_chars[0] - 109));
        gpio_put(tripPin, 0);  // set relevant crowbar pin low
        *trip_status =
	  *trip_status &
	  ~(1 << receive_chars[0] - 109);  // store information that channel
	// is no longer tripped
        sleep_ms(250);
        *trip_mask = *trip_mask | (1 << (receive_chars[0] - 109));
      } else {
        gpio_put(tripPin, 0);  // set relevant crowbar pin low
        *trip_status =
	  *trip_status &
	  ~(1 << receive_chars[0] - 109);  // store information that channel
	// is no longer tripped
      }

    } else if (114 < receive_chars[0] &&
               receive_chars[0] < 121) {  // ----- Disable Trip ----- //
      *trip_mask =
	*trip_mask &
	~(1 << (receive_chars[0] -
		115));  // store that channel is no longer capable of tripping

    } else if (120 < receive_chars[0] &&
               receive_chars[0] < 127) {  // ----- Enable Trip ----- //
      *trip_mask =
	*trip_mask |
	(1 << (receive_chars[0] -
	       121));  // store that channel is now capable of tripping

    } else if (receive_chars[0] == 33) {  // ----- Send Trip Statuses ----- //
      tud_cdc_write(&*trip_status, sizeof(&*trip_status));
      tud_cdc_write_flush();  // flushes write buffer, data will not actually be
                              // sent without this command

    } else if (receive_chars[0] ==
               99) {  // ----- Send trip enabled statuses ----- //
      tud_cdc_write(&*trip_mask, sizeof(&*trip_mask));
      tud_cdc_write_flush();
    } else if (75 < receive_chars[0] &&
               receive_chars[0] < 82) {  // ----- Set new trip value ----- //

      // join receive_chars into a single 16 bit unsigned integer
      uint16_t one = receive_chars[1] << 8;
      uint16_t two = receive_chars[2] + one;

      trip_currents[receive_chars[0] - 76] =
	(float)two / 65535 *
	1000;  // 1000 is the max value, probably change later

    } else if (receive_chars[0] == 37) {  // ----- Put Pedestal High ----- //
      gpio_put(all_pins.PedPin, 1);
      ped_on = 1;

    } else if (receive_chars[0] == 38) {  // ----- Put Pedestal Low ----- //
      gpio_put(all_pins.PedPin, 0);
      ped_on = 0;

    } else if (receive_chars[0] == 86) {  // ----- Send Voltages ----- //
      for (uint8_t i = 0; i < 6; i++) {
        tud_cdc_write(&channel_current_averaged[2*i+1], sizeof(&channel_current_averaged[2*i+1]));
      }
      tud_cdc_write_flush();  // flushes write buffer, data will not actually be
                              // sent without this command

    } else if (receive_chars[0] ==
               73) {  // ----- Send Averaged Currents ----- //

      for (uint8_t i = 0; i < 6; i++) {
        tud_cdc_write(&channel_current_averaged[2*i],
                      sizeof(&channel_current_averaged[2*i]));
      }
      tud_cdc_write_flush();  // flushes write buffer, data will not actually be
                              // sent without this command

    } else if (receive_chars[0] == 87) {  // ----- start current buffer ----- //
      *current_buffer_run = 1;
      remaining_buffer_iterations = floor(full_current_history_length / 2);

    } else if (receive_chars[0] == 88) {  // ----- stop current buffer ----- //
      *current_buffer_run = 0;



      
    } else if (receive_chars[0] > 88 &&
               receive_chars[0] <
	       95) {  // ----- Send chunk of current buffer ----- //
      float temp_currents[10];
      int channel = receive_chars[0] - 89;

      *current_buffer_run = 0;

      int send_index;

      for (int i = 0; i < 10; i++) {
        if (*full_position + i < full_current_history_length) {
          send_index = *full_position + i;
        } else {
          send_index = i - (full_current_history_length - *full_position);
        }

	if (channel%2 ==0 ){ //current
	  if (ped_on == 1) {
	    temp_currents[i] =
	      full_current_history[channel][send_index] * adc_to_uA -
	      ped_subtraction_stored[channel];
	  } else {
	    temp_currents[i] =
	      full_current_history[channel][send_index] * adc_to_uA;
	  }
	}
	else{
	    temp_currents[i] =
	      full_current_history[channel][send_index] * adc_to_V;
	}	  
	
      }

      tud_cdc_write(temp_currents, sizeof(temp_currents));
      tud_cdc_write_flush();

      *full_position += 10;
      if (*full_position >= full_current_history_length) {
        *full_position -= full_current_history_length;
      }

    } else if (receive_chars[0] == 97) {  // send value of slow_read to server
      tud_cdc_write(&*slow_read, sizeof(&*slow_read));
      tud_cdc_write_flush();
    } else if (receive_chars[0] == 95) {  // Send current buffer status ----- //
      tud_cdc_write(&*current_buffer_run, sizeof(&*current_buffer_run));
      tud_cdc_write_flush();  // flushes write buffer, data will not actually be
                              // sent without this command
    } else if (receive_chars[0] == 96) {  // move full position forward 10 //
      *full_position += 10;
      if (*full_position >= full_current_history_length) {
        *full_position -= full_current_history_length;
      }
    } else if (receive_chars[0] ==
               72) {  // Send chunk of average currents ----- //
      // check if data needs to be sent
      // the maximum USB buffer size is 64bytes. averaege_current_buffer is float, so 4 bytes. I can max send one at a time for all
      // or do 2 for currentonly. Doing this for now
      if (*average_store_position > 1) {
        for (uint8_t time_index = 0; time_index < 2; time_index++) {
          for (uint8_t channel_index = 0; channel_index < 6; channel_index++) {
            // write to usb buffer
            tud_cdc_write(
			  &average_current_history[2*channel_index][time_index],
			  sizeof(&average_current_history[2*channel_index][time_index]));
          }
        }
        tud_cdc_write_flush();  // tinyUSB formality

        // update average current_list
        for (uint16_t i = 0; i < (*average_store_position - 2); i++) {
          for (uint16_t channel = 0; channel < 6; channel++) {
            average_current_history[2*channel][i] =
	      average_current_history[2*channel][i + 2];
          }
        }
        // update store position
        *average_store_position -= 2;
      } else {
        float none_var = -100;
        tud_cdc_write(&none_var, sizeof(&none_var));
        tud_cdc_write_flush();  // tinyUSB formality
      }

    } else if (receive_chars[0] == 98) {  // Send value hv adc value //
      float return_val = 0;

      for (int i = 0; i < 50; i++) {
        return_val += (float)adc_read();
      }
      return_val /= 50;

      tud_cdc_write(&return_val, sizeof(return_val));
      tud_cdc_write_flush();

    } else if (receive_chars[0] > 38 && receive_chars[0] < 45) {
      if (ped_on == 1) {
        gpio_put(all_pins.PedPin, 0);  // put pedestal pin low
        sleep_ms(1400);

        // clear rx fifos
        for (uint32_t i = 0; i < 3; i++) {
          pio_sm_clear_fifos(pio_0, sm_array[i]);
          pio_sm_clear_fifos(pio_1, sm_array[i + 3]);
        }

        int32_t pre_ped_subtraction[6] = {0, 0, 0, 0, 0, 0};

        for (int ped_count = 0; ped_count < 200; ped_count++) {
          for (int i = 0; i < 2; i++) {
            pre_ped_subtraction[i] +=
	      (int16_t)pio_sm_get_blocking(pio_0, sm_array[2*i]);
            pre_ped_subtraction[i + 2] +=
	      (int16_t)pio_sm_get_blocking(pio_1, sm_array[2*i + 4]);
            pre_ped_subtraction[i + 4] +=
	      (int16_t)pio_sm_get_blocking(pio_2, sm_array[2*i + 8]);
          }
        }

        for (int i = 0; i < 6; i++) {
          ped_subtraction[i] = (float)pre_ped_subtraction[i] / 200 * adc_to_uA;
        }

        gpio_put(all_pins.PedPin, 1);  // put pedestal pin high

        // update ped_subtraction_stored
        if (*current_buffer_run == 1) {
          memcpy(ped_subtraction_stored, ped_subtraction,
                 sizeof(ped_subtraction));
        }

        sleep_ms(700);
      }
    } else if (receive_chars[0] > 44 &&
               receive_chars[0] < 51) {  // set new trip count requirement

      // join receive_chars into a single 16 bit unsigned integer
      uint16_t one = receive_chars[2] << 8;
      uint16_t two = receive_chars[1] + one;
      int intval = (int)two;

      memcpy(&trip_requirement[receive_chars[0] - 45], &intval, 4);
    


     } else if (receive_chars[0] == 255) {
      // force reboot into BOOTSEL mode
      reset_usb_boot(0, 0);
    }
  }
}

/* float get_single_voltage( */
/* 			 PIO pio, uint sm)  // obtains a single non-averaged voltage measurement */
/* { */
/*   uint32_t temp = pio_sm_get_blocking(pio, sm); */
/*   float voltage = ((int16_t)temp) * adc_to_V; */
/*   return voltage; */
/* } */

void get_all_averaged_currents(
			       PIO pio_0, PIO pio_1, PIO pio_2, uint sm[], float current_array[12],
			       uint32_t full_current_array[12][full_current_history_length],
			       uint16_t* full_position, uint8_t* current_buffer_run,
			       int* remaining_buffer_iterations, int* before_trip_allowed) {
  if (*before_trip_allowed > 0) {
    *before_trip_allowed -= 1;
  }


  memset(current_array, 0, 12 * sizeof(float));
  

  float latest_current_0;
  float latest_current_1;
  float latest_current_2;

  for (uint32_t i = 0; i < 200;
       i++)  // adds current measurements to current_array
    {
      for (uint32_t channel = 0; channel < 4; channel++) {

	if (pio_sm_is_rx_fifo_full(pio_0, sm[channel]) ||
	    pio_sm_is_rx_fifo_full(pio_1, sm[channel + 4]) ||
	    pio_sm_is_rx_fifo_full(pio_2, sm[channel + 8]) 
	    ) {
	  if (i > 10 && *before_trip_allowed == 0) {
	    slow_read = 1;
	  }
	}

	// NOTE: with an average of 200, overflow does not occur
	// However, if this average is increased later on, it may be necessary to
	// divide earlier/increase to 32 bit integers
	latest_current_0 = (int16_t)pio_sm_get_blocking(pio_0, sm[channel]);
	latest_current_1 = (int16_t)pio_sm_get_blocking(pio_1, sm[channel + 4]);
	latest_current_2 = (int16_t)pio_sm_get_blocking(pio_2, sm[channel + 8]);	

	current_array[channel] += latest_current_0;
	current_array[channel + 4] += latest_current_1;
	current_array[channel + 8] += latest_current_2;

	
	//triping only enabled for currents
	if (channel % 2 == 0 ){
	  int current_index = channel / 2; //currents are always in the even position
	  if ((latest_current_0 * adc_to_uA >
	       trip_currents[current_index] - ped_subtraction[current_index]) &&
	      ((trip_mask & (1 << current_index))) && ((~trip_status & (1 << current_index))) &&
	      *before_trip_allowed == 0) {
	    num_trigger[current_index] += 1;
	  } else if (num_trigger[current_index] > 0) {
	    num_trigger[current_index] -= 1;
	  }

	  if ((latest_current_1 * adc_to_uA >
	       trip_currents[current_index+2] - ped_subtraction[current_index+2]) &&
	      ((trip_mask & (1 << current_index+2))) && ((~trip_status & (1 << current_index+2))) &&
	      *before_trip_allowed == 0) {
	    num_trigger[current_index+2] += 1;
	  } else if (num_trigger[current_index+2] > 0) {
	    num_trigger[current_index+2] -= 1;
	  }

	  if ((latest_current_2 * adc_to_uA >
	       trip_currents[current_index+4] - ped_subtraction[current_index+4]) &&
	      ((trip_mask & (1 << current_index+4))) && ((~trip_status & (1 << current_index+4))) &&
	      *before_trip_allowed == 0) {
	    num_trigger[current_index+4] += 1;
	  } else if (num_trigger[current_index+4] > 0) {
	    num_trigger[current_index+4] -= 1;
	  }
	  

	}

	if (*remaining_buffer_iterations > 0) {
	  // update latest full current, along with its position in rotating
	  // buffer
	  full_current_array[channel][*full_position] =
            (uint32_t)latest_current_0;
	  full_current_array[channel + 4][*full_position] =
            (uint32_t)latest_current_1;
	  full_current_array[channel + 8][*full_position] =
            (uint32_t)latest_current_2;
	}
      }

      // if tripping is necessary, trip correct channel

      // check if any trip counts have been exceeded
      int trip_required = 0;
      for (int channel = 0; channel < 6; channel++) {
	if (num_trigger[channel] >= trip_requirement[channel]) {
	  trip_required = 1;

	  // set all num_triggers to zero
	  for (int i = 0; i < 6; i++) {
	    num_trigger[i] = 0;
	  }
	}
      }
      if (trip_required == 1) {
	if (*current_buffer_run == 1) {
	  *remaining_buffer_iterations = floor(full_current_history_length / 2);
	  *current_buffer_run = 0;
	}

	float current_sums[6] = {0, 0, 0, 0, 0, 0};
	int read_index;
	for (int channel_index = 0; channel_index < 6; channel_index++) {
	  for (int current_index = 0; current_index < 25; current_index++) {
	    if (*full_position - current_index < 0) {
	      read_index = full_current_history_length - current_index;
	    } else {
	      read_index = *full_position - current_index;
	    }
	    current_sums[channel_index] +=
              full_current_array[2*channel_index][read_index] * adc_to_uA -
              trip_currents[channel_index];
	  }
	}

	int max_channel;
	float max_value = 0;
	for (int i = 0; i < 6; i++) {
	  if (current_sums[i] > max_value && ((~trip_status & (1 << i)))) {
	    max_value = current_sums[i];
	    max_channel = i;
	  }
	}

	gpio_put(all_pins.crowbarPins[max_channel], 1);
	*before_trip_allowed = 20;
	trip_status = trip_status | (1 << max_channel);
      }

      if (*remaining_buffer_iterations > 0) {
	*full_position += 1;
	if (*full_position >= full_current_history_length) {
	  *full_position = 0;
	}

	if (*current_buffer_run == 0 && *remaining_buffer_iterations > 0) {
	  *remaining_buffer_iterations -= 1;
	}
      }
    }

  for (uint32_t channel = 0; channel < 6;
       channel++)  // divide & multiply summed current values by appropriate
                   // factors
    {
      // ped_on == 1
      if (ped_on == 1) {
	current_array[2*channel] =
          current_array[2*channel] * adc_to_uA / 200 - ped_subtraction[channel];
      } else {
	current_array[2*channel] = current_array[2*channel] * adc_to_uA / 200;
      }
      current_array[2*channel+1] = current_array[2*channel+1] * adc_to_V / 200;
    }
}

//******************************************************************************
// Standard loop function, called repeatedly
int main() {
#define PICO_XOSC_STARTUP_DELAY_MULTIPLIER 64

  stdio_init_all();

  set_sys_clock_khz(280000, true);  // Overclocking is necessary to keep up with reading PIO

  board_init();  // tinyUSB formality

  // float clkdiv = 34; // set clock divider for PIO
  float clkdiv = 45;  // results in 81.967 kHz
  uint32_t pio_start_mask = 0b1111;  // mask to select which state machines in each PIO block are started

  adc_init();
  adc_gpio_init(28);
  adc_select_input(2);

  variable_init();
  port_init();

  float channel_current_averaged[12] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
  uint16_t burst_position = 0;

  float average_current_history[12][average_current_history_length];
  uint16_t average_position = 0;
  uint16_t average_store_position = 0;


  // start channel 0 state machine
  uint sm_channel_0 = pio_claim_unused_sm(pio_0, true);
  uint offset_channel_0 = pio_add_program(pio_0, &clock_program);
  clock_program_init(pio_0, sm_channel_0, offset_channel_0,
		     all_pins.sclk_0,all_pins.idata0, clkdiv);


  // start channel 1 state machine
  uint sm_channel_1 = pio_claim_unused_sm(pio_0, true);
  uint offset_channel_1 = pio_add_program(pio_0, &csel_program);
  csel_program_init(pio_0, sm_channel_1, offset_channel_1,
		    all_pins.csPin_0,all_pins.vdata0, clkdiv);

  // start channel 2 state machine
  uint sm_channel_2 = pio_claim_unused_sm(pio_0, true);
  uint offset_channel_2 = pio_add_program(pio_0, &channel_program);
  channel_program_init(pio_0, sm_channel_2, offset_channel_2,
                       all_pins.idata1, clkdiv);
  

  // start channel 3 state machine
  uint sm_channel_3 = pio_claim_unused_sm(pio_0, true);
  uint offset_channel_3 = pio_add_program(pio_0, &channel_program);
  channel_program_init(pio_0, sm_channel_3, offset_channel_3,
                       all_pins.vdata1, clkdiv);
  



  //////////////////////////////////

  // start channel 0 state machine
  uint sm_channel_4 = pio_claim_unused_sm(pio_1, true);
  uint offset_channel_4 = pio_add_program(pio_1, &clock_program);
  clock_program_init(pio_1, sm_channel_4, offset_channel_4,
		     all_pins.sclk_1,all_pins.idata2, clkdiv);


  // start channel 1 state machine
  uint sm_channel_5 = pio_claim_unused_sm(pio_1, true);
  uint offset_channel_5 = pio_add_program(pio_1, &csel_program);
  csel_program_init(pio_1, sm_channel_5, offset_channel_5,
		    all_pins.csPin_1,all_pins.vdata2, clkdiv);

  // start channel 2 state machine
  uint sm_channel_6 = pio_claim_unused_sm(pio_1, true);
  uint offset_channel_6 = pio_add_program(pio_1, &channel_program);
  channel_program_init(pio_1, sm_channel_6, offset_channel_6,
                       all_pins.idata3, clkdiv);
  

  // start channel 3 state machine
  uint sm_channel_7 = pio_claim_unused_sm(pio_1, true);
  uint offset_channel_7 = pio_add_program(pio_1, &channel_program);
  channel_program_init(pio_1, sm_channel_7, offset_channel_7,
                       all_pins.vdata3, clkdiv);
  
  
  //////////////////////////////////////




  // start channel 0 state machine
  uint sm_channel_8 = pio_claim_unused_sm(pio_2, true);
  uint offset_channel_8 = pio_add_program(pio_2, &clock_program);
  clock_program_init(pio_2, sm_channel_8, offset_channel_8,
		     all_pins.sclk_2,all_pins.idata4, clkdiv);


  // start channel 1 state machine
  uint sm_channel_9 = pio_claim_unused_sm(pio_2, true);
  uint offset_channel_9 = pio_add_program(pio_2, &csel_program);
  csel_program_init(pio_2, sm_channel_9, offset_channel_9,
		    all_pins.csPin_2,all_pins.vdata4, clkdiv);

  // start channel 2 state machine
  uint sm_channel_10 = pio_claim_unused_sm(pio_2, true);
  uint offset_channel_10 = pio_add_program(pio_2, &channel_program);
  channel_program_init(pio_2, sm_channel_10, offset_channel_10,
                       all_pins.idata5, clkdiv);
  

  // start channel 3 state machine
  uint sm_channel_11 = pio_claim_unused_sm(pio_2, true);
  uint offset_channel_11 = pio_add_program(pio_2, &channel_program);
  channel_program_init(pio_2, sm_channel_11, offset_channel_11,
                       all_pins.vdata5, clkdiv);
  
  

  

  // create array of state machines
  // this is used to acquire data from DAQ state machines in other areas of this
  // code
  uint sm_array[12];
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

  // start all state machines in pio block in sync
  pio_enable_sm_mask_in_sync(pio_0, pio_start_mask);
  pio_enable_sm_mask_in_sync(pio_1, pio_start_mask);
  pio_enable_sm_mask_in_sync(pio_2, pio_start_mask);

  for (uint8_t i = 0; i < 6; i++)  // ensure that all crowbar pins are initially off
    {
      gpio_put(all_pins.crowbarPins[i], 1);
    }

  gpio_put(all_pins.PedPin, 1);  // put pedestal pin high
  sleep_ms(2000);

  tud_init(BOARD_TUD_RHPORT);  // tinyUSB formality

  while (true)  // DAQ & USB communication Loop, runs forever
    {
      // ----- Collect averaged current measurements ----- //

      for (int j = 0; j < 35; j++) {
	sleep_ms(1);  // delay is longer than ideal, but seems to be necessary, or
	// current data will be polluted

	// clear rx fifos
	for (uint32_t i = 0; i < 4; i++) {
	  pio_sm_clear_fifos(pio_0, sm_array[i]);
	  pio_sm_clear_fifos(pio_1, sm_array[i + 4]);
	  pio_sm_clear_fifos(pio_2, sm_array[i + 8]);
	}

	// acquire averaged current values
	for (uint32_t i = 0; i < 1000; i++) {
	  get_all_averaged_currents(
				    pio_0, pio_1, pio_2, sm_array, channel_current_averaged,
				    full_current_array, &full_position, &current_buffer_run,
				    &remaining_buffer_iterations,
				    &before_trip_allowed);  // get average of 200 full speed current
	  // measurements

	  // store averaged currents
	  if (average_store_position <
	      1999)  // check that current buffer size has not been exceeded
	    {
	      for (uint8_t i = 0; i < 12; i++) {
		average_current_history[i][average_store_position] =
		  channel_current_averaged[i];
	      }
	      average_store_position +=
		1;  // increment pointer to current storage position
	    } else {  // begin overwriting current data, starting
	    average_store_position =
              0;  // set pointer to beginning of current storage buffer
	    for (uint8_t i = 0; i < 12; i++) {
	      memset(average_current_history[i], 0,
		     sizeof(average_current_history[i]));
	    }
	  }

	  // cdc_task reads in commands from PI via usb and responds appropriately
	  cdc_task(channel_current_averaged, sm_array,
		   &burst_position, trip_currents, &trip_mask, &trip_status,
		   average_current_history, &average_store_position,
		   full_current_array, &full_position, &current_buffer_run,
		   &slow_read, &before_trip_allowed, sm_array, trip_requirement);
	  tud_task();  // tinyUSB formality
	}

	// ----- Collect single voltage measurements ----- //

	/* gpio_put(all_pins.enablePin, 1);  // set mux to voltage */
	/* sleep_ms(1);  // delay is longer than ideal, but seems to be necessary, or */
	/*               // voltage data will be polluted */

	/* cdc_task(channel_current_averaged, channel_voltage, sm_array, */
	/*          &burst_position, trip_currents, &trip_mask, &trip_status, */
	/*          average_current_history, &average_store_position, */
	/*          full_current_array, &full_position, &current_buffer_run, */
	/*          &slow_read, &before_trip_allowed, sm_array, trip_requirement); */
	/* tud_task(); */

	// clear rx fifos, otherwise data can be polluted by previous current
	// measurements
	for (uint32_t i = 0; i < 4; i++) {
	  pio_sm_clear_fifos(pio_0, sm_array[i]);
	  pio_sm_clear_fifos(pio_1, sm_array[i + 4]);
	  pio_sm_clear_fifos(pio_1, sm_array[i + 8]);
	}

	/* for (uint32_t channel = 0; channel < 3; */
	/*      channel++)  // read in a single voltage value for each of 6 channels */
	/*   { */
	/*     channel_voltage[channel] = get_single_voltage(pio_0, sm_array[channel]); */

	/*     channel_voltage[channel + 3] = */
	/*       get_single_voltage(pio_1, sm_array[channel + 3]); */
	/*   } */

	/* gpio_put(all_pins.enablePin, 0);  // set mux to current */
	sleep_ms(1);
      }
    }
  return 0;
}
