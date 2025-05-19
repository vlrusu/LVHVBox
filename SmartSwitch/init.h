// init.h
#ifndef INIT_H
#define INIT_H

#include <stdint.h>
#include "hardware/pio.h"

#define mChn 6
#define nAdc 6
#define full_current_history_length 8000
#define short_current_history_length 50
#define average_current_history_length 2000
#define SM_COUNT 12

struct Pins {
    uint8_t crowbarPins[mChn];
    uint8_t PedPin;
    uint8_t sclk_0, sclk_1, sclk_2;
    uint8_t csPin_0, csPin_1, csPin_2;
    uint8_t idata0, vdata0, idata1, vdata1;
    uint8_t idata2, vdata2, idata3, vdata3;
    uint8_t idata4, vdata4, idata5, vdata5;
};

extern struct Pins all_pins;

extern float ped_subtraction[6];
extern float ped_subtraction_stored[6];
extern float channel_current_averaged[12];
extern float average_current_history[12][average_current_history_length];
extern uint32_t full_current_array[12][full_current_history_length];
extern uint32_t short_current_array[6][short_current_history_length];

extern uint8_t trip_mask;
extern uint8_t trip_status;
extern uint8_t slow_read;
extern uint8_t current_buffer_run;
extern int before_trip_allowed;
extern int ped_on;
extern int trip_requirement[6];
extern uint16_t num_trigger[6];
extern float trip_currents[6];
extern uint16_t full_position;
extern uint16_t short_position;
extern uint16_t average_store_position;
extern int remaining_buffer_iterations;
extern const float adc_to_V;
extern const float adc_to_uA;

void port_init();
void variable_init();
void setup_output_pins(uint8_t* pins, size_t count);

#endif // INIT_H
