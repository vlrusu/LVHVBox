// -------------------------------------------------- //
// This file is autogenerated by pioasm; do not edit! //
// -------------------------------------------------- //

#pragma once

#if !PICO_NO_HARDWARE
#include "hardware/pio.h"
#endif

// --------- //
// channel_1 //
// --------- //

#define channel_1_wrap_target 0
#define channel_1_wrap 7

static const uint16_t channel_1_program_instructions[] = {
            //     .wrap_target
    0xe031, //  0: set    x, 17                      
    0x8000, //  1: push   noblock                    
    0xa042, //  2: nop                               
    0xa042, //  3: nop                               
    0xa042, //  4: nop                               
    0x4001, //  5: in     pins, 1                    
    0x0043, //  6: jmp    x--, 3                     
    0x0000, //  7: jmp    0                          
            //     .wrap
};

#if !PICO_NO_HARDWARE
static const struct pio_program channel_1_program = {
    .instructions = channel_1_program_instructions,
    .length = 8,
    .origin = -1,
};

static inline pio_sm_config channel_1_program_get_default_config(uint offset) {
    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset + channel_1_wrap_target, offset + channel_1_wrap);
    return c;
}

void channel_1_program_init(PIO pio, uint sm, uint offset, uint pin, float div) {
    pio_sm_config c_channel_1 = channel_1_program_get_default_config(offset);
    pio_gpio_init(pio, pin);
    sm_config_set_in_pins(&c_channel_1, pin);
    pio_sm_set_consecutive_pindirs(pio, sm, pin, 1, false);
    // Shifting to left matches the customary MSB-first ordering of SPI.
    sm_config_set_in_shift(
        &c_channel_1,
        false, // Shift-to-right = false (i.e. shift to left)
        false,  // Autopush enabled
        18      // Autopush threshold = 1
    );
    sm_config_set_clkdiv(&c_channel_1, div);
    pio_sm_init(pio, sm, offset, &c_channel_1);
}

#endif
