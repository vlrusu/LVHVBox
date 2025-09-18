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
#include <stdbool.h>
#include <stdint.h>

// ==== Command IDs ====
// Trip / mask / thresholds
#define CMD_TRIP_CHANNEL            0x10  // payload: uint8 ch_idx(0..5)
#define CMD_RESET_TRIP              0x11  // payload: uint8 ch_idx
#define CMD_TRIP_DISABLE            0x12  // payload: uint8 ch_idx
#define CMD_TRIP_ENABLE             0x13  // payload: uint8 ch_idx
#define CMD_GET_TRIP_STATUS         0x14  // payload: none -> resp: uint8 trip_status
#define CMD_GET_TRIP_MASK           0x15  // payload: none -> resp: uint8 trip_mask
#define CMD_SET_TRIP_THRESHOLD      0x16  // payload: uint8 ch_idx, float uA
#define CMD_SET_TRIP_REQUIREMENT    0x17  // payload: uint8 ch_idx, uint16 count
#define CMD_GET_TRIP_CURRENTS       0x18  // payload: none -> resp: 6 * float

// Pedestal
#define CMD_PED_ON                  0x20  // payload: none
#define CMD_PED_OFF                 0x21  // payload: none
#define CMD_FORCE_PEDS              0x22  // payload: optional uint16 samples (default 200)

// Currents / Voltages / buffers
#define CMD_GET_CURRENTS            0x30  // payload: none -> resp: 6 * float  (even indices)
#define CMD_GET_VOLTAGES            0x31  // payload: none -> resp: 6 * float  (odd indices)
#define CMD_BUFFER_START            0x32  // payload: none
#define CMD_BUFFER_STOP             0x33  // payload: none
#define CMD_GET_BUFFER_CHUNK        0x34  // payload: uint8 ch_idx(0..5) -> resp: 10 * float
#define CMD_GET_SLOW_READ           0x35  // payload: none -> resp: uint8 slow_read
#define CMD_GET_BUFFER_RUN          0x36  // payload: none -> resp: uint8 current_buffer_run
#define CMD_ADVANCE_BUFFER          0x37  // payload: uint16 step (default 10 if omitted)
#define CMD_GET_AVG_HISTORY         0x38  // payload: none -> resp: 2 samples * 6ch => 12 * float (or -100 if empty)

// ADC / system
#define CMD_GET_HV_ADC              0x40  // payload: uint16 samples (default 50) -> resp: float
#define CMD_REBOOT_TO_BOOTSEL       0xFF  // payload: none


// ==== Small helpers ====
static inline void write_bytes(const void *ptr, size_t n) {
    tud_cdc_write(ptr, (uint32_t)n);
}

static inline void write_u8(uint8_t v) { write_bytes(&v, 1); }
static inline void write_u16_le(uint16_t v) {
    uint8_t b[2] = { (uint8_t)(v & 0xFF), (uint8_t)(v >> 8) };
    write_bytes(b, 2);
}
static inline void write_float(float v) { write_bytes(&v, sizeof(float)); }

// Read exactly n bytes into buf if available; non-blocking: returns false if not enough data
static bool read_exact(uint8_t *buf, uint32_t n) {
    if (tud_cdc_available() < n) return false;
    uint32_t got = tud_cdc_read(buf, n);
    return got == n;
}


// ==== Command handlers ====

static void handle_trip_channel(uint8_t ch_idx) {
    if (ch_idx > 5) return;
    if (trip_mask & (1u << ch_idx)) {
        current_buffer_run = 0;
        before_trip_allowed = 20;
        memcpy(ped_subtraction_stored, ped_subtraction, sizeof(ped_subtraction));
        uint8_t pin = all_pins.crowbarPins[ch_idx];
        gpio_put(pin, 1);
        trip_status |= (1u << ch_idx);
    }
}

static void handle_reset_trip(uint8_t ch_idx) {
    if (ch_idx > 5) return;
    current_buffer_run = 1;
    remaining_buffer_iterations = full_current_history_length / 2;
    uint8_t pin = all_pins.crowbarPins[ch_idx];
    trip_mask &= ~(1u << ch_idx);
    gpio_put(pin, 0);
    trip_status &= ~(1u << ch_idx);
    sleep_ms(250);
    trip_mask |= (1u << ch_idx);
}

static void handle_trip_disable(uint8_t ch_idx) {
    if (ch_idx > 5) return;
    trip_mask &= ~(1u << ch_idx);
}

static void handle_trip_enable(uint8_t ch_idx) {
    if (ch_idx > 5) return;
    trip_mask |= (1u << ch_idx);
}

static void handle_set_trip_threshold(uint8_t ch_idx, float uA) {
    if (ch_idx > 5) return;
    trip_currents[ch_idx] = uA;
}

static void handle_set_trip_requirement(uint8_t ch_idx, uint16_t req) {
    if (ch_idx > 5) return;
    trip_requirement[ch_idx] = (int)req;
}

static void handle_ped_on(void)  { gpio_put(all_pins.PedPin, 1); ped_on = 1; }
static void handle_ped_off(void) { gpio_put(all_pins.PedPin, 0); ped_on = 0; }

static void handle_force_peds(uint sm_array[], uint16_t samples) {
    if (ped_on != 1) return;     // Only do this when pedestal is on

    // put PedPin low
    gpio_put(all_pins.PedPin, 0);
    sleep_ms(1400);

    // clear RX FIFOs
    for (uint32_t i = 0; i < 3; i++) {
        pio_sm_clear_fifos(pio0, sm_array[i]);
        pio_sm_clear_fifos(pio1, sm_array[i + 4]);
        pio_sm_clear_fifos(pio2, sm_array[i + 8]);
    }

    int32_t pre[6] = {0};

    // Expect two channels per PIO (0,1), (4,5), (8,9) – mirrored from your code
    for (uint16_t ped_count = 0; ped_count < samples; ped_count++) {
        for (int i = 0; i < 2; i++) {
            pre[i]     += (int16_t)pio_sm_get_blocking(pio0, sm_array[2*i]);
            pre[i + 2] += (int16_t)pio_sm_get_blocking(pio1, sm_array[2*i + 4]);
            pre[i + 4] += (int16_t)pio_sm_get_blocking(pio2, sm_array[2*i + 8]);
        }
    }

    for (int i = 0; i < 6; i++) {
        ped_subtraction[i] = (float)pre[i] / (float)samples * adc_to_uA;
    }

    gpio_put(all_pins.PedPin, 1);  // put pedestal pin high

    if (current_buffer_run == 1) {
        memcpy(ped_subtraction_stored, ped_subtraction, sizeof(ped_subtraction));
    }

    sleep_ms(700);
}

static void handle_get_currents(void) {
    // even indices are currents: 0,2,4,6,8,10 => 6 values
    for (uint8_t i = 0; i < 6; i++) {
        float *ptr = &channel_current_averaged[2*i]; // I
        write_float(*ptr);
    }
}

static void handle_get_voltages(void) {
    // odd indices are voltages: 1,3,5,7,9,11 => 6 values
    for (uint8_t i = 0; i < 6; i++) {
        float *ptr = &channel_current_averaged[2*i + 1]; // V
        write_float(*ptr);
    }
}

static void handle_buffer_start(void) {
    current_buffer_run = 1;
    remaining_buffer_iterations = full_current_history_length / 2;
}

static void handle_buffer_stop(void) {
    current_buffer_run = 0;
}

static void handle_get_buffer_chunk(uint8_t ch_idx) {
    if (ch_idx > 5) return;
    float buf[10];
    for (int i = 0; i < 10; i++) {
        int idx  = (full_position + i) % full_current_history_length;
        float val = full_current_array[2*ch_idx][idx] * adc_to_uA;
        if (ped_on) val -= ped_subtraction_stored[ch_idx];
        buf[i] = val;
    }
    write_bytes(buf, sizeof(buf));
    full_position = (full_position + 10) % full_current_history_length;
}

static void handle_get_avg_history(void) {
    if (average_store_position > 1) {
        // send 2 samples per channel (currents at even slots)
        for (uint8_t i = 0; i < 2; i++) {
            for (uint8_t j = 0; j < 6; j++) {
                float v = average_current_history[2*j][i];
                write_float(v);
            }
        }
        // pop 2
        for (int i = 0; i < average_store_position - 2; i++) {
            for (int j = 0; j < 6; j++) {
                average_current_history[2*j][i] = average_current_history[2*j][i+2];
            }
        }
        average_store_position -= 2;
    } else {
        float val = -100.0f;
        write_float(val);
    }
}

static void handle_get_hv_adc(uint16_t samples) {
    if (samples == 0) samples = 50;
    float adc_val = 0.0f;
    for (uint16_t i = 0; i < samples; i++) adc_val += adc_read();
    adc_val /= (float)samples;
    write_float(adc_val);
}

// ==== Command dispatcher ====

static void dispatch_cmd(uint8_t cmd, const uint8_t *p, uint8_t len, uint sm_array[]) {
    switch (cmd) {
        // Trip group
        case CMD_TRIP_CHANNEL:
            if (len == 1) handle_trip_channel(p[0]);
            break;
        case CMD_RESET_TRIP:
            if (len == 1) handle_reset_trip(p[0]);
            break;
        case CMD_TRIP_DISABLE:
            if (len == 1) handle_trip_disable(p[0]);
            break;
        case CMD_TRIP_ENABLE:
            if (len == 1) handle_trip_enable(p[0]);
            break;
        case CMD_GET_TRIP_STATUS:
            if (len == 0) { write_u8(trip_status); tud_cdc_write_flush(); }
            break;
        case CMD_GET_TRIP_MASK:
            if (len == 0) { write_u8(trip_mask); tud_cdc_write_flush(); }
            break;
        case CMD_SET_TRIP_THRESHOLD:
            if (len == 1 + sizeof(float)) {
                uint8_t ch_idx = p[0];
                float uA;
                memcpy(&uA, p+1, sizeof(float));
                handle_set_trip_threshold(ch_idx, uA);
            }
            break;
        case CMD_SET_TRIP_REQUIREMENT:
            if (len == 3) {
                uint8_t ch_idx = p[0];
                uint16_t req = (uint16_t)p[1] | ((uint16_t)p[2] << 8);
                handle_set_trip_requirement(ch_idx, req);
            }
            break;
        case CMD_GET_TRIP_CURRENTS:
            if (len == 0) {
                for (uint8_t i = 0; i < 6; i++) write_float(trip_currents[i]);
                tud_cdc_write_flush();
            }
            break;

        // Pedestal
        case CMD_PED_ON:
            if (len == 0) handle_ped_on();
            break;
        case CMD_PED_OFF:
            if (len == 0) handle_ped_off();
            break;
        case CMD_FORCE_PEDS: {
            uint16_t samples = 200;
            if (len == 2) samples = (uint16_t)p[0] | ((uint16_t)p[1] << 8);
            if (len == 0 || len == 2) handle_force_peds(sm_array, samples);
            break;
        }

        // Currents / Voltages / buffers
        case CMD_GET_CURRENTS:
            if (len == 0) { handle_get_currents(); tud_cdc_write_flush(); }
            break;
        case CMD_GET_VOLTAGES:
            if (len == 0) { handle_get_voltages(); tud_cdc_write_flush(); }
            break;
        case CMD_BUFFER_START:
            if (len == 0) handle_buffer_start();
            break;
        case CMD_BUFFER_STOP:
            if (len == 0) handle_buffer_stop();
            break;
        case CMD_GET_BUFFER_CHUNK:
            if (len == 1) { handle_get_buffer_chunk(p[0]); tud_cdc_write_flush(); }
            break;
        case CMD_GET_SLOW_READ:
            if (len == 0) { write_u8(slow_read); tud_cdc_write_flush(); }
            break;
        case CMD_GET_BUFFER_RUN:
            if (len == 0) { write_u8(current_buffer_run); tud_cdc_write_flush(); }
            break;
        case CMD_ADVANCE_BUFFER: {
            uint16_t step = 10;
            if (len == 2) step = (uint16_t)p[0] | ((uint16_t)p[1] << 8);
            if (len == 0 || len == 2) {
                full_position = (full_position + step) % full_current_history_length;
            }
            break;
        }
        case CMD_GET_AVG_HISTORY:
            if (len == 0) { handle_get_avg_history(); tud_cdc_write_flush(); }
            break;

        // ADC / system
        case CMD_GET_HV_ADC: {
            uint16_t samples = 50;
            if (len == 2) samples = (uint16_t)p[0] | ((uint16_t)p[1] << 8);
            if (len == 0 || len == 2) { handle_get_hv_adc(samples); tud_cdc_write_flush(); }
            break;
        }
        case CMD_REBOOT_TO_BOOTSEL:
            if (len == 0) reset_usb_boot(0, 0);
            break;

        default:
            // Unknown command: ignore or send error
            break;
    }
}

// ==== CDC task with header/payload state (non-blocking) ====

void cdc_task(uint sm_array[]) {
    static bool have_header = false;
    static uint8_t hdr_cmd = 0;
    static uint8_t hdr_len = 0;
    static uint8_t payload[64]; 

    if (!tud_cdc_available()) return;

    // 1) Read header if we don't have one
    if (!have_header) {
        if (tud_cdc_available() < 2) return; // need at least cmd+len
        uint8_t hdr[2];
        if (!read_exact(hdr, 2)) return;      // should succeed due to check
        hdr_cmd = hdr[0];
        hdr_len = hdr[1];
        have_header = true;

        if (hdr_len > sizeof(payload)) {
            // Oversized payload, drop it (and clear RX to resync)
            tud_cdc_read_flush();
            have_header = false;
            return;
        }
    }

    // 2) Read payload if enough bytes are available; otherwise come back next tick
    if (hdr_len > 0) {
        if (tud_cdc_available() < hdr_len) return; // wait for the rest
        if (!read_exact(payload, hdr_len)) return; // good to go
    }

    // 3) Dispatch
    dispatch_cmd(hdr_cmd, payload, hdr_len, sm_array);

    // 4) Reset header state
    have_header = false;
}
