/* Protocol-only probe. No daemon, GPIO, I2C, USB, or hardware command handlers. */
#include "Messages.h"
#include "Protocol.h"
#include <errno.h>
#include <stdint.h>
#include <sys/socket.h>

static unsigned int allocations, reads, sends;
static int fail_allocation(void) {
    const char *n = getenv("FAIL_ALLOCATION");
    return n && ++allocations == (unsigned int)strtoul(n, NULL, 10);
}
void *probe_malloc(size_t n) { if (fail_allocation()) { errno = ENOMEM; return NULL; } return malloc(n); }
void *probe_calloc(size_t n, size_t width) { if (fail_allocation()) { errno = ENOMEM; return NULL; } return calloc(n, width); }
void *probe_realloc(void *p, size_t n) { if (fail_allocation()) { errno = ENOMEM; return NULL; } return realloc(p, n); }
ssize_t probe_read(int fd, void *p, size_t n) {
    if (getenv("FRAGMENT_IO")) {
        ++reads;
        if (reads % 17 == 1) { errno = EINTR; return -1; }
        if (reads % 17 == 2) { errno = EAGAIN; return -1; }
        if (n > 2) n = 2;
    }
    return read(fd, p, n);
}
ssize_t probe_send(int fd, const void *p, size_t n, int flags) {
    if (getenv("FRAGMENT_IO")) {
        ++sends;
        if (sends % 17 == 1) { errno = EINTR; return -1; }
        if (sends % 17 == 2) { errno = EAGAIN; return -1; }
        if (n > 2) n = 2;
    }
    return send(fd, p, n, flags);
}

static int constructors(void) {
    for (int i = 0; i < 100; ++i) {
        Message_t *m = message_initialize();
        message_destroy(m);
        m = message_wrap_chars("100% ERROR %n");
        if (m) {
            if (m->blocks[1]->used != strlen("100% ERROR %n") ||
                memcmp(m->blocks[1]->bytes, "100% ERROR %n", strlen("100% ERROR %n"))) return 2;
            message_destroy(m);
        }
        m = message_wrap_chars(""); message_destroy(m);
        m = message_wrap_error(-3); message_destroy(m);
        m = message_wrap_float(1.25f); message_destroy(m);
        m = message_wrap_double(2.5); message_destroy(m);
    }
    MessageBlock_t *b = block_construct('Z', 100); if (b) return 3;
    b = block_construct('F', UINT32_MAX); if (b) return 4;
    b = block_construct('I', 1);
    if (b) {
        int n = 42;
        block_insert(b, &n); block_insert(b, &n); // Reject capacity overrun.
        if (b->valid) return 5;
        block_destroy(b);
    }
    block_destroy(NULL); message_destroy(NULL);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    if (!strcmp(argv[1], "constructors")) return constructors();
    if (argc != 3) return 2;
    int fd = atoi(argv[2]);
    if (!strcmp(argv[1], "send") || !strcmp(argv[1], "backpressure")) {
        Message_t *m = message_initialize();
        if (!m) return 2;
        unsigned int count = !strcmp(argv[1], "backpressure") ? 1048576 : 1;
        MessageBlock_t *b = block_construct('F', count);
        if (!b) { message_destroy(m); return 2; }
        b->used = count;
        message_append(m, b);
        int small = 1024;
        setsockopt(fd, SOL_SOCKET, SO_SNDBUF, &small, sizeof small);
        ssize_t sent = message_send(m, fd); int error = errno;
        message_destroy(m);
        printf("%zd %d\n", sent, error); close(fd); return 0;
    }
    unsigned int rounds = !strcmp(argv[1], "twice") ? 2 : 1;
    for (unsigned int i = 0; i < rounds; ++i) {
        Message_t *m = NULL;
        ssize_t received = message_recv(&m, fd); int error = errno;
        if (!strcmp(argv[1], "parse")) {
            printf("%zd %d %d\n", received, error, m ? message_is_request(m) : 0);
            message_destroy(m); close(fd); return 0;
        }
        if (received <= 0 || !m) { message_destroy(m); close(fd); return 3; }
        ssize_t sent = message_send(m, fd);
        message_destroy(m);
        if (sent < 0) { close(fd); return 4; }
    }
    close(fd); return 0;
}
