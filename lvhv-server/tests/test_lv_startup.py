"""Actual C startup code with GPIO, MCP, time and notification stubs only."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_station_reset_portable import function

SERVER = Path(__file__).resolve().parents[1]


class LVStartup(unittest.TestCase):
    def test_staggered_and_immediate_modes_order_failures_and_policy_override(self):
        source = (SERVER / 'i2c_routines.c').read_text()
        definitions = '\n'.join(function(source, name) for name in (
            'station_reset_pulse', 'i2c_lv_power_control', 'i2c_lv_power_on', 'i2c_lv_power_off'))
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "lv_power_policy.h"
#define HIGH 1
#define LOW 0
#define STATION_RESET_PIN 25
typedef struct { int unused; } MCP;
typedef struct { int result; } Message_t;
static MCP fake, *lvpgoodMCP = &fake;
static uint8_t lv_global_enable = 18;
static int events[64], count, writes, gaps, notices, wrapped;
static int fail_global, fail_write, fail_gap;
static uint8_t map[6] = {4,3,2,7,6,5};
static void event(int e) { assert(count < 64); events[count++] = e; }
int setup_gpio(uint32_t pin) { assert(pin == 25); event(100); return 0; }
int write_gpio_value(uint32_t pin, int value) {
    if (pin == 25) event(1000 + value);
    else { assert(pin == 18); event(2000 + value); if (fail_global) return -1; }
    return 0;
}
int msleep(long ms) {
    event(3000 + ms);
    if (ms != 500) { assert(ms == LV_POWER_ON_STAGGER_MS); ++gaps; if (gaps == fail_gap) return -1; }
    return 0;
}
int MCP_pinWrite(MCP* m, uint8_t pin, uint8_t value) {
    assert(m == lvpgoodMCP && pin == map[writes]);
    event(4000 + pin * 2 + value); ++writes;
    return writes == fail_write ? -1 : 0;
}
int error_log(const char* message) { (void)message; return 0; }
Message_t* message_wrap_int(int value) { wrapped = value; return NULL; }
int rs485_notify_power_on(unsigned int channel, int result) {
    if ((channel == 6 || channel == 7) && result == 0) { ++notices; event(5000 + channel); }
    return 0;
}
'''
        harness += definitions
        harness += r'''
static void clear(void) {
    count = writes = gaps = notices = wrapped = fail_global = fail_write = fail_gap = 0;
}
static void startup(int channel) {
    clear(); i2c_lv_power_on(channel, map);
    assert(wrapped == 0 && writes == 6 && notices == 1);
    int at = 0;
    assert(events[at++] == 100); // One reset, held low for the existing 500ms.
    assert(events[at++] == 1000); assert(events[at++] == 3500);
    assert(events[at++] == 1001); assert(events[at++] == 2001);
    for (int i = 0; i < 6; ++i) {
        assert(events[at++] == 4000 + map[i] * 2 + HIGH);
        if (channel == 6 && i < 5) assert(events[at++] == 3000 + LV_POWER_ON_STAGGER_MS);
    }
    assert(events[at++] == 5000 + channel && at == count);
    assert(gaps == (channel == 6 ? 5 : 0));
}
int main(void) {
    startup(6); startup(7);
    for (int i = 1; i <= 6; ++i) {
        clear(); fail_write = i; i2c_lv_power_on(6, map);
        assert(wrapped == -1 && writes == i && gaps == i-1 && notices == 0);
        clear(); fail_write = i; i2c_lv_power_on(7, map);
        assert(wrapped == -1 && writes == 6 && gaps == 0 && notices == 0);
    }
    for (int i = 1; i <= 5; ++i) {
        clear(); fail_gap = i; i2c_lv_power_on(6, map);
        assert(wrapped == -1 && writes == i && gaps == i && notices == 0);
    }
    clear(); fail_global = 1; i2c_lv_power_on(6, map);
    assert(wrapped == -1 && writes == 0 && gaps == 0 && notices == 0);
    clear(); fail_write = 1; i2c_lv_power_off(6, map);
    assert(wrapped == -1 && writes == 6 && count == 7 && gaps == 0 && notices == 0);
    clear(); i2c_lv_power_off(7, map);
    assert(wrapped == -1 && count == 0 && notices == 0);
    clear(); i2c_lv_power_on(8, map);
    assert(wrapped == -1 && count == 0 && notices == 0);
    puts("PASS: real control startup ordering and failures, no hardware access");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.c').write_text(harness)
            for options in ([], ['-DLV_POWER_ON_STAGGER_MS=75']):
                subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', *options, '-I', str(SERVER),
                    str(root / 'test.c'), '-o', str(root / 'test')],
                    check=True, capture_output=True, text=True)
                result = subprocess.run([str(root / 'test')], check=True,
                    capture_output=True, text=True, timeout=10)
                self.assertIn('no hardware access', result.stdout)
