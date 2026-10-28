"""Actual server main/headers with device, socket and thread boundaries stubbed."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SERVER = Path(__file__).resolve().parents[1]


class StartupOptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='lvhv-startup-options-')
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        # Keep the real application headers. Only platform/device headers need
        # stand-ins to compile this main-function probe on a non-Linux laptop.
        for name in ('linux/i2c.h', 'linux/i2c-dev.h', 'linux/spi/spidev.h', 'i2c/smbus.h'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('/* No hardware declarations used by main. */\n')
        usb = root / 'libusb-1.0/libusb.h'
        usb.parent.mkdir()
        usb.write_text('''
#ifndef STARTUP_TEST_USB_H
#define STARTUP_TEST_USB_H
struct libusb_device_handle;
#define LIBUSB_OPTION_LOG_LEVEL 0
#define LIBUSB_LOG_LEVEL_WARNING 0
int libusb_init(void*);
int libusb_set_option(void*, int, ...);
void libusb_exit(void*);
#endif
''')
        stubs = root / 'stubs.c'
        stubs.write_text(r'''
#include <assert.h>
#include "connections.h"
#include "i2c_routines.h"
#include "pico_routines.h"
#include "pico_registry.h"
#include "spi_routines.h"

uint8_t lv_mcp_reset, lv_global_enable;
MCP *lvpgoodMCP, *hvMCP;

void log_init(Logger_t* log, char* path, unsigned int limit, int print) {
    (void)log; (void)limit; (void)print;
    printf("LOG_STUB path=%s\n", path ? path : "none");
}
void log_write(Logger_t* log, char* text, unsigned int level) {
    (void)log; (void)level; puts(text);
}
void log_destroy(Logger_t* log) {
    (void)log; free(lvpgoodMCP); free(hvMCP);
}
int initialize_spi(void) { puts("SPI_STUB"); return 0; }
int initialize_i2c(uint8_t channel_map[6]) {
    const uint8_t expected[6] = {4,3,2,7,6,5};
    assert(lv_mcp_reset == 27 && lv_global_enable == 18);
    assert(memcmp(channel_map, expected, sizeof expected) == 0);
    puts("I2C_STUB"); return 0;
}
int libusb_init(void* context) { (void)context; return 0; }
int libusb_set_option(void* context, int option, ...) {
    (void)context; (void)option; return 0;
}
void libusb_exit(void* context) { (void)context; }
void pico_registry_init(void) {}
void pico_registry_set_status(size_t id, int connected) {
    (void)id; (void)connected;
}
void pico_init(Pico_t* pico, uint16_t vendor, size_t id, size_t offset) {
    (void)vendor; pico->id = id; pico->channel_offset = offset; pico->handle = NULL;
}
void queue_init(PriorityQueue_t* queue, size_t size) {
    (void)queue; assert(size == 1024);
}
int open_server(unsigned int port, int backlog) {
    printf("SOCKET_STUB port=%u backlog=%d\n", port, backlog); return -1;
}
void* foyer(void* args) { (void)args; abort(); }
void* i2c_loop(void* args) { (void)args; abort(); }
void* pico_loop(void* args) { (void)args; abort(); }
int stub_pthread_create(pthread_t* thread, const pthread_attr_t* attr,
                       void* (*function)(void*), void* args) {
    *thread = (pthread_t)0; (void)attr; (void)function; (void)args; return 0;
}
int stub_pthread_join(pthread_t thread, void** result) {
    (void)thread; (void)result; return 0;
}
''')
        cls.probe = root / 'startup-probe'
        result = subprocess.run([
            shutil.which('cc'), '-std=gnu11', '-Werror=implicit-function-declaration',
            '-Dpthread_create=stub_pthread_create', '-Dpthread_join=stub_pthread_join',
            '-I', str(root), '-I', str(SERVER), '-I', str(SERVER / 'messaging'),
            str(SERVER / 'lvhv-server.c'), str(SERVER / 'utils.c'), str(stubs),
            '-o', str(cls.probe),
        ], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_probe(self, *args):
        return subprocess.run([str(self.probe), *args], capture_output=True,
                              text=True, timeout=5)

    def test_default_startup_without_configuration_file(self):
        result = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('LOG_STUB path=none', result.stdout)
        self.assertIn('SPI_STUB', result.stdout)
        self.assertIn('I2C_STUB', result.stdout)
        self.assertIn('SOCKET_STUB port=12000 backlog=3', result.stdout)
        self.assertNotIn('config', result.stdout.lower())

    def test_supported_options_keep_their_values(self):
        result = self.run_probe('-p', '23456', '-b', '9', '-l', '/not-created/test.log')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('LOG_STUB path=/not-created/test.log', result.stdout)
        self.assertIn('SOCKET_STUB port=23456 backlog=9', result.stdout)

    def test_retired_config_and_missing_arguments_fail_before_initialization(self):
        for args in (('-c', 'old-config.txt'), ('-p',), ('-b',), ('-l',)):
            with self.subTest(args=args):
                result = self.run_probe(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('STUB', result.stdout)


if __name__ == '__main__':
    unittest.main()
