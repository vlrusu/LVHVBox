"""Real LV/HV control functions and DAC serializer, with GPIO/SPI/timing stubs."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from test_station_reset_portable import function

SERVER = Path(__file__).resolve().parents[1]


class ControlSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='lvhv-control-safety-')
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        source = (SERVER / 'i2c_routines.c').read_text()
        helpers = '\n'.join(function(source, name) for name in (
            'station_reset_pulse', 'i2c_lv_power_control', 'i2c_lv_power_on', 'i2c_lv_power_off',
            'i2c_dac_write', 'i2c_set_hv_by_dac', 'i2c_query_hv_dac_cache'))
        harness = r'''
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "Command.h"
#include "Messages.h"
#include "dac8164.h"
#include "../commands.h"
typedef struct { uint32_t hv_dac[LVHV_HV_CHANNELS]; } i2c_state_t;
#define STATION_RESET_PIN 25
static MCP fake_mcp, *lvpgoodMCP = &fake_mcp;
static uint8_t lv_global_enable = 18;
static DAC8164 hv_dacs[3];
static unsigned int mcp_calls, gpio_calls, notices, fail_call, clocks, wire;
static int gpio_fail, all_fail, last_data;
int setup_gpio(uint32_t pin) { (void)pin; return 0; }
int write_gpio_value(uint32_t pin, int value) {
    (void)value; ++gpio_calls; return pin == lv_global_enable && gpio_fail ? -1 : 0;
}
int msleep(long value) { (void)value; return 0; }
int usleep(unsigned int value) { (void)value; return 0; }
int error_log(const char* message) { (void)message; return 0; }
int MCP_pinMode(MCP* m, uint8_t pin, uint8_t mode) { (void)m; (void)pin; (void)mode; return 0; }
int MCP_pinWrite(MCP* m, uint8_t pin, uint8_t value) {
    (void)m; ++mcp_calls;
    if (all_fail || mcp_calls == fail_call) return -1;
    if (pin == 4) last_data = value;
    if (pin == 2 && value == HIGH) { ++clocks; wire = (wire << 1) | last_data; }
    return 0;
}
int rs485_notify_power_on(unsigned int channel, int result) {
    if (channel == 6 && result == 0) ++notices;
    return 0;
}
static void clear(void) {
    mcp_calls = gpio_calls = notices = fail_call = clocks = wire = 0;
    gpio_fail = all_fail = last_data = 0;
    for (int i = 0; i < 3; ++i)
        hv_dacs[i] = (DAC8164){._MCP=&fake_mcp, ._sclk_pin=2, ._sync_pin=3, ._sdi_pin=4};
}
'''
        harness += helpers
        harness += r'''
static void lv(void) {
    uint8_t map[6] = {4,3,2,7,6,5};
    for (unsigned int failure = 0; failure <= 6; ++failure) {
        clear(); fail_call = failure;
        int result = message_unwrap_int(i2c_lv_power_off(6, map));
        assert(result == (failure ? -1 : 0));
        assert(gpio_calls == 1 && mcp_calls == 6); // finish other shutdown writes
    }
    clear(); gpio_fail = all_fail = 1;
    assert(message_unwrap_int(i2c_lv_power_off(6, map)) == -1);
    assert(gpio_calls == 1 && mcp_calls == 6);
    clear(); gpio_fail = 1;
    assert(message_unwrap_int(i2c_lv_power_off(6, map)) == -1 && mcp_calls == 6);
    clear(); fail_call = 1;
    assert(message_unwrap_int(i2c_lv_power_on(6, map)) == -1 && notices == 0);
    clear(); assert(message_unwrap_int(i2c_lv_power_on(6, map)) == 0 && notices == 1);
    for (unsigned int ch = 7; ch <= 255; ++ch) {
        clear(); assert(i2c_lv_power_control(ch, map, LOW) < 0);
        assert(mcp_calls == 0 && gpio_calls == 0);
    }
    clear(); assert(i2c_lv_power_control(0, NULL, LOW) < 0);
    assert(i2c_lv_power_control(0, map, 2) < 0 && mcp_calls == 0 && gpio_calls == 0);
}
static void hv(void) {
    i2c_state_t state = {0}, before = state;
    for (unsigned int ch = LVHV_HV_CHANNELS; ch <= 255; ++ch) {
        clear(); assert(i2c_dac_write(ch, 100, &state) < 0);
        assert(message_unwrap_int(i2c_set_hv_by_dac(ch, 100, &state)) < 0);
        assert(message_unwrap_int(i2c_query_hv_dac_cache(ch, &state)) < 0);
        assert(mcp_calls == 0 && !memcmp(&before, &state, sizeof state));
    }
    float bad[] = {-1, .5f, 15000.25f, 15001, 65536, FLT_MAX, NAN, INFINITY, -INFINITY};
    for (unsigned int i = 0; i < sizeof bad / sizeof *bad; ++i) {
        clear(); assert(message_unwrap_int(i2c_set_hv_by_dac(0, bad[i], &state)) < 0);
        assert(mcp_calls == 0 && !memcmp(&before, &state, sizeof state));
    }
    clear(); assert(i2c_dac_write(0, UINT32_MAX, &state) < 0 && mcp_calls == 0);
    assert(i2c_dac_write(0, 100, NULL) < 0 && mcp_calls == 0);
    assert(message_unwrap_int(i2c_query_hv_dac_cache(0, NULL)) < 0);
    for (unsigned int channel = 0; channel < LVHV_HV_CHANNELS; ++channel) {
        clear(); assert(message_unwrap_int(i2c_set_hv_by_dac(channel, 15000, &state)) == 0);
        assert(message_unwrap_int(i2c_query_hv_dac_cache(channel, &state)) == 15000);
        assert(mcp_calls == 75 && clocks == 24);
    }
    clear(); assert(message_unwrap_int(i2c_set_hv_by_dac(0, 0, &state)) == 0);
    assert(state.hv_dac[0] == 0);
}
static void dac_failures(void) {
    i2c_state_t state = {0}; state.hv_dac[0] = 777;
    for (unsigned int failure = 1; failure <= 75; ++failure) {
        clear(); fail_call = failure;
        assert(message_unwrap_int(i2c_set_hv_by_dac(0, 100, &state)) == -1);
        assert(state.hv_dac[0] == 777);
        assert(mcp_calls == failure + 2); // abort, then best-effort idle restoration
    }
    clear(); assert(message_unwrap_int(i2c_set_hv_by_dac(0, 100, &state)) == 0);
    assert(state.hv_dac[0] == 100 && wire == 0x100190u && clocks == 24);
    clear(); assert(DAC8164_writeChannel(&hv_dacs[0], 12, 100) < 0 && mcp_calls == 0);
    assert(DAC8164_writeChannel(&hv_dacs[0], 0, 15001) < 0 && mcp_calls == 0);
    assert(DAC8164_writeChannel(NULL, 0, 100) < 0 && mcp_calls == 0);
}
int main(int argc, char** argv) {
    assert(argc == 2);
    if (!strcmp(argv[1], "lv")) lv();
    else if (!strcmp(argv[1], "hv")) hv();
    else if (!strcmp(argv[1], "dac")) dac_failures();
    else return 2;
    puts("PASS: control safety with hardware stubs");
}
'''
        (root / 'test.c').write_text(harness)
        cls.probe = root / 'test'
        result = subprocess.run([shutil.which('cc'), '-std=gnu11', '-g',
            '-fsanitize=address,undefined,float-cast-overflow', '-fno-omit-frame-pointer',
            '-I', str(SERVER), '-I', str(SERVER / 'messaging'), str(root / 'test.c'),
            str(SERVER / 'Command.c'), str(SERVER / 'dac8164.c'),
            str(SERVER / 'messaging/Messages.c'), '-o', str(cls.probe)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_mode(self, mode):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=' + ('0' if sys.platform == 'darwin' else '1') +
                   ':abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
        result = subprocess.run([str(self.probe), mode], capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('control safety', result.stdout)

    def test_lv_failures_reach_ack_without_skipping_other_shutdown_writes(self):
        self.run_mode('lv')

    def test_hv_boundaries_and_bad_values_never_access_or_write_hardware(self):
        self.run_mode('hv')

    def test_every_dac_transfer_failure_propagates_without_advancing_cache(self):
        self.run_mode('dac')
