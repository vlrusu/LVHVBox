// Ed Callaghan
// Client handlers
// September 2024

#ifndef HANDLER_H
#define HANDLER_H

#include "Task.h"
#include "PriorityQueue.h"

typedef struct {
  int client_addr;
  PriorityQueue_t* queue;
} client_handler_args_t;

void* client_handler(void*);

#endif
