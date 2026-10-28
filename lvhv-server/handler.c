// Ed Callaghan
// Client handlers
// September 2024

#include <unistd.h>
#include "../commands.h"
#include "handler.h"
#include "Protocol.h"
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
  free(casted);

  char msg[128];
  snprintf(msg, sizeof msg, "new client session open at fd %d", addr);
  log_write(logger, msg, LOG_INFO);

  Message_t* message = NULL;
  while (0 < message_recv(&message, addr)){
    // Reject malformed request layouts before task creation or hardware dispatch.
    if (!message_is_request(message)) break;

    // generate new task
    task_t task;
    task_init(&task);
    task.addr = addr;
    task.complete = 0;
    task.error = 0;

    // unpack message into task, and deallocate
    task.command.name = block_as_uint(message->blocks[LVHV_REQUEST_COMMAND]);
    task.command.type = block_as_uint(message->blocks[LVHV_REQUEST_SUBSYSTEM]);
    task.command.char_parameter = message->blocks[LVHV_REQUEST_CHANNEL]->bytes[0];
    task.command.float_parameter = block_as_float(message->blocks[LVHV_REQUEST_NUMERIC]);
    snprintf(msg, sizeof(msg), "client %d received command %s (%" PRIu32 ")",
             addr, command_name(task.command.name), task.command.name);
    log_write(logger, msg, LOG_DETAIL);

    message_destroy(message);
    message = NULL;

    // submit to relevant queue
    int queued = 0;
    QueueItem_t* item = malloc(sizeof(QueueItem_t));
    if (!item) { task_destroy(&task); break; }
    task.rv = NULL;
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
        snprintf(msg, sizeof msg, "WARNING: command issued to invalid pico %zu channel %d", pico_id, channel);
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
          snprintf(msg, sizeof msg, "client %d pico command to unknown channel %d", addr, task.command.char_parameter);
          log_write(logger, msg, LOG_INFO);
        }
      }
    }
    else{
      snprintf(msg, sizeof msg, "client %d command of unknown type %u", addr, task.command.type);
      log_write(logger, msg, LOG_INFO);
    }

    // wait until task is complete
    if (queued){
      pthread_mutex_lock(&(task.mutex));
      while (!task.complete){
        // TODO catch errors here
        pthread_cond_wait(&(task.condition), &(task.mutex));
      }
      pthread_mutex_unlock(&(task.mutex));
    }

    // send response back to client
    //write(task.addr, &(task.rv), sizeof(task.rv));
    ssize_t sent = message_send(task.rv, task.addr);
    message_destroy(task.rv);
    free(item);
    task_destroy(&task);
    if (sent < 0) break;
  }

  message_destroy(message);

  snprintf(msg, sizeof msg, "closing client session for fd %d", addr);
  log_write(logger, msg, LOG_INFO);
  close(addr);
  pthread_exit(NULL);
}
