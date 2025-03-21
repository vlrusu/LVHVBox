// Ed Callaghan
// Factoring out the ugliness related to to usb-control of the picos
// October 2024

#include "pico_routines.h"

void pico_write_low(Pico_t* pico, char* src, size_t size){
  libusb_bulk_transfer(pico->handle, 0x02, src, size, 0, 0);
}

void pico_write_low_timeout(Pico_t* pico, char* src, size_t size,
                                          unsigned int timeout){
  libusb_bulk_transfer(pico->handle, 0x02, src, size, 0, timeout);
}

void pico_read_low(Pico_t* pico, char* buffer, size_t size){
  libusb_bulk_transfer(pico->handle, 0x82, buffer, size, 0, 0);
}

void pico_read_low_timeout(Pico_t* pico, char* buffer, size_t size,
                                         unsigned int timeout){
  libusb_bulk_transfer(pico->handle, 0x82, buffer, size, 0, timeout);
}

void pico_write_read_low(Pico_t* pico, char* src, size_t isize,
                                       char* buffer, size_t osize){
  pico_write_low(pico, src, isize);
  pico_read_low(pico, buffer, osize);
}

void pico_write_read_low_timeout(Pico_t* pico,
                                 char* src, size_t isize, unsigned int itmout,
                                 char* buf, size_t osize, unsigned int otmout){
  pico_write_low_timeout(pico, src, isize, itmout);
  pico_read_low_timeout(pico, buf, osize, otmout);
}

Message_t* pico_get_vhv(Pico_t* pico, uint8_t channel, Logger_t* logger){
  char msg[128];
  { // run pico_query_trip_status_all manually to test pico handle
    char trip_cmd = 33;  // Command used in pico_query_trip_status_all
    int trip_status = 0;
    int transferred = 0;
    int result = libusb_bulk_transfer(pico->handle, 0x02, &trip_cmd, 1, &transferred, 0);
    sprintf(msg, "pico_get_vhv: Trip command send result=%d", result);
    log_write(logger, msg, LOG_INFO);

    transferred = 0;
    result = libusb_bulk_transfer(pico->handle, 0x82, (char*)&trip_status, sizeof(int), &transferred, 0);
    sprintf(msg, "pico_get_vhv: Trip status read result=%d, status=%d", result, trip_status);
    log_write(logger, msg, LOG_INFO);
  }

  char reading = 'V';
  char* buffer = malloc(24);
  pico_write_read_low(pico, &reading, 1, buffer, 24);

  { // run pico_query_trip_status_all manually to test pico handle
    char trip_cmd = 33;  // Command used in pico_query_trip_status_all
    int trip_status = 0;
    int transferred = 0;
    int result = libusb_bulk_transfer(pico->handle, 0x02, &trip_cmd, 1, &transferred, 0);
    sprintf(msg, "pico_get_vhv: Trip command send result=%d", result);
    log_write(logger, msg, LOG_INFO);

    transferred = 0;
    result = libusb_bulk_transfer(pico->handle, 0x82, (char*)&trip_status, sizeof(int), &transferred, 0);
    sprintf(msg, "pico_get_vhv: Trip status read result=%d, status=%d", result, trip_status);
    log_write(logger, msg, LOG_INFO);
  }

  // After reading the 24-byte buffer, check all channels
  for (int i = 0; i < 6; i++) {
    float value = *(float*)&buffer[4 * i];
    sprintf(msg, "pico_get_vhv: Channel %d value: %.9f",
            i + pico->channel_offset, value);
    log_write(logger, msg, LOG_INFO);
  }

  // Show the raw bytes for all 24 bytes (6 floats)
  for (int i = 0; i < 6; i++) {
    sprintf(msg, "pico_get_vhv: Channel %d raw bytes: %02X %02X %02X %02X",
            i + pico->channel_offset,
            buffer[4*i] & 0xFF,
            buffer[4*i+1] & 0xFF,
            buffer[4*i+2] & 0xFF,
            buffer[4*i+3] & 0xFF);
    log_write(logger, msg, LOG_INFO);

    uint32_t raw_int = *(uint32_t*)&buffer[4 * i];
    sprintf(msg, "pico_get_vhv: Channel %d as uint32: %u",
            i + pico->channel_offset, raw_int);
    log_write(logger, msg, LOG_INFO);
  }

  sprintf(msg, "pico_get_vhv: Channel: %d",channel);
  log_write(logger, msg, LOG_INFO);
  channel -= pico->channel_offset;
  sprintf(msg, "pico_get_vhv: Channel: %d",channel);
  log_write(logger, msg, LOG_INFO);
  float frv = * (float*) &buffer[4 * channel];
  Message_t* rv = message_wrap_float(frv);

  free(buffer);
  return rv;
}

Message_t* pico_get_ihv(Pico_t* pico, uint8_t channel){
  char reading = 'H';
  char* buffer = malloc(48);
  pico_write_read_low(pico, &reading, 1, buffer, 48);

  channel -= pico->channel_offset;
  float frv = * (float*) &buffer[24 + 4 * channel];
  Message_t* rv = message_wrap_float(frv);

  free(buffer);
  return rv;
}

Message_t* pico_enable_trip(Pico_t* pico, uint8_t channel){
  char writeable = 121 + channel - pico->channel_offset;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_disable_trip(Pico_t* pico, uint8_t channel){
  char writeable = 115 + channel - pico->channel_offset;;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_reset_trip(Pico_t* pico, uint8_t channel){
  char writeable = 109 + channel - pico->channel_offset;;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_force_trip(Pico_t* pico, uint8_t channel){
  char writeable = 103 + channel - pico->channel_offset;;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_program_trip_threshold(Pico_t* pico, uint8_t channel, float threshold){
  uint16_t encoded = (uint16_t) (65535 * (threshold / 1000.0));

  char writeable[3];
  writeable[0] = 76 + channel - pico->channel_offset;
  writeable[1] = (encoded >> 8) & 0xFFFF;
  writeable[2] = (encoded >> 0) & 0xFFFF;

  pico_write_low(pico, writeable, sizeof(writeable));
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_program_trip_count(Pico_t* pico, uint8_t channel, float count){
  uint16_t casted = (uint16_t) count;

  char writeable[3];
  writeable[0] = 45 + channel - pico->channel_offset;
  writeable[1] = (casted >> 8) & 0xFFFF;
  writeable[2] = (casted >> 0) & 0xFFFF;

  pico_write_low(pico, writeable, sizeof(writeable));
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_query_trip_enabled_all(Pico_t* pico){
  char writeable = 99;
  int irv;
  pico_write_read_low(pico, &writeable, 1, (char*) &irv, sizeof(irv));
  Message_t* rv = message_wrap_int(irv);
  return rv;
}

Message_t* pico_query_trip_enabled(Pico_t* pico, uint8_t channel){
  Message_t* message_mask = pico_query_trip_enabled_all(pico);
  int mask = message_unwrap_int(message_mask);

  int selection = (1 << (channel - pico->channel_offset));
  int irv = (mask & selection) != 0;
  Message_t* rv = message_wrap_int(irv);
  return rv;
}

Message_t* pico_query_trip_status_all(Pico_t* pico, Logger_t* logger){
  char writeable = 33;
  int irv;

  char msg[128];
  sprintf(msg, "pico_query_trip_status_all: ENTER pico=%p, id=%d",
        (void*)pico, pico->id);
  log_write(logger, msg, LOG_INFO);

  sprintf(msg, "pico_query_trip_status_all: Sending command 33 (!)", writeable);
  log_write(logger, msg, LOG_INFO);

  pico_write_read_low(pico, &writeable, 1, (char*) &irv, sizeof(irv));

  sprintf(msg, "pico_query_trip_status_all: Received raw trip status: %d (0x%08X)", irv, irv);
  log_write(logger, msg, LOG_INFO);

  sprintf(msg, "pico_query_trip_status_all: Binary: %c%c%c%c%c%c",
        (irv & 0x20) ? '1' : '0',
        (irv & 0x10) ? '1' : '0',
        (irv & 0x08) ? '1' : '0',
        (irv & 0x04) ? '1' : '0',
        (irv & 0x02) ? '1' : '0',
        (irv & 0x01) ? '1' : '0');
  log_write(logger, msg, LOG_INFO);

  Message_t* rv = message_wrap_int(irv);
  return rv;
}

Message_t* pico_query_trip_status(Pico_t* pico, uint8_t channel, Logger_t* logger){
  Message_t* message_mask = pico_query_trip_status_all(pico, logger);
  int mask = message_unwrap_int(message_mask);

  int selection = (1 << (channel - pico->channel_offset));
  int irv = (mask & selection) != 0;
  Message_t* rv = message_wrap_int(irv);
  return rv;
}

// only for pico 0
Message_t* pico_query_current(Pico_t* pico){
  char writeable = 98;
  float frv;
  pico_write_read_low(pico, &writeable, 1, (char*) &frv, sizeof(frv));
  frv *= 3.3 / 4096;
  Message_t* rv = message_wrap_int(frv);
  return rv;
}

// only for pico 1
Message_t* pico_query_pcb_temperature(Pico_t* pico){
  char writeable = 98;
  float frv;
  pico_write_read_low(pico, &writeable, 1, (char*) &frv, sizeof(frv));
  frv *= 3.3 / 4096;
  frv = 1.8455 - frv;
  frv /= 0.01123;
  Message_t* rv = message_wrap_int(frv);
  return rv;
}

Message_t* pico_get_slow_read(Pico_t* pico, uint8_t channel){
  char writeable = 97;
  char readable;
  pico_write_read_low(pico, &writeable, 1, &readable, 1);
  int irv = (int) readable;
  Message_t* rv = message_wrap_int(irv);
  return rv;
}

Message_t* pico_get_buffer_status(Pico_t* pico, uint8_t channel){
  char writeable = 95;
  char readable;
  pico_write_read_low(pico, &writeable, 1, &readable, 1);
  int irv = (int) readable;
  Message_t* rv = message_wrap_int(irv);
  return rv;
}

Message_t* pico_enable_pedestal(Pico_t* pico){
  char writeable = 37;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_disable_pedestal(Pico_t* pico){
  char writeable = 38;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_update_pedestal(Pico_t* pico, uint8_t channel){
  char writeable = 39 + channel - pico->channel_offset;;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_begin_current_buffering(Pico_t* pico){
  char writeable = 87;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_end_current_buffering(Pico_t* pico){
  char writeable = 88;
  pico_write_low(pico, &writeable, 1);
  Message_t* rv = message_wrap_int(1);
  return rv;
}

Message_t* pico_query_current_buffer(Pico_t* pico, uint8_t channel){
  char writeable = 89;
  writeable += channel - pico->channel_offset;

  const unsigned int count = 10;
  float buffer[count];
  pico_write_read_low_timeout(pico, &writeable, 1, 50,
                                    (char*) buffer, sizeof(buffer), 500);

  // package into structured message
  MessageBlock_t* block = block_construct('F', count);
  for (unsigned int i = 0 ; i < count ; i++){
    block_insert(block, &buffer[i]);
  }
  Message_t* rv = message_initialize();
  message_append(rv, block);

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
    log_write(logger, msg, LOG_INFO);

    // execute pico operation
    Message_t* rv;
    // lv commands
    if (task->command.name == COMMAND_get_vhv){
      uint8_t channel = task->command.char_parameter;
      sprintf(msg, "pico_loop: entering get_vhv with channel %d", channel);
      log_write(logger, msg, LOG_INFO);
      rv = pico_get_vhv(pico, channel, logger);
    }
    else if (task->command.name == COMMAND_get_ihv){
      uint8_t channel = task->command.char_parameter;
      rv = pico_get_ihv(pico, channel);
    }
    else if (task->command.name == COMMAND_enable_trip){
      uint8_t channel = task->command.char_parameter;
      rv = pico_enable_trip(pico, channel);
    }
    else if (task->command.name == COMMAND_disable_trip){
      uint8_t channel = task->command.char_parameter;
      rv = pico_disable_trip(pico, channel);
    }
    else if (task->command.name == COMMAND_reset_trip){
      uint8_t channel = task->command.char_parameter;
      rv = pico_reset_trip(pico, channel);
    }
    else if (task->command.name == COMMAND_force_trip){
      uint8_t channel = task->command.char_parameter;
      rv = pico_force_trip(pico, channel);
    }
    else if (task->command.name == COMMAND_program_trip_threshold){
      uint8_t channel = task->command.char_parameter;
      float threshold = task->command.float_parameter;
      rv = pico_program_trip_threshold(pico, channel, threshold);
    }
    else if (task->command.name == COMMAND_program_trip_count){
      uint8_t channel = task->command.char_parameter;
      float count = task->command.float_parameter;
      rv = pico_program_trip_count(pico, channel, count);
    }
    else if (task->command.name == COMMAND_query_trip_enabled){
      uint8_t channel = task->command.char_parameter;
      rv = pico_query_trip_enabled(pico, channel);
    }
    else if (task->command.name == COMMAND_query_trip_status){
      uint8_t channel = task->command.char_parameter;
      rv = pico_query_trip_status(pico, channel, logger);
    }
    else if (task->command.name == COMMAND_query_current){
      rv = pico_query_current(pico);
    }
    else if (task->command.name == COMMAND_query_pcb_temperature){
      rv = pico_query_pcb_temperature(pico);
    }
    else if (task->command.name == COMMAND_get_slow_read){
      uint8_t channel = task->command.char_parameter;
      rv = pico_get_slow_read(pico, channel);
    }
    else if (task->command.name == COMMAND_get_buffer_status){
      uint8_t channel = task->command.char_parameter;
      rv = pico_get_buffer_status(pico, channel);
    }
    else if (task->command.name == COMMAND_enable_pedestal){
      rv = pico_enable_pedestal(pico);
    }
    else if (task->command.name == COMMAND_disable_pedestal){
      rv = pico_disable_pedestal(pico);
    }
    else if (task->command.name == COMMAND_update_pedestal){
      uint8_t channel = task->command.char_parameter;
      rv = pico_update_pedestal(pico, channel);
    }
    else if (task->command.name == COMMAND_begin_current_buffering){
      rv = pico_begin_current_buffering(pico);
    }
    else if (task->command.name == COMMAND_end_current_buffering){
      rv = pico_end_current_buffering(pico);
    }
    else if (task->command.name == COMMAND_query_current_buffer){
      // this returns a length-10 subsequence of a length-8000 buffer
      // TODO return arbitrarily many samples
      uint8_t channel = task->command.char_parameter;
      rv = pico_query_current_buffer(pico, channel);
    }
    // otherwise, have encountered an unexpected command
    else{
      sprintf(msg, "pico %d encountered command of unknown label %u. skipping this command.", pico->id, task->command.name);
      log_write(logger, msg, LOG_INFO);
    }

    // mark task as complete
    // sprintf(msg, "pico %d return value = %f", pico->id, rv);
    // log_write(logger, msg, LOG_VERBOSE);
    pthread_mutex_lock(&(task->mutex));
    task->rv = rv;
    task->complete = 1;
    pthread_mutex_unlock(&(task->mutex));
    pthread_cond_signal(&(task->condition));
  }
}
