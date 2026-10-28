"""Compile actual control functions with GPIO/I2C/sleep/notification stubs only."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

SERVER = Path(__file__).resolve().parents[1]


def function(source, name):
    match = re.search(r'^(?:static )?(?:int|Message_t\*) ' + name + r'\([^\n]*\)\s*\{',
                      source, re.MULTILINE)
    if match is None:
        raise AssertionError('Missing function: ' + name)
    start = source.index('{', match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


class StationResetTests(unittest.TestCase):
    def test_power_and_reset_dispatch_with_hardware_stubs(self):
        source = (SERVER / 'i2c_routines.c').read_text()
        definitions = '\n'.join(function(source, name) for name in (
            'station_reset_pulse', 'i2c_station_reset', 'i2c_lv_power_control',
            'i2c_lv_power_on', 'i2c_lv_power_off'))
        pin_define = re.search(r'^#define STATION_RESET_PIN .*$', source, re.MULTILINE)[0]
        loop = source[source.index('void* i2c_loop'):]
        dispatch = loop[loop.index('if (!command_is_valid(&task->command))'):
                        loop.index('else if (task->command.name == COMMAND_readMonV6)')]
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "Command.h"
#include "../commands.h"
#define HIGH 1
#define LOW 0
typedef struct { int result; } Message_t;
typedef struct { int unused; } MCP;
typedef struct { command_t command; } task_t;
static MCP fake_mcp, *lvpgoodMCP = &fake_mcp;
static uint8_t lv_global_enable = 17;
static int setup_count, write_count, waited, low_count, high_count;
static int mcp_count, notice_count, fail_setup, fail_wait, fail_write = -1;
static Message_t response;
int setup_gpio(uint32_t pin) {
    assert(pin == 25); ++setup_count; return fail_setup ? -1 : 0;
}
int write_gpio_value(uint32_t pin, int value) {
    ++write_count;
    if (pin == 25) {
        if (value == LOW) ++low_count;
        if (value == HIGH) ++high_count;
        if (value == fail_write) return -1;
    } else { assert(pin == 17); }
    return 0;
}
int msleep(long ms) {
    assert(ms == 500 && low_count == 1 && high_count == 0);
    waited = (int)ms; return fail_wait ? -1 : 0;
}
int MCP_pinWrite(MCP* mcp, uint8_t pin, uint8_t value) {
    (void)mcp; (void)pin; (void)value; ++mcp_count; return 0;
}
int error_log(const char* message) { (void)message; return 0; }
Message_t* message_wrap_int(int value) { response.result = value; return &response; }
Message_t* message_wrap_error(int value) { return message_wrap_int(value); }
int rs485_notify_power_on(unsigned int channel, int result) {
    if (channel == 6 && result == 0) ++notice_count;
    return 0;
}
'''
        harness += pin_define + '\n' + definitions
        harness += '''
static Message_t* dispatch(command_t command) {
    task_t item = {.command = command}; task_t* task = &item;
    uint8_t channel_map[6] = {4,3,2,7,6,5}; Message_t* rv;
''' + dispatch + 'else { assert(0); rv = NULL; } return rv; }\n'
        harness += r'''
static void clear(void) {
    setup_count = write_count = waited = low_count = high_count = 0;
    mcp_count = notice_count = fail_setup = fail_wait = 0; fail_write = -1;
}
int main(void) {
    command_t cmd = {.name=COMMAND_powerOn, .type=TYPE_lv, .char_parameter=6};
    clear(); assert(dispatch(cmd)->result == 0);
    assert(setup_count == 1 && low_count == 1 && high_count == 1 && waited == 500);
    assert(mcp_count == 6 && notice_count == 1);
    clear(); fail_setup = 1; assert(dispatch(cmd)->result == -1);
    assert(write_count == 0 && mcp_count == 0 && notice_count == 0);
    clear(); cmd.char_parameter = 2; assert(dispatch(cmd)->result == 0);
    assert(mcp_count == 1 && setup_count == 0 && notice_count == 0);
    clear(); cmd.name = COMMAND_station_reset;
    assert(dispatch(cmd)->result == 0);
    assert(setup_count == 1 && low_count == 1 && waited == 500 && high_count == 1);
    assert(mcp_count == 0 && notice_count == 0);
    assert(strcmp(command_name(COMMAND_station_reset), "station_reset") == 0);
    clear(); fail_setup = 1; assert(dispatch(cmd)->result == -1);
    assert(write_count == 0 && waited == 0);
    clear(); fail_write = LOW; assert(dispatch(cmd)->result == -1);
    assert(waited == 0 && mcp_count == 0);
    clear(); fail_wait = 1; assert(dispatch(cmd)->result == -1);
    assert(high_count == 1 && mcp_count == 0);
    clear(); fail_write = HIGH; assert(dispatch(cmd)->result == -1);
    assert(waited == 500 && mcp_count == 0);
    clear(); cmd.name = COMMAND_powerOff; cmd.char_parameter = 6;
    assert(dispatch(cmd)->result == 0);
    assert(setup_count == 0 && mcp_count == 6 && notice_count == 0);
    puts("PASS: LV On resets then requests discovery; independent GPIO25 reset; all IO stubbed");
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / 'test.c').write_text(harness)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-I', str(SERVER),
                            str(path / 'test.c'), str(SERVER / 'Command.c'),
                            '-o', str(path / 'test')], check=True, capture_output=True, text=True)
            result = subprocess.run([str(path / 'test')], check=True, capture_output=True, text=True)
            self.assertIn('all IO stubbed', result.stdout)


if __name__ == '__main__':
    unittest.main()
