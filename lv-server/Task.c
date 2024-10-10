// Ed Callaghan
// Task interface
// September 2024

#include "Task.h"

void task_init(task_t* task){
  pthread_mutex_init(&(task->mutex), NULL);
}

void task_destroy(task_t* task){
  pthread_mutex_destroy(&(task->mutex));
}

int complete(task_t* task){
  pthread_mutex_lock(&(task->mutex));
  int rv = task->complete;
  pthread_mutex_unlock(&(task->mutex));
  return rv;
}
