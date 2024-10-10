// Ed Callaghan
// Factoring out the ugliness related to to usb-control of the picos
// October 2024

#ifndef PICO_ROUTINES_H
#define PICO_ROUTINES_H

#include "../commands.h"
#include "utils.h"
#include "Logging.h"
#include "Pico.h"
#include "PriorityQueue.h"
#include "Task.h"

typedef struct {
  PriorityQueue_t* queue;
  Pico_t* pico;
  Logger_t* logger;
} pico_loop_args_t;

void pico_write_low(Pico_t*, char*);
void pico_read_low(Pico_t*, char*, size_t);
void pico_write_read_low(Pico_t*, char*, char*, size_t);
float pico_get_vhv(Pico_t*, uint8_t);
float pico_get_ihv(Pico_t*, uint8_t);
void* pico_loop(void*);

#endif
