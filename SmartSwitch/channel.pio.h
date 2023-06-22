// -------------------------------------------------- //
// This file is autogenerated by pioasm; do not edit! //
// -------------------------------------------------- //

#pragma once

#if !PICO_NO_HARDWARE
#include "hardware/pio.h"
#endif

// ------- //
// channel //
// ------- //

#define channel_wrap_target 0
#define channel_wrap 5

static const uint16_t channel_program_instructions[] = {
            //     .wrap_target
    0xe031, //  0: set    x, 17                      
    0x8100, //  1: push   noblock                [1] 
    0xa142, //  2: nop                           [1] 
    0x4001, //  3: in     pins, 1                    
    0x0042, //  4: jmp    x--, 2                     
    0x0000, //  5: jmp    0                          
            //     .wrap
};

#if !PICO_NO_HARDWARE
static const struct pio_program channel_program = {
    .instructions = channel_program_instructions,
    .length = 6,
    .origin = -1,
};

static inline pio_sm_config channel_program_get_default_config(uint offset) {
    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset + channel_wrap_target, offset + channel_wrap);
    return c;
}

void channel_program_init(PIO pio, uint sm, uint offset, uint pin, float div) {
    pio_sm_config c_channel = channel_program_get_default_config(offset);
    pio_gpio_init(pio, pin);
    sm_config_set_in_pins(&c_channel, pin);
    pio_sm_set_consecutive_pindirs(pio, sm, pin, 1, false);
    // Shifting to left matches the customary MSB-first ordering of SPI.
    sm_config_set_in_shift(
        &c_channel,
        false, // Shift-to-right = false (i.e. shift to left)
        false,  // Autopush enabled
        18      // Autopush threshold = 1
    );
    sm_config_set_clkdiv(&c_channel, div);
    pio_sm_init(pio, sm, offset, &c_channel);
}

#endif