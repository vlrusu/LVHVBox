// Ed Callaghan
// Task interface
// September 2024

#include "Task.h"

void task_init(task_t* task){
  pthread_mutex_init(&(task->mutex), NULL);
  pthread_cond_init(&(task->condition), NULL);
}

void task_destroy(task_t* task){
  pthread_cond_destroy(&(task->condition));
  pthread_mutex_destroy(&(task->mutex));
}

int complete(task_t* task){
  pthread_mutex_lock(&(task->mutex));
  int rv = task->complete;
  pthread_mutex_unlock(&(task->mutex));
  return rv;
}
