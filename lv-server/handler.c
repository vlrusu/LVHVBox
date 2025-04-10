// Ed Callaghan
// Client handlers
// September 2024

#include <unistd.h>
#include "../commands.h"
#include "handler.h"
#include "utils.h"
#include "pico_routines.h"
#include "pico_registry.h"

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
  Message_t* message;
  while (0 < message_recv(&message, addr)){
    // generate new task
    task_t task;
    task_init(&task);
    task.addr = addr;
    task.complete = 0;
    task.error = 0;
    pthread_cond_init(&(task.condition), NULL);

    // only accept LVHV+cmd+type+char+float
    if (message->count != 5){
      break;
    }
    if (message->blocks[1]->type != 'U'){
      break;
    }
    if (message->blocks[1]->count != 1){
      break;
    }
    if (message->blocks[2]->type != 'U'){
      break;
    }
    if (message->blocks[2]->count != 1){
      break;
    }
    if (message->blocks[3]->type != 'C'){
      break;
    }
    if (message->blocks[3]->count != 1){
      break;
    }
    if (message->blocks[4]->type != 'F'){
      break;
    }
    if (message->blocks[4]->count != 1){
      break;
    }

    // unpack message into task, and deallocate
    unsigned int* u;
    as_uints(message->blocks[1], &u);
    task.command.name = (uint32_t) (*u);
    free(u);
    sprintf(msg, "client %d received command label %u", addr, task.command.name);
    log_write(logger, msg, LOG_DETAIL);

    as_uints(message->blocks[2], &u);
    task.command.type = (uint32_t) (*u);
    free(u);
    sprintf(msg, "client %d received command label %u", addr, task.command.name);
    log_write(logger, msg, LOG_DETAIL);

    char* c;
    as_chars(message->blocks[3], &c);
    task.command.char_parameter = *c;
    free(c);

    float* f;
    as_floats(message->blocks[4], &f);
    task.command.float_parameter = *f;
    free(f);

    message_destroy(message);

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
      // Check if the required pico is connected
      uint8_t channel = task.command.char_parameter;
      size_t pico_id = (channel < 6) ? 0 : 1;

      if (!pico_is_connected(pico_id)) {
        sprintf(msg, "WARNING: command issued to invalid pico %d channel %d", pico_id, channel);
        log_write(logger, msg, LOG_INFO);
        task.rv = message_wrap_chars("ERROR");
      }
      else{
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
    //write(task.addr, &(task.rv), sizeof(task.rv));
    message_send(task.rv, task.addr);
    message_destroy(task.rv);
    free(item);
    task_destroy(&task);
  }

  message_destroy(message);

  sprintf(msg, "closing client session for fd %d", addr);
  log_write(logger, msg, LOG_INFO);
  close(addr);
}
