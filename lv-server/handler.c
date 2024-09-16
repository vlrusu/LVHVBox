// Ed Callaghan
// Client handlers
// September 2024

#include <unistd.h>
#include "handler.h"
#include "utils.h"

void* client_handler(void* args){
  client_handler_args_t* casted = (client_handler_args_t*) args;
  int addr = casted->client_addr;
  PriorityQueue_t* queue = casted->queue;

  char buffer[512];
  int stop = 0;
  while (0 < read(addr, buffer, sizeof(buffer))){
    // generate new task
    task_t task;
    task.addr = addr;
    task.complete = 0;
    task.error = 0;

    uint32_t zero = buffer[3];
    uint32_t one = buffer[2] << 8;
    uint32_t two = buffer[1] << 16;
    uint32_t three = buffer[0] << 24;
    task.command.name = zero + one + two + three;

    uint32_t zero_0 = buffer[7];
    uint32_t one_0 = buffer[6] << 8;
    uint32_t two_0 = buffer[5] << 16;
    uint32_t three_0 = buffer[4] << 24;
    task.command.type = zero_0 + one_0 + two_0 + three_0;
    
    memcpy(&task.command.char_parameter, &buffer[8], 1);
    memcpy(&task.command.float_parameter, &buffer[9], 4);

    // submit to queue
    queue_push(&task);

    // wait until task is complete
    // TODO

    // send response back to client
    // TODO
  }
}
