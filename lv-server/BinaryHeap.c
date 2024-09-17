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
  // identify leftmost empty node
  size_t i = 0;
  while ((heap->buffer[i] != NULL) && (i < heap->size - 1)){
    i++;
  }

  // if root is empty, assign and short-circuit
  if (i == 0){
    heap->buffer[i] = node;
  }
  // for nontrivial insertions, append to bottom, and bubble up
  else if (0 < i){
    int stop = 0;
    HeapNode_t* parent;
    while ((0 < i) && (!stop)){
      size_t pi = (i - 1) / 2;
      node = heap->buffer[i];
      parent = heap->buffer[pi];

      // swap node with parent, update indices
      if (parent->key < node->key){
        heap->buffer[i] = parent;
        heap->buffer[pi] = node;
        i = pi;
      }
      else{
        stop = 1;
      }
    }
  }
  else{
    // cannot reach here
  }

  heap->count++;
}

HeapNode_t* heap_pop(Heap_t* heap){
  // identify rightmost empty node
  size_t i = heap->size - 1;
  while ((heap->buffer[i] != NULL) && (0 < i)){
    i--;
  }

  HeapNode_t* rv = heap->buffer[0];
  // if root, overwrite the top node and return
  if (i == 0){
    heap->buffer[i] = NULL;
  }
  // for nontrivial extractions, pull from the top, reset, and bubble down
  else if (0 < i){
    // place rightmost element into root slot
    heap->buffer[0] = heap->buffer[i];
    heap->buffer[i] = NULL;

    int stop = 0;
    HeapNode_t* node;
    HeapNode_t* child;
    while ((i < heap->size - 1) && (!stop)){
      // identify smallest non-null child
      size_t ci = 2+i + 1;
      if (heap->buffer[ci] == NULL){
        stop = 1;
      }
      else if (heap->buffer[ci+1] == NULL){
        if (heap->buffer[ci+1]->key < heap->buffer[ci]->key){
          ci++;
        }
      }
      // assuming there is a child to compare to
      if (!stop){
        node = heap->buffer[i];
        child = heap->buffer[ci];

        // move larger element downward
        if (child->key < node->key){
          heap->buffer[i] = child;
          heap->buffer[ci] = node;
        }
        else{
          stop = 1;
        }
      }
    }
  }
  else{
      // cannot reach here
  }

  heap->count--;
  return rv;
}
