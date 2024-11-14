// Ed Callaghan
// Client handlers
// September 2024

#include <unistd.h>
#include "../commands.h"
#include "handler.h"
#include "utils.h"
#include "pico_routines.h"

void* client_handler(void* args){
  client_handler_args_t* casted = (client_handler_args_t*) args;
  int addr = casted->client_addr;
  PriorityQueue_t* i2c_queue = casted->i2c_queue;
  PriorityQueue_t* pico_a_queue = casted->pico_a_queue;
  PriorityQueue_t* pico_b_queue = casted->pico_b_queue;
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
      task_init(&task);
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

      // submit to relevant queue
      int queued = 0;
      QueueItem_t* item = malloc(sizeof(QueueItem_t));
      item->payload = &task;
      item->key = 0;
      // i2c commands
      if ((task.command.type == TYPE_lv) || (task.command.type == TYPE_hv)){
        queue_push(i2c_queue, item);
        queued = 1;
      }
      // pico commands
      else if (task.command.type == TYPE_pico){
        // first, global slow controls are split between the two picos...
        if (task.command.name == COMMAND_query_current){
          queue_push(pico_a_queue, item);
          queued = 1;
        }
        else if (task.command.name == COMMAND_query_pcb_temperature){
          queue_push(pico_b_queue, item);
          queued = 1;
        }
        // otherwise, pico of local command is determined by the channel #
        else if (task.command.char_parameter < 6){
          queue_push(pico_a_queue, item);
          queued = 1;
        }
        else if (task.command.char_parameter < 12){
          queue_push(pico_b_queue, item);
          queued = 1;
        }
        else{
          sprintf(msg, "client %d pico command to unknown channel %d", addr, task.command.char_parameter);
          log_write(logger, msg, LOG_INFO);
        }
      }
      else{
        sprintf(msg, "client %d command of unknown type %u", addr, task.command.type);
        log_write(logger, msg, LOG_INFO);
      }

      // wait until task is complete
      if (queued){
        pthread_mutex_t local_mutex;
        pthread_mutex_init(&local_mutex, NULL);
        pthread_mutex_lock(&local_mutex);
        while (!complete(&task)){
          // TODO catch errors here
          pthread_cond_wait(&(task.condition), &local_mutex);
        }
        pthread_mutex_unlock(&local_mutex);
      }

      // send response back to client
      write(task.addr, &(task.rv), sizeof(task.rv));
      free(item);
      task_destroy(&task);
    }
    else{
      sprintf(msg, "client %d sent message of length %u != 13, ignoring", addr, nread);
      log_write(logger, msg, LOG_INFO);
    }
  }

  sprintf(msg, "closing client session for fd %d", addr);
  log_write(logger, msg, LOG_INFO);
  close(addr);
}
