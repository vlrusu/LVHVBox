// Ed Callaghan
// Client handlers
// September 2024

#ifndef HANDLER_H
#define HANDLER_H

#include "Logging.h"
#include "PriorityQueue.h"
#include "Task.h"

typedef struct {
  int client_addr;
  PriorityQueue_t* queue;
  Logger_t* logger;
} client_handler_args_t;

void* client_handler(void*);

#endif
