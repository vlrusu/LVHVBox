/*============================================================================
* File:     usb_comm.c
* Author:   Vadim Rusu
* Created:  2025-05-15
*============================================================================*/
#include "usb_comm.h"
#include "init.h"
#include "daq.h"
#include "tusb.h"
#include "pico/bootrom.h"
#include <string.h>

void cdc_task(uint sm_array[]) {
    if (!tud_cdc_available()) return;

    uint8_t cmd[5];
    tud_cdc_read(cmd, sizeof(cmd));
    tud_cdc_read_flush();

    uint8_t ch = cmd[0];

    // ----- Trip specific channel -----
    if (ch >= 103 && ch < 109) {
        uint8_t pin = all_pins.crowbarPins[ch - 103];
        if (trip_mask & (1 << (ch - 103))) {
            current_buffer_run = 0;
            before_trip_allowed = 20;
            memcpy(ped_subtraction_stored, ped_subtraction, sizeof(ped_subtraction));
            gpio_put(pin, 1);
            trip_status |= (1 << (ch - 103));
        }
    }
    // ----- Reset trip for a channel -----
    else if (ch >= 109 && ch < 115) {
        current_buffer_run = 1;
        remaining_buffer_iterations = full_current_history_length / 2;
        uint8_t pin = all_pins.crowbarPins[ch - 109];
        trip_mask &= ~(1 << (ch - 109));
        gpio_put(pin, 0);
        trip_status &= ~(1 << (ch - 109));
        sleep_ms(250);
        trip_mask |= (1 << (ch - 109));
    }
    // ----- Disable trip capability -----
    else if (ch >= 115 && ch < 121) {
        trip_mask &= ~(1 << (ch - 115));
    }
    // ----- Enable trip capability -----
    else if (ch >= 121 && ch < 127) {
        trip_mask |= (1 << (ch - 121));
    }
    // ----- Send trip status -----
    else if (ch == 33) {
        tud_cdc_write(&trip_status, sizeof(trip_status));
        tud_cdc_write_flush();
    }
    // ----- Send trip mask -----
    else if (ch == 99) {
        tud_cdc_write(&trip_mask, sizeof(trip_mask));
        tud_cdc_write_flush();
    }
    // ----- Set trip threshold current -----
    else if (ch >= 76 && ch < 82) {
        uint16_t val = (cmd[1] << 8) | cmd[2];
        trip_currents[ch - 76] = (float)val / 65535 * 1000;
    }
    // ----- Pedestal control -----
    else if (ch == 37) {
        gpio_put(all_pins.PedPin, 1);
        ped_on = 1;

	
    } else if (ch == 38) {
        gpio_put(all_pins.PedPin, 0);
        ped_on = 0;
    }
    // ----- Get pedestals forced ----
    else if (ch > 38 && ch < 45) {
      if (ped_on == 1) {
        gpio_put(all_pins.PedPin, 0);  // put pedestal pin low
        sleep_ms(1400);

        // clear rx fifos
        for (uint32_t i = 0; i < 3; i++) {
          pio_sm_clear_fifos(pio0, sm_array[i]);
          pio_sm_clear_fifos(pio1, sm_array[i + 4]);
	  pio_sm_clear_fifos(pio2, sm_array[i + 8]);
        }

        int32_t pre_ped_subtraction[6] = {0, 0, 0, 0, 0, 0};

        for (int ped_count = 0; ped_count < 200; ped_count++) {
          for (int i = 0; i < 2; i++) {
            pre_ped_subtraction[i] +=
	      (int16_t)pio_sm_get_blocking(pio0, sm_array[2*i]);
            pre_ped_subtraction[i + 2] +=
	      (int16_t)pio_sm_get_blocking(pio1, sm_array[2*i + 4]);
            pre_ped_subtraction[i + 4] +=
	      (int16_t)pio_sm_get_blocking(pio2, sm_array[2*i + 8]);
          }
        }

        for (int i = 0; i < 6; i++) {
          ped_subtraction[i] = (float)pre_ped_subtraction[i] / 200 * adc_to_uA;
        }

        gpio_put(all_pins.PedPin, 1);  // put pedestal pin high

        // update ped_subtraction_stored
        if (current_buffer_run == 1) {
          memcpy(ped_subtraction_stored, ped_subtraction,
                 sizeof(ped_subtraction));
        }

        sleep_ms(700);
      }
    }
    
    
    // ----- Send voltages or currents -----
    else if (ch == 86 || ch == 73) {
        for (uint8_t i = 0; i < 6; i++) {
            float* ptr = &channel_current_averaged[(ch == 86 ? 2*i+1 : 2*i)];
            tud_cdc_write(ptr, sizeof(float));
        }
        tud_cdc_write_flush();
    }
    // ----- Start or stop current buffer -----
    else if (ch == 87) {
        current_buffer_run = 1;
        remaining_buffer_iterations = full_current_history_length / 2;
    } else if (ch == 88) {
        current_buffer_run = 0;
    }
    // ----- Send chunk of current buffer (10 values) -----
    //FIXME - send voltages as well
    else if (ch >= 89 && ch < 95) {
        int ch_idx = ch - 89;
        float buf[10];
        for (int i = 0; i < 10; i++) {
            int idx = (full_position + i) % full_current_history_length;
            float val = full_current_array[2*ch_idx][idx] *  adc_to_uA;
            if (ped_on) val -= ped_subtraction_stored[ch_idx];

	    //            float val = full_current_array[ch_idx][idx] * (ch_idx % 2 ? adc_to_V : adc_to_uA);
	    //            if (ped_on && ch_idx % 2 == 0) val -= ped_subtraction_stored[ch_idx];

	    
	    buf[i] = val;
        }
        tud_cdc_write(buf, sizeof(buf));
        tud_cdc_write_flush();
        full_position = (full_position + 10) % full_current_history_length;
    }
    // ----- Send slow_read status -----
    else if (ch == 97) {
        tud_cdc_write(&slow_read, sizeof(slow_read));
        tud_cdc_write_flush();
    }
    // ----- Send current buffer run status -----
    else if (ch == 95) {
        tud_cdc_write(&current_buffer_run, sizeof(current_buffer_run));
        tud_cdc_write_flush();
    }
    // ----- Advance full_position by 10 -----
    else if (ch == 96) {
        full_position = (full_position + 10) % full_current_history_length;
    }
    // ----- Send averaged current history (2 samples per channel) -----
    else if (ch == 72) {
        if (average_store_position > 1) {
            for (uint8_t i = 0; i < 2; i++) {
                for (uint8_t j = 0; j < 6; j++) {
                    tud_cdc_write(&average_current_history[2*j][i], sizeof(float));
                }
            }
            tud_cdc_write_flush();
            for (int i = 0; i < average_store_position - 2; i++) {
                for (int j = 0; j < 6; j++) {
                    average_current_history[2*j][i] = average_current_history[2*j][i+2];
                }
            }
            average_store_position -= 2;
        } else {
            float val = -100;
            tud_cdc_write(&val, sizeof(val));
            tud_cdc_write_flush();
        }
    }
    // ----- Send averaged HV ADC value -----
    else if (ch == 98) {
        float adc_val = 0;
        for (int i = 0; i < 50; i++) adc_val += adc_read();
        adc_val /= 50;
        tud_cdc_write(&adc_val, sizeof(adc_val));
        tud_cdc_write_flush();
    }
    // ----- Set new trip trigger count requirement -----
    else if (ch > 44 && ch < 51) {
        uint16_t val = (cmd[2] << 8) | cmd[1];
        trip_requirement[ch - 45] = (int)val;
    }
    // ----- Reboot to BOOTSEL mode -----
    else if (ch == 255) {
        reset_usb_boot(0, 0);
    }
}
