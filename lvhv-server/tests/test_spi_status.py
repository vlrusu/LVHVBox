"""Actual MCP register-write status handling, with an ioctl stub only."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_station_reset_portable import function

SERVER = Path(__file__).resolve().parents[1]


class SPIStatusTests(unittest.TestCase):
    def test_failed_and_short_spi_writes_are_failures(self):
        source = (SERVER / 'MCP23S08.c').read_text()
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include "MCP23S08.h"
#define OPCODEW 0x40
#define SPI_IOC_MESSAGE(n) 0
struct spi_ioc_transfer { unsigned long tx_buf, rx_buf; unsigned int len, speed_hz;
                          unsigned short delay_usecs; unsigned char bits_per_word; };
uint8_t spi_bpw = 8; uint32_t spi_speed = 40000000; uint16_t spi_delay; int spiFds;
static int transferred, calls;
int ioctl(int fd, int request, struct spi_ioc_transfer* transfer) {
    (void)fd; (void)request; ++calls; assert(transfer->len == 3); return transferred;
}
int error_log(const char* message) { (void)message; return 0; }
'''
        harness += function(source, 'MCP_byteWrite')
        harness += r'''
int main(void) {
    MCP mcp = {0};
    for (transferred = -1; transferred <= 4; ++transferred)
        assert(MCP_byteWrite(&mcp, GPIO, 0) == (transferred == 3 ? 0 : -1));
    assert(calls == 6);
}
'''
        with tempfile.TemporaryDirectory(prefix='lvhv-spi-status-') as directory:
            path = Path(directory)
            (path / 'test.c').write_text(harness)
            result = subprocess.run([shutil.which('cc'), '-std=gnu11', '-I', str(SERVER),
                str(path / 'test.c'), '-o', str(path / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(path / 'test')], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
