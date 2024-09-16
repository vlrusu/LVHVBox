// Ed Callaghan
// A thread-safe (!) priority queue
// September 2024

#ifndef PRIORITY_QUEUE_H
#define PRIORITY_QUEUE_H

#include <pthread.h>
#include "BinaryHeap.h"

typedef struct {
  Heap_t heap;
  pthread_mutex_t mutex;
} PriorityQueue_t;
typedef HeapNode_t QueueItem_t;

void queue_init(PriorityQueue_t*, size_t);
void queue_destroy(PriorityQueue_t*);
void queue_push(PriorityQueue_t*, QueueItem_t*);
QueueItem_t* queue_pop(PriorityQueue_t*);

#endif
