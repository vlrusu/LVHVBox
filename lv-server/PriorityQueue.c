// Ed Callaghan
// A thread-safe (!) priority queue
// September 2024

#include "PriorityQueue.h"

void queue_init(PriorityQueue_t* queue, size_t size){
  heap_init(&(queue->heap), size);
  pthread_mutex_init(&(queue->mutex), NULL);
}

void queue_destroy(PriorityQueue_t* queue){
  heap_destroy(&(queue->heap));
  pthread_mutex_destroy(&(queue->mutex));
}

void queue_push(PriorityQueue_t* queue, QueueItem_t* item){
  pthread_mutex_lock(&(queue->mutex));
  heap_push(&(queue->heap), (HeapNode_t*) item);
  pthread_mutex_unlock(&(queue->mutex));
}

QueueItem_t* queue_pop(PriorityQueue_t* queue){
  pthread_mutex_lock(&(queue->mutex));
  QueueItem_t* rv = (QueueItem_t*) heap_pop(&(queue->heap));
  pthread_mutex_unlock(&(queue->mutex));
  return rv;
}

size_t queue_size(PriorityQueue_t* queue){
  pthread_mutex_lock(&(queue->mutex));
  size_t rv = queue->heap.count;
  pthread_mutex_unlock(&(queue->mutex));
  return rv;
}
