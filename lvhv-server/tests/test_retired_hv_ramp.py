"""Old numeric ramp requests cannot reach hardware; direct DAC commands still work."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from test_station_reset_portable import function

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / 'lvhv-server'


class RetiredHVRampTests(unittest.TestCase):
    def test_actual_i2c_dispatch_rejects_retired_ids_and_preserves_dac_commands(self):
        source = (SERVER / 'i2c_routines.c').read_text()
        loop = source[source.index('void* i2c_loop'):]
        dispatch = loop[loop.index('if (!command_is_valid(&task->command))'):
                        loop.index('// mark task as complete')]
        helpers = '\n'.join(function(source, name) for name in ('i2c_set_hv_by_dac', 'i2c_query_hv_dac_cache'))
        harness = r'''
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "Command.h"
#include "Messages.h"
#include "../commands.h"
typedef struct { uint32_t hv_dac[12]; } i2c_state_t;
typedef struct { command_t command; } task_t;
static unsigned int io_calls;
#define LOG_INFO 2
void log_write(void* logger, char* msg, unsigned int level) {
    (void)logger; (void)msg; (void)level;
}
static Message_t* unexpected_io(void) { ++io_calls; return message_wrap_int(0); }
#define i2c_lv_power_on(...) unexpected_io()
#define i2c_lv_power_off(...) unexpected_io()
#define i2c_station_reset(...) unexpected_io()
#define i2c_read_6V_voltage(...) unexpected_io()
#define i2c_read_6V_current(...) unexpected_io()
#define i2c_read_48V_voltage(...) unexpected_io()
#define i2c_read_48V_current(...) unexpected_io()
int i2c_dac_write(uint8_t channel, uint32_t dac, i2c_state_t* state) {
    ++io_calls; state->hv_dac[channel] = dac; return 0;
}
'''
        harness += helpers
        harness += '''
static Message_t* dispatch(command_t command, i2c_state_t* initial) {
    task_t data = {.command = command}; task_t* task = &data;
    i2c_state_t state = *initial;
    void* logger = NULL; char msg[128]; Message_t* rv;
''' + dispatch + '*initial = state; return rv; }\n'
        harness += r'''
int main(void) {
    i2c_state_t state = {0};
    // Literal retired IDs intentionally independent of the current command header.
    uint32_t retired[] = {344631822u, 1236373670u};
    for (unsigned int i = 0; i < 2; ++i) {
        command_t command = {.name = retired[i], .type = TYPE_hv,
                            .char_parameter = 5, .float_parameter = 1200.f};
        Message_t* reply = dispatch(command, &state);
        assert(io_calls == 0);
        assert(reply && reply->count == 2);
        assert(message_unwrap_int(reply) == -3);
        assert(!strcmp(command_name(retired[i]), "unknown"));
    }
    assert(COMMAND_set_hv_by_dac == 344631823u);
    assert(COMMAND_query_hv_dac_cache == 344631824u);
    command_t command = {.name = COMMAND_set_hv_by_dac, .type = TYPE_hv,
                        .char_parameter = 5, .float_parameter = 100.f};
    assert(message_unwrap_int(dispatch(command, &state)) == 0);
    assert(io_calls == 1 && state.hv_dac[5] == 100);
    command.name = COMMAND_query_hv_dac_cache;
    assert(message_unwrap_int(dispatch(command, &state)) == 100);
    assert(io_calls == 1);
    puts("PASS: retired IDs return failure without IO; direct DAC write/cache preserved");
}
'''
        with tempfile.TemporaryDirectory(prefix='lvhv-retired-ramp-') as directory:
            path = Path(directory)
            (path / 'test.c').write_text(harness)
            result = subprocess.run([shutil.which('cc'), '-std=gnu11', '-fsanitize=address,undefined',
                '-I', str(SERVER), '-I', str(SERVER / 'messaging'), str(path / 'test.c'),
                str(SERVER / 'Command.c'), str(SERVER / 'messaging/Messages.c'), '-o', str(path / 'test')],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(path / 'test')], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('direct DAC write/cache preserved', result.stdout)


if __name__ == '__main__':
    unittest.main()
