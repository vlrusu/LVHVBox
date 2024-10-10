// Ed Callaghan
// Factoring out the ugliness related to to usb-control of the picos
// October 2024

#include "pico_routines.h"

void pico_write_low(Pico_t* pico, char* src){
  libusb_bulk_transfer(pico->handle, 0x02, src, 1, 0, 0);
}

void pico_read_low(Pico_t* pico, char* buffer, size_t size){
  libusb_bulk_transfer(pico->handle, 0x82, buffer, size, 0, 0);
}

void pico_write_read_low(Pico_t* pico, char* src, char* buffer, size_t size){
  pico_write_low(pico, src);
  pico_read_low(pico, buffer, size);
//libusb_bulk_transfer(pico->handle, 0x02, src, 1, 0, 0);
//libusb_bulk_transfer(pico->handle, 0x82, buffer, size, 0, 0);
}

float pico_get_vhv(Pico_t* pico, uint8_t channel){
  char reading = 'V';
  char* buffer = malloc(24);
  pico_write_read_low(pico, &reading, buffer, 24);

  channel -= pico->channel_offset;
  float rv = * (float*) &buffer[4 * channel];

  free(buffer);
  return rv;
}

float pico_get_ihv(Pico_t* pico, uint8_t channel){
  char reading = 'H';
  char* buffer = malloc(48);
  pico_write_read_low(pico, &reading, buffer, 48);

  channel -= pico->channel_offset;
  float rv = * (float*) &buffer[24 + 4 * channel];

  free(buffer);
  return rv;
}

void* pico_loop(void* args){
  pico_loop_args_t* casted = (pico_loop_args_t*) args;
  PriorityQueue_t* queue = casted->queue;
  Pico_t* pico = casted->pico;
  Logger_t* logger = casted->logger;

  char msg[128];
  while (1) {
    while (queue_size(queue) < 1){
      msleep(100);
    }

    // TODO
    // pop next task off the stack
    QueueItem_t* item = queue_pop(queue);
    task_t* task = (task_t*) (item->payload);
    sprintf(msg, "pico %d received command label %u", pico->id, task->command.name);
    log_write(logger, msg, LOG_VERBOSE);

    // execute pico operation
    float rv;
    // lv commands
    if (task->command.name == COMMAND_get_vhv){
      uint8_t channel = task->command.char_parameter;
      rv = pico_get_vhv(pico, channel);
    }
    else if (task->command.name == COMMAND_get_ihv){
      uint8_t channel = task->command.char_parameter;
      rv = pico_get_ihv(pico, channel);
    }
    // otherwise, have encountered an unexpected command
    else{
      sprintf(msg, "pico %d encountered command of unknown label %u. skipping this command.", pico->id, task->command.name);
      log_write(logger, msg, LOG_INFO);
    }

    // mark task as complete
    sprintf(msg, "pico %d return value = %f", pico->id, rv);
    log_write(logger, msg, LOG_VERBOSE);
    pthread_mutex_lock(&(task->mutex));
    task->rv = rv;
    task->complete = 1;
    pthread_mutex_unlock(&(task->mutex));
    pthread_cond_signal(&(task->condition));
  }
}
