/*============================================================================
* File:     init.c
* Author:   Vadim Rusu
* Created:  2025-05-15
*============================================================================*/

#include "init.h"
#include "hardware/gpio.h"
#include <string.h>

struct Pins all_pins;


// Data buffers and tracking
float channel_current_averaged[12] = {0};
float ped_subtraction[6] = {0};
float ped_subtraction_stored[6] = {0};
float average_current_history[12][average_current_history_length] = {{0}};
uint32_t full_current_array[12][full_current_history_length] = {{0}};
uint32_t short_current_array[6][short_current_history_length] = {{0}};

// Trip control and state
uint8_t trip_mask = 0xFF;              // all channels enabled
uint8_t trip_status = 0xFF;            // all channels initially tripped
uint8_t slow_read = 0;
uint8_t current_buffer_run = 1;
int before_trip_allowed = 0;
int ped_on = 1;

int trip_requirement[6] = {100, 100, 100, 100, 100, 100};
uint16_t num_trigger[6] = {0};
float trip_currents[6] = {20, 20, 20, 20, 20, 20};

// Ring buffer positions
uint16_t full_position = 0;
uint16_t short_position = 0;
uint16_t average_store_position = 0;
int remaining_buffer_iterations = full_current_history_length / 2;

// ADC conversion constants
const float adc_to_V = 2.5 / 32768.0 * 1000;  // mV per code
const float adc_to_uA = (2.5 / 32768.0) / (100.0 * 101.0) * 1e6;  // uA per code

void setup_output_pins(uint8_t* pins, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        gpio_init(pins[i]);
        gpio_set_dir(pins[i], GPIO_OUT);
    }
}

void port_init() {
    setup_output_pins(all_pins.crowbarPins, mChn);
    gpio_init(all_pins.PedPin);
    gpio_set_dir(all_pins.PedPin, GPIO_OUT);
}

void variable_init() {

    if (pico == 1) {
      uint8_t crowbarPins[6] = {7, 0, 8, 15, 18, 22};
        memcpy(all_pins.crowbarPins, crowbarPins, sizeof(crowbarPins));
        all_pins.PedPin = 20;
        all_pins.sclk_0 = 5;  all_pins.csPin_0 = 2;  all_pins.idata0 = 9; all_pins.vdata0 = 10;
        all_pins.idata1 = 1;  all_pins.vdata1 = 4;  all_pins.sclk_1 = 11; all_pins.csPin_1 = 13;
        all_pins.idata2 = 6;  all_pins.vdata2 = 3;  all_pins.idata3 = 14; all_pins.vdata3 = 12;
        all_pins.sclk_2 = 19; all_pins.csPin_2 = 26; all_pins.idata4 = 17; all_pins.vdata4 = 16;
        all_pins.idata5 = 27; all_pins.vdata5 = 21;
    } else {
        uint8_t crowbarPins[6] = {7, 2, 9, 16, 22, 17};
        memcpy(all_pins.crowbarPins, crowbarPins, sizeof(crowbarPins));
        all_pins.PedPin = 15;
        all_pins.sclk_0 = 4;  all_pins.csPin_0 = 0;  all_pins.idata0 = 8;  all_pins.vdata0 = 10;
        all_pins.idata1 = 1;  all_pins.vdata1 = 3;  all_pins.sclk_1 = 20; all_pins.csPin_1 = 13;
        all_pins.idata2 = 6;  all_pins.vdata2 = 5;  all_pins.idata3 = 14; all_pins.vdata3 = 12;
        all_pins.sclk_2 = 11; all_pins.csPin_2 = 19; all_pins.idata4 = 26; all_pins.vdata4 = 27;
        all_pins.idata5 = 18; all_pins.vdata5 = 21;
    }
}

