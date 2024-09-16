// Ed Callaghan
// Task interface
// September 2024

#ifndef TASK_H
#define TASK_H

#include <pthread.h>
#include "Command.h"

typedef struct{
  command_t command;
  int addr;
  int complete;
  int error;
  pthread_mutex_t mutex;
} task_t;

int complete(task_t*);

#endif
