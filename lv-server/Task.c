// Ed Callaghan
// Task interface
// September 2024

#include "Task.h"

int complete(task_t* task){
  pthread_mutex_lock(&(task->mutex));
  int rv = task->complete;
  pthread_mutex_unlock(&(task->mutex));
  return rv;
}
