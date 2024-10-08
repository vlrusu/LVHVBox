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
  Logger_t* logger = casted->logger;

  char msg[128];
  sprintf(msg, "new client session open at fd %d", addr);
  log_write(logger, msg, LOG_INFO);

  char buffer[512];
  int stop = 0;
  int nread;
  while (0 < (nread = read(addr, buffer, sizeof(buffer)))){
    if (nread == 13){
      // generate new task
      task_t task;
      task.addr = addr;
      task.complete = 0;
      task.error = 0;
      pthread_cond_init(&(task.condition), NULL);

      uint32_t zero = buffer[3];
      uint32_t one = buffer[2] << 8;
      uint32_t two = buffer[1] << 16;
      uint32_t three = buffer[0] << 24;
      task.command.name = zero + one + two + three;
      sprintf(msg, "client %d received command label %u", addr, task.command.name);
      log_write(logger, msg, LOG_DETAIL);

      uint32_t zero_0 = buffer[7];
      uint32_t one_0 = buffer[6] << 8;
      uint32_t two_0 = buffer[5] << 16;
      uint32_t three_0 = buffer[4] << 24;
      task.command.type = zero_0 + one_0 + two_0 + three_0;

      memcpy(&task.command.char_parameter, &buffer[8], 1);
      memcpy(&task.command.float_parameter, &buffer[9], 4);

      // submit to queue
      QueueItem_t* item = malloc(sizeof(QueueItem_t));
      item->payload = &task;
      item->key = 0;
      queue_push(queue, item);

      // wait until task is complete
      pthread_mutex_t local_mutex;
      pthread_mutex_lock(&local_mutex);
      while (!complete(&task)){
        // TODO catch errors here
        pthread_cond_wait(&(task.condition), &local_mutex);
      }
      pthread_mutex_unlock(&local_mutex);

      // send response back to client
      write(task.addr, &(task.rv), sizeof(task.rv));
    }
  }

  sprintf(msg, "closing client session for fd %d", addr);
  log_write(logger, msg, LOG_INFO);
  close(addr);
}
