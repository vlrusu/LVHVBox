// Ed Callaghan
// Structured messages
// January 2025

#ifndef MESSAGES_H
#define MESSAGES_H

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/param.h>
#include <unistd.h>

typedef struct {
  char type;
  unsigned int count;
  unsigned int used;
  char* bytes;
} MessageBlock_t;

typedef struct {
  unsigned int count;
  unsigned int space;
  MessageBlock_t** blocks;
} Message_t;

unsigned int typed_sizeof(char);
unsigned int typed_printf(char, char*);

void unstructured_cp(MessageBlock_t*, void**);
void as_chars(MessageBlock_t*, char**);
void as_ints(MessageBlock_t*, int**);
void as_uints(MessageBlock_t*, unsigned int**);
void as_floats(MessageBlock_t*, float**);
void as_doubles(MessageBlock_t*, double**);

MessageBlock_t* block_construct(char, unsigned int);
void block_destroy(MessageBlock_t*);
void block_insert(MessageBlock_t*, void*);
void block_print(MessageBlock_t*);

Message_t* message_construct();
void message_destroy(Message_t*);
void message_blocks_realloc(Message_t*);
void message_append(Message_t*, MessageBlock_t*);
void message_print(Message_t*);

MessageBlock_t* header_initialize();
Message_t* message_initialize();

ssize_t block_send(MessageBlock_t*, int);
ssize_t message_send(Message_t*, int);
ssize_t block_recv(MessageBlock_t**, int);
ssize_t message_recv(Message_t**, int);

Message_t* message_wrap_int(int);
Message_t* message_wrap_float(float);

int message_as_int(Message_t*);
float message_as_float(Message_t*);
int message_unwrap_int(Message_t*);
float message_unwrap_float(Message_t*);

#endif
