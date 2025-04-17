#ifndef PICO_REGISTRY_H
#define PICO_REGISTRY_H

#include <pthread.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    int connected[2];  // Status for each pico (0=disconnected, 1=connected)
    pthread_mutex_t mutex;
} pico_registry_t;

extern pico_registry_t pico_registry;

void pico_registry_init(void);
void pico_registry_set_status(size_t pico_id, int status);
int pico_is_connected(size_t pico_id);

#endif
