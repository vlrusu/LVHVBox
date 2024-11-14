// Ed Callaghan
// Internals of e.g. socket connections
// September 2024

#ifndef CONNECTIONS_H
#define CONNECTIONS_H

#include <sys/socket.h>
#include <sys/types.h>
#include <netinet/in.h>
#include <stddef.h>

#include "utils.h"
#include "Logging.h"
#include "PriorityQueue.h"
#include "handler.h"

int open_server(unsigned int, int);

typedef struct {
  int fd;
  PriorityQueue_t* i2c_queue;
  PriorityQueue_t* pico_a_queue;
  PriorityQueue_t* pico_b_queue;
  Logger_t* logger;
} foyer_args_t;

void* foyer(void*);

#endif
