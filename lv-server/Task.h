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
  float rv;
  int complete;
  int error;
  pthread_mutex_t mutex;
  pthread_cond_t condition;
} task_t;

int complete(task_t*);

#endif
