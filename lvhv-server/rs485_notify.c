#include "rs485_notify.h"
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#ifndef RS485_POWER_ON_SOCKET
#define RS485_POWER_ON_SOCKET "/run/rs485-server/power-on.sock"
#endif

int rs485_notify_power_on(unsigned int channel, int power_result) {
    if (channel != 6 || power_result != 0) return 0;
    const char event[] = "lv-all-on-v1";
    struct sockaddr_un address = {0};
    address.sun_family = AF_UNIX;
    if (strlen(RS485_POWER_ON_SOCKET) >= sizeof address.sun_path) {
        errno = ENAMETOOLONG;
        return -1;
    }
    strcpy(address.sun_path, RS485_POWER_ON_SOCKET);
    int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) return -1;
    int result = -1;
    if (fcntl(fd, F_SETFD, FD_CLOEXEC) != -1 &&
        fcntl(fd, F_SETFL, O_NONBLOCK) != -1) {
        ssize_t sent = sendto(fd, event, sizeof event - 1, 0,
                             (struct sockaddr *)&address, sizeof address);
        if (sent == (ssize_t)(sizeof event - 1)) result = 0;
    }
    int saved_errno = errno;
    close(fd);
    errno = saved_errno;
    return result;
}
