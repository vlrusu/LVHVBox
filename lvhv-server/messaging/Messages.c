// Ed Callaghan's LVHV protocol API, hardened for bounded framing and ownership.
// Wire constants/layout are generated from protocol/lvhv.json.
#include "Messages.h"
#include "Protocol.h"
#include <errno.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <poll.h>
#include <stdint.h>
#include <sys/socket.h>
#include <time.h>

_Static_assert(CHAR_BIT == 8 && sizeof(int) == 4 && sizeof(unsigned int) == 4,
               "LVHV requires 32-bit int and 8-bit bytes");
_Static_assert(sizeof(float) == 4 && sizeof(double) == 8 && FLT_RADIX == 2 &&
               FLT_MANT_DIG == 24 && DBL_MANT_DIG == 53, "LVHV requires IEEE binary32/64");

unsigned int typed_sizeof(char type) { return lvhv_type_size(type); }

unsigned int typed_printf(char type, char *bytes) {
    if (!bytes) return 0;
    switch (type) {
        case 'C': return (unsigned int)printf("%c", *bytes);
        case 'I': { int x; memcpy(&x, bytes, sizeof x); return (unsigned int)printf("%d", x); }
        case 'U': { unsigned int x; memcpy(&x, bytes, sizeof x); return (unsigned int)printf("%u", x); }
        case 'F': { float x; memcpy(&x, bytes, sizeof x); return (unsigned int)printf("%f", x); }
        case 'D': { double x; memcpy(&x, bytes, sizeof x); return (unsigned int)printf("%f", x); }
        default: return 0;
    }
}

static int block_ok(const MessageBlock_t *b) {
    return b && b->valid && typed_sizeof(b->type) && b->used <= b->count && b->bytes &&
           b->count <= (LVHV_MAX_MESSAGE_BYTES - LVHV_BLOCK_HEADER_BYTES) / typed_sizeof(b->type);
}

MessageBlock_t *block_construct(char type, unsigned int count) {
    unsigned int width = typed_sizeof(type);
    if (!width) { errno = EINVAL; return NULL; }
    if (count > (LVHV_MAX_MESSAGE_BYTES - LVHV_BLOCK_HEADER_BYTES) / width) {
        errno = EMSGSIZE; return NULL;
    }
    MessageBlock_t *b = calloc(1, sizeof *b);
    if (!b) return NULL;
    // Extra byte keeps locally stored character/config values NUL-terminated;
    // it is not included in the wire count or payload.
    b->bytes = calloc((size_t)count * width + 1, 1);
    if (!b->bytes) { free(b); return NULL; }
    b->type = type; b->count = count; b->valid = 1;
    return b;
}

void block_destroy(MessageBlock_t *b) {
    if (b) { free(b->bytes); free(b); }
}

void block_insert(MessageBlock_t *b, void *value) {
    if (!block_ok(b) || !value || b->used == b->count) {
        if (b) b->valid = 0;
        errno = EINVAL; return;
    }
    unsigned int width = typed_sizeof(b->type);
    memcpy(b->bytes + (size_t)b->used * width, value, width);
    ++b->used;
}

void unstructured_cp(MessageBlock_t *b, void **out) {
    if (!out) { errno = EINVAL; return; }
    *out = NULL;
    if (!block_ok(b)) { errno = EINVAL; return; }
    size_t size = (size_t)b->used * typed_sizeof(b->type);
    *out = calloc(size + 1, 1);
    if (*out) memcpy(*out, b->bytes, size);
}
void as_chars(MessageBlock_t *b, char **out) { unstructured_cp(b, (void **)out); }
void as_ints(MessageBlock_t *b, int **out) { unstructured_cp(b, (void **)out); }
void as_uints(MessageBlock_t *b, unsigned int **out) { unstructured_cp(b, (void **)out); }
void as_floats(MessageBlock_t *b, float **out) { unstructured_cp(b, (void **)out); }
void as_doubles(MessageBlock_t *b, double **out) { unstructured_cp(b, (void **)out); }

void block_print(MessageBlock_t *b) {
    if (!block_ok(b)) return;
    for (unsigned int i = 0; i < b->used; ++i) {
        if (i) printf(",");
        typed_printf(b->type, b->bytes + (size_t)i * typed_sizeof(b->type));
    }
    printf(";");
}

Message_t *message_construct(void) {
    Message_t *m = calloc(1, sizeof *m);
    if (!m) return NULL;
    m->space = 2; m->valid = 1;
    m->blocks = calloc(m->space, sizeof *m->blocks);
    if (!m->blocks) { free(m); return NULL; }
    return m;
}

void message_destroy(Message_t *m) {
    if (!m) return;
    for (unsigned int i = 0; i < m->count; ++i) block_destroy(m->blocks[i]);
    free(m->blocks); free(m);
}

void message_blocks_realloc(Message_t *m) {
    if (!m || !m->valid || m->space >= LVHV_MAX_BLOCKS) {
        if (m) m->valid = 0;
        errno = EMSGSIZE; return;
    }
    unsigned int target = m->space ? m->space * 2 : 2;
    if (target > LVHV_MAX_BLOCKS) target = LVHV_MAX_BLOCKS;
    MessageBlock_t **blocks = realloc(m->blocks, (size_t)target * sizeof *blocks);
    if (!blocks) { m->valid = 0; return; }
    m->blocks = blocks; m->space = target;
}

// Always takes ownership of b, including on allocation/validation failure.
void message_append(Message_t *m, MessageBlock_t *b) {
    if (!m || !m->valid || !block_ok(b) || m->count >= LVHV_MAX_BLOCKS) {
        if (m) m->valid = 0;
        block_destroy(b); errno = EINVAL; return;
    }
    if (m->count == m->space) message_blocks_realloc(m);
    if (!m->valid) { block_destroy(b); return; }
    m->blocks[m->count++] = b;
}

void message_print(Message_t *m) {
    if (m) for (unsigned int i = 0; i < m->count; ++i) block_print(m->blocks[i]);
}

MessageBlock_t *header_initialize(void) {
    MessageBlock_t *b = block_construct('C', LVHV_MAGIC_BYTES);
    if (b) { memcpy(b->bytes, LVHV_MAGIC, LVHV_MAGIC_BYTES); b->used = LVHV_MAGIC_BYTES; }
    return b;
}
Message_t *message_initialize(void) {
    Message_t *m = message_construct();
    if (!m) return NULL;
    message_append(m, header_initialize());
    if (!m->valid) { message_destroy(m); return NULL; }
    return m;
}

static int magic_ok(const Message_t *m) {
    if (!m || !m->valid || !m->count || m->count > LVHV_MAX_BLOCKS) return 0;
    MessageBlock_t *b = m->blocks[0];
    return block_ok(b) && b->type == 'C' && b->used == LVHV_MAGIC_BYTES &&
           memcmp(b->bytes, LVHV_MAGIC, LVHV_MAGIC_BYTES) == 0;
}
int message_is_request(const Message_t *m) {
    if (!magic_ok(m) || m->count != LVHV_REQUEST_FIELDS + 1) return 0;
    for (unsigned int i = 0; i < LVHV_REQUEST_FIELDS; ++i) {
        MessageBlock_t *b = m->blocks[i + 1];
        if (!block_ok(b) || b->type != LVHV_REQUEST_TYPES[i] ||
            b->used != LVHV_REQUEST_COUNTS[i]) return 0;
    }
    return 1;
}

static int64_t now_ms(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0) return -1;
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
static int64_t deadline_ms(void) {
    int64_t now = now_ms();
    return now < 0 ? -1 : now + LVHV_FRAME_TIMEOUT_MS;
}
static int wait_fd(int fd, int sending, int64_t deadline) {
    for (;;) {
        int timeout = -1;
        if (deadline >= 0) {
            int64_t now = now_ms();
            if (now < 0) return -1;
            if (now >= deadline) { errno = ETIMEDOUT; return -1; }
            timeout = (int)(deadline - now);
        }
        struct pollfd p = {fd, sending ? POLLOUT : POLLIN, 0};
        int rc = poll(&p, 1, timeout);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0) return -1;
        if (!rc) { errno = ETIMEDOUT; return -1; }
        if (p.revents & POLLNVAL) { errno = EBADF; return -1; }
        if (sending && (p.revents & (POLLHUP | POLLERR))) { errno = EPIPE; return -1; }
        return 0; // A read on HUP consumes any remaining bytes, then reports EOF.
    }
}
static ssize_t exact_io(int fd, void *buffer, size_t size, int sending, int64_t deadline) {
    size_t done = 0;
    while (done < size) {
        if (wait_fd(fd, sending, deadline) < 0) return -1;
        ssize_t rc;
        if (sending) {
            int flags = 0;
#ifdef MSG_DONTWAIT
            flags |= MSG_DONTWAIT;
#endif
#ifdef MSG_NOSIGNAL
            flags |= MSG_NOSIGNAL;
#elif defined(SO_NOSIGPIPE)
            int one = 1;
            if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one) < 0 && errno != ENOTSOCK) return -1;
#endif
            rc = send(fd, (char *)buffer + done, size - done, flags);
            if (rc < 0 && errno == ENOTSOCK) rc = write(fd, (char *)buffer + done, size - done);
        } else {
            rc = read(fd, (char *)buffer + done, size - done);
        }
        if (rc < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (rc < 0) return -1;
        if (!rc) {
            if (!sending && !done) return 0;
            errno = sending ? EPIPE : EPROTO; return -1;
        }
        done += (size_t)rc;
    }
    return (ssize_t)done;
}
static void put_count(unsigned char *p, uint32_t n) {
    for (unsigned int i = 0; i < LVHV_COUNT_BYTES; ++i)
        p[i] = (unsigned char)(n >> (8 * (LVHV_LITTLE_ENDIAN ? i : LVHV_COUNT_BYTES - 1 - i)));
}
static uint32_t get_count(const unsigned char *p) {
    uint32_t n = 0;
    for (unsigned int i = 0; i < LVHV_COUNT_BYTES; ++i)
        n |= (uint32_t)p[i] << (8 * (LVHV_LITTLE_ENDIAN ? i : LVHV_COUNT_BYTES - 1 - i));
    return n;
}
static void swap_payload(char *p, unsigned int count, unsigned int width) {
    const uint16_t one = 1;
    if ((*(const unsigned char *)&one == 1) == LVHV_LITTLE_ENDIAN) return;
    for (unsigned int i = 0; i < count; ++i)
        for (unsigned int j = 0; j < width / 2; ++j) {
            char t = p[(size_t)i * width + j];
            p[(size_t)i * width + j] = p[(size_t)i * width + width - 1 - j];
            p[(size_t)i * width + width - 1 - j] = t;
        }
}

static ssize_t send_block(MessageBlock_t *b, int fd, int64_t deadline) {
    if (!block_ok(b)) { errno = EINVAL; return -1; }
    size_t size = (size_t)b->used * typed_sizeof(b->type);
    unsigned char header[LVHV_BLOCK_HEADER_BYTES]; header[0] = (unsigned char)b->type;
    put_count(header + 1, b->used);
    // Transform a private copy so serialization never mutates a queued reply.
    char *wire = malloc(size ? size : 1);
    if (!wire) return -1;
    memcpy(wire, b->bytes, size);
    swap_payload(wire, b->used, typed_sizeof(b->type));
    int ok = exact_io(fd, header, sizeof header, 1, deadline) == (ssize_t)sizeof header &&
             exact_io(fd, wire, size, 1, deadline) == (ssize_t)size;
    int saved = errno; free(wire); errno = saved;
    return ok ? (ssize_t)(sizeof header + size) : -1;
}
ssize_t block_send(MessageBlock_t *b, int fd) {
    int64_t deadline = deadline_ms();
    return deadline < 0 ? -1 : send_block(b, fd, deadline);
}

ssize_t message_send(Message_t *m, int fd) {
    if (!magic_ok(m)) { errno = EINVAL; return -1; }
    size_t size = LVHV_COUNT_BYTES;
    for (unsigned int i = 0; i < m->count; ++i) {
        if (!block_ok(m->blocks[i])) { errno = EINVAL; return -1; }
        size_t n = LVHV_BLOCK_HEADER_BYTES + (size_t)m->blocks[i]->used * typed_sizeof(m->blocks[i]->type);
        if (n > LVHV_MAX_MESSAGE_BYTES - size) { errno = EMSGSIZE; return -1; }
        size += n;
    }
    int64_t deadline = deadline_ms();
    if (deadline < 0) return -1;
    unsigned char prefix[LVHV_COUNT_BYTES]; put_count(prefix, m->count);
    if (exact_io(fd, prefix, sizeof prefix, 1, deadline) != (ssize_t)sizeof prefix) return -1;
    for (unsigned int i = 0; i < m->count; ++i) if (send_block(m->blocks[i], fd, deadline) < 0) return -1;
    return (ssize_t)size;
}

static ssize_t recv_block(MessageBlock_t **out, int fd, size_t budget, int64_t deadline) {
    *out = NULL;
    unsigned char header[LVHV_BLOCK_HEADER_BYTES];
    ssize_t received = exact_io(fd, header, sizeof header, 0, deadline);
    if (received != (ssize_t)sizeof header) { if (received >= 0) errno = EPROTO; return -1; }
    unsigned int width = typed_sizeof((char)header[0]);
    uint32_t count = get_count(header + 1);
    if (!width) { errno = EPROTO; return -1; }
    if (budget < sizeof header || count > (budget - sizeof header) / width) { errno = EMSGSIZE; return -1; }
    MessageBlock_t *b = block_construct((char)header[0], count);
    if (!b) return -1;
    size_t size = (size_t)count * width;
    received = exact_io(fd, b->bytes, size, 0, deadline);
    if (received != (ssize_t)size) {
        int saved = received >= 0 ? EPROTO : errno;
        block_destroy(b); errno = saved; return -1;
    }
    swap_payload(b->bytes, count, width); b->used = count;
    *out = b; return (ssize_t)(sizeof header + size);
}
ssize_t block_recv(MessageBlock_t **out, int fd) {
    if (!out) { errno = EINVAL; return -1; }
    *out = NULL;
    int64_t deadline = deadline_ms();
    return deadline < 0 ? -1 : recv_block(out, fd, LVHV_MAX_MESSAGE_BYTES, deadline);
}
ssize_t message_recv(Message_t **out, int fd) {
    if (!out) { errno = EINVAL; return -1; }
    *out = NULL;
    unsigned char prefix[LVHV_COUNT_BYTES];
    // Preserve idle persistent clients. Once a frame starts, one deadline covers
    // every remaining header/payload; a slow peer cannot reset it per field.
    ssize_t first = exact_io(fd, prefix, 1, 0, -1);
    if (first <= 0) return first;
    int64_t deadline = deadline_ms();
    if (deadline < 0) return -1;
    ssize_t rest = exact_io(fd, prefix + 1, sizeof prefix - 1, 0, deadline);
    if (rest != (ssize_t)sizeof prefix - 1) { if (rest >= 0) errno = EPROTO; return -1; }
    uint32_t count = get_count(prefix);
    if (!count || count > LVHV_MAX_BLOCKS) { errno = EMSGSIZE; return -1; }
    Message_t *m = message_construct();
    if (!m) return -1;
    size_t total = sizeof prefix;
    for (uint32_t i = 0; i < count; ++i) {
        MessageBlock_t *b = NULL;
        ssize_t n = recv_block(&b, fd, LVHV_MAX_MESSAGE_BYTES - total, deadline);
        if (n < 0) { int saved = errno; message_destroy(m); errno = saved; return -1; }
        total += (size_t)n; message_append(m, b);
        if (!m->valid || (!i && !magic_ok(m))) {
            message_destroy(m); errno = EPROTO; return -1;
        }
    }
    *out = m; return (ssize_t)total;
}

static Message_t *wrap(char type, const void *value, unsigned int count) {
    Message_t *m = message_initialize();
    if (!m) return NULL;
    MessageBlock_t *b = block_construct(type, count);
    if (!b) { message_destroy(m); return NULL; }
    if (count) memcpy(b->bytes, value, (size_t)count * typed_sizeof(type));
    b->used = count; message_append(m, b);
    if (!m->valid) { message_destroy(m); return NULL; }
    return m;
}
Message_t *message_wrap_int(int value) { return wrap('I', &value, 1); }
// Preserve the legacy signed-I tag used by this public API.
Message_t *message_wrap_unsigned_int(unsigned int value) { return wrap('I', &value, 1); }
Message_t *message_wrap_float(float value) { return wrap('F', &value, 1); }
Message_t *message_wrap_double(double value) { return wrap('D', &value, 1); }
Message_t *message_wrap_chars(char *value) {
    if (!value) { errno = EINVAL; return NULL; }
    size_t count = strlen(value);
    if (count > LVHV_MAX_MESSAGE_BYTES - LVHV_COUNT_BYTES - 2 * LVHV_BLOCK_HEADER_BYTES - LVHV_MAGIC_BYTES) {
        errno = EMSGSIZE; return NULL;
    }
    return wrap('C', value, (unsigned int)count);
}
Message_t *message_wrap_error(int code) {
    if (!code) code = -1;
    return message_wrap_int(code > 0 ? -code : code);
}

int block_as_int(MessageBlock_t *b) {
    int value = -1;
    if (!block_ok(b) || b->used != 1 || b->type != 'I') errno = EINVAL;
    else memcpy(&value, b->bytes, sizeof value);
    return value;
}
unsigned int block_as_uint(MessageBlock_t *b) {
    unsigned int value = UINT_MAX;
    if (!block_ok(b) || b->used != 1 || b->type != 'U') errno = EINVAL;
    else memcpy(&value, b->bytes, sizeof value);
    return value;
}
float block_as_float(MessageBlock_t *b) {
    float value = NAN;
    if (!block_ok(b) || b->used != 1 || b->type != 'F') errno = EINVAL;
    else memcpy(&value, b->bytes, sizeof value);
    return value;
}
int message_unwrap_int(Message_t *m) {
    int value = -1;
    if (magic_ok(m) && m->count == 2) value = block_as_int(m->blocks[1]); else errno = EINVAL;
    message_destroy(m); return value;
}
float message_unwrap_float(Message_t *m) {
    float value = NAN;
    if (magic_ok(m) && m->count == 2) value = block_as_float(m->blocks[1]); else errno = EINVAL;
    message_destroy(m); return value;
}
