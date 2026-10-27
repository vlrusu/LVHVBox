/* Run only linked with these hardware stubs and --gc-sections; never a device test. */
#include "i2c_routines.h"
#include <assert.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>

static int wrapped, fail_reset, logged, reset_calls;
int setup_gpio(uint32_t pin) {
    if (pin == 25) ++reset_calls;
    return fail_reset && pin == 25 ? -1 : 0;
}
int write_gpio_value(uint32_t pin, int value) { (void)pin; (void)value; return 0; }
int msleep(long ms) { (void)ms; return 0; }
int MCP_pinWrite(MCP* mcp, uint8_t pin, uint8_t value) {
    (void)mcp; (void)pin; (void)value; return 0;
}
int error_log(const char* message) { (void)message; ++logged; return 0; }
Message_t* message_wrap_int(int value) { wrapped = value; return NULL; }

int main(int argc, char** argv) {
    assert(argc == 2);
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK, 0);
    assert(fd >= 0);
    struct sockaddr_un address = {0};
    address.sun_family = AF_UNIX;
    assert(strlen(argv[1]) < sizeof address.sun_path);
    strcpy(address.sun_path, argv[1]);
    assert(bind(fd, (struct sockaddr*)&address, sizeof address) == 0);
    uint8_t map[6] = {4,3,2,7,6,5};
    char event[32];
    for (int ch = 0; ch < 6; ++ch) {
        i2c_lv_power_on(ch, map);
        assert(wrapped == 0);
        assert(recv(fd, event, sizeof event, 0) == -1 && errno == EAGAIN);
    }
    i2c_lv_power_on(6, map);
    assert(wrapped == 0);
    assert(reset_calls == 1);
    assert(recv(fd, event, sizeof event, 0) == 12);
    assert(memcmp(event, "lv-all-on-v1", 12) == 0);
    i2c_lv_power_off(6, map);
    assert(wrapped == 0);
    assert(recv(fd, event, sizeof event, 0) == -1 && errno == EAGAIN);
    fail_reset = 1;
    i2c_station_reset();
    assert(wrapped == -1);
    assert(recv(fd, event, sizeof event, 0) == -1 && errno == EAGAIN);
    fail_reset = 0;
    i2c_station_reset();
    assert(wrapped == 0 && reset_calls == 3);
    assert(recv(fd, event, sizeof event, 0) == -1 && errno == EAGAIN);
    close(fd); unlink(argv[1]);
    int previous = logged;
    i2c_lv_power_on(6, map);
    assert(wrapped == 0 && logged == previous + 1);
    puts("PASS: powerOn with reset, separate reset, reset failure, unavailable RS485; hardware stubbed");
    return 0;
}
