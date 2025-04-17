// pico_registry.c
#include "pico_registry.h"

pico_registry_t pico_registry;

void pico_registry_init(void) {
    pico_registry.connected[0] = 0;
    pico_registry.connected[1] = 0;
    pthread_mutex_init(&pico_registry.mutex, NULL);
}

void pico_registry_set_status(size_t pico_id, int status) {
    if (pico_id > 1) return;
    
    pthread_mutex_lock(&pico_registry.mutex);
    pico_registry.connected[pico_id] = status;
    pthread_mutex_unlock(&pico_registry.mutex);
}

int pico_is_connected(size_t pico_id) {
    if (pico_id > 1) return 0;
    
    pthread_mutex_lock(&pico_registry.mutex);
    int status = pico_registry.connected[pico_id];
    pthread_mutex_unlock(&pico_registry.mutex);
    
    return status;
}
