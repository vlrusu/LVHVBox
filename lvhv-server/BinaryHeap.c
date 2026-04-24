// Ed Callaghan
// Quick and dirty binary-heap implementation, to allow for a priority queue
// September 2024

#include "BinaryHeap.h"

void heap_init(Heap_t* heap, size_t size){
  heap->buffer = malloc(size * sizeof(HeapNode_t));
  for (size_t i = 0 ; i < size ; i++){
    heap->buffer[i] = NULL;
  }
  heap->size = size;
  heap->count = 0;
}

void heap_destroy(Heap_t* heap){
  free(heap->buffer);
}

void heap_push(Heap_t* heap, HeapNode_t* node){
  if (heap->count >= heap->size){
    return;
  }

  size_t i = heap->count;
  heap->buffer[i] = node;

  while (0 < i){
    size_t pi = (i - 1) / 2;
    HeapNode_t* parent = heap->buffer[pi];

    if (parent->key >= node->key){
      break;
    }

    heap->buffer[i] = parent;
    heap->buffer[pi] = node;
    i = pi;
  }

  heap->count++;
}

HeapNode_t* heap_pop(Heap_t* heap){
  if (heap->count == 0){
    return NULL;
  }

  HeapNode_t* rv = heap->buffer[0];
  heap->count--;

  if (heap->count == 0){
    heap->buffer[0] = NULL;
    return rv;
  }

  HeapNode_t* node = heap->buffer[heap->count];
  heap->buffer[heap->count] = NULL;
  heap->buffer[0] = node;

  size_t i = 0;
  while (1){
    size_t left = 2 * i + 1;
    size_t right = left + 1;
    size_t child = left;

    if (left >= heap->count){
      break;
    }

    if ((right < heap->count) && (heap->buffer[left]->key < heap->buffer[right]->key)){
      child = right;
    }

    if (heap->buffer[child]->key <= node->key){
      break;
    }

    heap->buffer[i] = heap->buffer[child];
    heap->buffer[child] = node;
    i = child;
  }

  return rv;
}
