// Ed Callaghan
// Quick and dirty binary-heap implementation, to allow for a priority queue
// September 2024

#ifndef BINARYHEAP_H
#define BINARYHEAP_H

#include <stddef.h>
#include <stdlib.h>

typedef unsigned int HeapKey_t;
typedef struct {
  void* payload;
  HeapKey_t key;
} HeapNode_t;

typedef struct {
  HeapNode_t** buffer;
  size_t size;
  size_t count;
} Heap_t;

void heap_init(Heap_t*, size_t);
void heap_destroy(Heap_t*);
void heap_push(Heap_t*, HeapNode_t*);
HeapNode_t* heap_pop(Heap_t*);

#endif
