// Ed Callaghan
// Structured messages
// January 2025

#include "Messages.h"

unsigned int typed_sizeof(char type){
  switch (type){
    case 'C':
      return sizeof(char);
      break;
    case 'I':
      return sizeof(int);
      break;
    case 'U':
      return sizeof(unsigned int);
      break;
    case 'F':
      return sizeof(float);
      break;
    case 'D':
      return sizeof(double);
      break;
    default:
      return 0;
      break;
  }
}

unsigned int typed_printf(char type, char* buf){
  switch (type){
    case 'C':
      printf("%c", *((char*) buf));
      break;
    case 'I':
      printf("%d", *((int*) buf));
      break;
    case 'U':
      printf("%u", *((unsigned int*) buf));
      break;
    case 'F':
      printf("%f", *((float*) buf));
      break;
    case 'D':
      printf("%f", *((double*) buf));
      break;
    default:
      printf("%c", '!');
      break;
  }
}

void unstructured_cp(MessageBlock_t* block, void** out){
  unsigned int size = block->used * typed_sizeof(block->type);
  *out = (void*) malloc(size);
  memcpy(*out, block->bytes, size);
}

void as_chars(MessageBlock_t* block, char** out){
  unstructured_cp(block, (void**) out);
  *out = (char*) *out;
}

void as_ints(MessageBlock_t* block, int** out){
  unstructured_cp(block, (void**) out);
  *out = (int*) *out;
}

void as_uints(MessageBlock_t* block, unsigned int** out){
  unstructured_cp(block, (void**) out);
  *out = (unsigned int*) *out;
}

void as_floats(MessageBlock_t* block, float** out){
  unstructured_cp(block, (void**) out);
  *out = (float*) *out;
}

void as_doubles(MessageBlock_t* block, double** out){
  unstructured_cp(block, (void**) out);
  *out = (double*) *out;
}

MessageBlock_t* block_construct(char type, unsigned int count){
  unsigned int size = typed_sizeof(type);
  MessageBlock_t* rv = (MessageBlock_t*) malloc(sizeof(MessageBlock_t));
  rv->type = type;
  rv->count = count;
  rv->used = 0;
  rv->bytes = (char*) malloc(rv->count * size);
  return rv;
}

void block_destroy(MessageBlock_t* block){
  free(block->bytes);
  free(block);
}

void block_insert(MessageBlock_t* block, void* buf){
  unsigned int size = typed_sizeof(block->type);
  unsigned int offset = block->used * size;
  memcpy(block->bytes + offset, buf, size);
  block->used++;
}

void block_print(MessageBlock_t* block){
  unsigned int size = typed_sizeof(block->type);
  for (unsigned int i = 0 ; i < block->used ; i++){
    unsigned int offset = i * size;
    if (0 < i){
      printf(",");
    }
    typed_printf(block->type, block->bytes + offset);
  }
  printf(";");
}

Message_t* message_construct(){
  Message_t* rv = (Message_t*) malloc(sizeof(Message_t));
  rv->count = 0;
  rv->space = 2;
  rv->blocks = (MessageBlock_t**) malloc(2 * sizeof(MessageBlock_t*));
  return rv;
}

void message_destroy(Message_t* message){
  for (unsigned int i = 0 ; i < message->count ; i++){
    block_destroy(message->blocks[i]);
  }
  free(message);
}

void message_blocks_realloc(Message_t* message){
  size_t target;
  if (message->space == 0){
    target = 2;
  }
  else{
    target = 2 * message->space;
  }
  message->blocks = realloc(message->blocks, target * sizeof(MessageBlock_t*));
  message->space = target;
}

void message_append(Message_t* message, MessageBlock_t* block){
  if (message->count == message->space){
    message_blocks_realloc(message);
  }
  message->blocks[message->count] = block;
  message->count++;
}

void message_print(Message_t* message){
  for (unsigned int i = 0 ; i < message->count ; i++){
    block_print(message->blocks[i]);
  }
}

MessageBlock_t* header_initialize(){
  MessageBlock_t* rv = block_construct('C', 4);
  sprintf(rv->bytes, "LVHV");
  rv->used = 4;
  return rv;
}

Message_t* message_initialize(){
  Message_t* rv = message_construct();
  MessageBlock_t* header = header_initialize();
  message_append(rv, header);
  return rv;
}

ssize_t block_send(MessageBlock_t* block, int fd){
  size_t size = (size_t) (block->used * typed_sizeof(block->type));
  ssize_t rv = 0;
  rv += write(fd, &(block->type), 1);
  rv += write(fd, &(block->used), sizeof(unsigned int));
  rv += write(fd, block->bytes, size);
  return rv;
}

ssize_t message_send(Message_t* message, int fd){
  ssize_t rv = 0;
  rv += write(fd, &(message->count), sizeof(unsigned int));
  for (unsigned int i = 0 ; i < message->count ; i++){
    rv += block_send(message->blocks[i], fd);
  }
  return rv;
}

ssize_t block_recv(MessageBlock_t** dst, int fd){
  const size_t chunk = 256;

  char type;
  unsigned int count;

  ssize_t rv = 0;
  rv += read(fd, &type, 1);
  rv += read(fd, &count, sizeof(unsigned int));
  MessageBlock_t* block = block_construct(type, count);

  unsigned int size = count * typed_sizeof(type);
  char* ptr = block->bytes;

  ssize_t nread;
  unsigned int rest = size;
  unsigned int tbr = MIN(rest, chunk);
  while ((nread = read(fd, ptr, tbr)) != 0){
    ptr += nread;
    rv += nread;
    block->used += (nread / typed_sizeof(type));
    rest -= nread;
    tbr = MIN(rest, chunk);
  }
  assert((unsigned int) (ptr - block->bytes) == size);

  *dst = block;
  return rv;
}

ssize_t message_recv(Message_t** message, int fd){
  *message = message_construct();

  unsigned int rv;
  ssize_t nread;

  // first byte is the block count
  unsigned int count;
  if ((nread = read(fd, &count, sizeof(unsigned int))) < 1){
    // TODO error-out...
    rv = 0;
    return rv;
  }
  rv += nread;

  for (unsigned int i = 0 ; i < count ; i++){
    MessageBlock_t* block;
    rv += block_recv(&block, fd);
    message_append(*message, block);
  }

  char* first = ((*message)->blocks[0])->bytes;
  //assert((int) strncmp(first, "LVHV", 4) == 0);
  if ((int) strncmp(first, "LVHV", 4) != 0){
    rv = 0;
  }
  return rv;
}

Message_t* message_wrap_int(int x){
  Message_t* rv = message_initialize();
  MessageBlock_t* block = block_construct('I', 1);
  block_insert(block, &x);
  message_append(rv, block);
  return rv;
}

Message_t* message_wrap_float(float x){
  Message_t* rv = message_initialize();
  MessageBlock_t* block = block_construct('F', 1);
  block_insert(block, &x);
  message_append(rv, block);
  return rv;
}

int block_as_int(MessageBlock_t* block){
  int* ptr;
  as_ints(block, &ptr);
  int rv = *ptr;
  return rv;
}

float block_as_float(MessageBlock_t* block){
  float* ptr;
  as_floats(block, &ptr);
  float rv = *ptr;
  return rv;
}

int message_unwrap_int(Message_t* message){
  int rv = block_as_int(message->blocks[1]);
  message_destroy(message);
  return rv;
}

float message_unwrap_float(Message_t* message){
  float rv = block_as_float(message->blocks[1]);
  message_destroy(message);
  return rv;
}
