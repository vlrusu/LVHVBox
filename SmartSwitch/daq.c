/*============================================================================
 * File:     daq.c
 * Author:   Vadim Rusu
 * Created:  2025-05-15
 *============================================================================*/

#include "daq.h"
#include "init.h"
#include "hardware/pio.h"
#include <math.h>
#include <string.h>

void get_all_averaged_currents(PIO p0, PIO p1, PIO p2, uint sm[]) {
  float latest[3];
  float* curr = channel_current_averaged;

  if (before_trip_allowed > 0) before_trip_allowed--;

  memset(curr, 0, sizeof(float) * 12);

  for (int i = 0; i < 200; i++) {

    for (uint32_t channel = 0; channel < 4; channel++) {

      if (pio_sm_is_rx_fifo_full(pio0, sm[channel]) ||
	  pio_sm_is_rx_fifo_full(pio1, sm[channel + 4]) ||
	  pio_sm_is_rx_fifo_full(pio2, sm[channel + 8]) 
	  ) {
	if (i > 10 && before_trip_allowed == 0) {
	  slow_read = 1;
	}
      }
    }

      
    for (int ch = 0; ch < 4; ch++) {
      latest[0] = (int16_t)pio_sm_get_blocking(p0, sm[ch]);
      latest[1] = (int16_t)pio_sm_get_blocking(p1, sm[ch+4]);
      latest[2] = (int16_t)pio_sm_get_blocking(p2, sm[ch+8]);

      for (int j = 0; j < 3; j++) {
	curr[ch + 4 * j] += latest[j];
	if (remaining_buffer_iterations > 0) {
	  full_current_array[ch + 4 * j][full_position] = (uint32_t)latest[j];
	  if (ch % 2 == 0) short_current_array[ch/2 + 2 * j][short_position] = (uint32_t)latest[j];
	}
      }

      if (ch % 2 == 0 && before_trip_allowed == 0) {
	for (int j = 0; j < 3; j++) {
	  int index = (j * 2) + (ch / 2);
	  float value = latest[j] * adc_to_uA - ped_subtraction[index];
	  if ((trip_mask & (1 << index)) && !(trip_status & (1 << index))) {
	    if (value > trip_currents[index])
	      num_trigger[index]++;
	    else if (num_trigger[index] > 0)
	      num_trigger[index]--;
	  }
	}
      }
    }
  }

  for (int ch = 0; ch < 6; ch++) {
    int idx = 2 * ch;
    curr[idx]   = curr[idx] * adc_to_uA / 200 - (ped_on ? ped_subtraction[ch] : 0);
    curr[idx+1] = curr[idx+1] * adc_to_V / 200;
  }

  short_position = (short_position + 1) % short_current_history_length;
  
  if (remaining_buffer_iterations > 0) {
    full_position = (full_position + 1) % full_current_history_length;
    if (!current_buffer_run) remaining_buffer_iterations--;
  }

  for (int ch = 0; ch < 6; ch++) {
    if (num_trigger[ch] >= trip_requirement[ch] && before_trip_allowed == 0) {
      for (int i = 0; i < 6; i++) num_trigger[i] = 0;
      if (current_buffer_run) {
	remaining_buffer_iterations = full_current_history_length / 2;
	current_buffer_run = 0;
      }

      float max_val = 0;
      int max_ch = -1;
      for (int i = 0; i < 6; i++) {
	float sum = 0;
	for (int j = 0; j < 25; j++) { //the short buffer is 50 long, if 25 gets increased, that needs to increase as well
	  int idx = (full_position + full_current_history_length - j) % full_current_history_length;
	  int short_idx = (short_position + short_current_history_length - j) % short_current_history_length;
	  sum += short_current_array[i][short_idx] * adc_to_uA - trip_currents[i];
	}
	if (sum > max_val && !(trip_status & (1 << i))) {
	  max_val = sum;
	  max_ch = i;
	}
      }
      if (max_ch >= 0) {
	gpio_put(all_pins.crowbarPins[max_ch], 1);
	before_trip_allowed = 20;
	trip_status |= (1 << max_ch);
      }
      break;
    }
  }
}

void store_average_currents() {
  if (average_store_position >= average_current_history_length) {
    average_store_position = 0;
    for (int i = 0; i < 12; i++) {
      memset(average_current_history[i], 0, sizeof(float) * average_current_history_length);
    }
  }
  for (int i = 0; i < 12; i++) {
    average_current_history[i][average_store_position] = channel_current_averaged[i];
  }
  average_store_position++;
}
