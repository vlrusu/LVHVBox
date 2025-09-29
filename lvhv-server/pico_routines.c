// Ed Callaghan
// USB bulk protocol helpers for Picos (updated to [CMD, LEN, PAYLOAD...])
// October 2025

#include "pico_routines.h"
#include <time.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <libusb-1.0/libusb.h>

// ---- Adjust if your endpoints changed in the new firmware ----
#define EP_OUT 0x02   // bulk OUT endpoint address
#define EP_IN  0x82   // bulk IN  endpoint address

// ---- Protocol command IDs (must match firmware) ----
enum {
  CMD_TRIP_CHANNEL            = 0x10, // payload: u8 ch_idx
  CMD_RESET_TRIP              = 0x11, // payload: u8 ch_idx
  CMD_TRIP_DISABLE            = 0x12, // payload: u8 ch_idx
  CMD_TRIP_ENABLE             = 0x13, // payload: u8 ch_idx
  CMD_GET_TRIP_STATUS         = 0x14, // resp: u8
  CMD_GET_TRIP_MASK           = 0x15, // resp: u8
  CMD_SET_TRIP_THRESHOLD      = 0x16, // payload: u8 ch_idx, float uA (LE)
  CMD_SET_TRIP_REQUIREMENT    = 0x17, // payload: u8 ch_idx, u16 count (LE)
  CMD_GET_TRIP_CURRENTS       = 0x18, // resp: 6 * float

  CMD_PED_ON                  = 0x20,
  CMD_PED_OFF                 = 0x21,
  CMD_FORCE_PEDS              = 0x22, // payload: optional u16 samples (LE)

  CMD_GET_CURRENTS            = 0x30, // resp: 6 * float
  CMD_GET_VOLTAGES            = 0x31, // resp: 6 * float
  CMD_BUFFER_START            = 0x32,
  CMD_BUFFER_STOP             = 0x33,
  CMD_GET_BUFFER_CHUNK        = 0x34, // payload: u8 ch_idx -> resp: 10 * float
  CMD_GET_SLOW_READ           = 0x35, // resp: u8
  CMD_GET_BUFFER_RUN          = 0x36, // resp: u8
  CMD_ADVANCE_BUFFER          = 0x37, // payload: optional u16 step (LE, default 10)

  CMD_GET_AVG_HISTORY         = 0x38, // resp: 12 * float or single float(-100.0)

  CMD_GET_HV_ADC              = 0x40, // payload: optional u16 samples (LE) -> resp: float

  CMD_REBOOT_TO_BOOTSEL       = 0xFF
};

// ---- Low-level bulk helpers ----
static inline int bulk_write(libusb_device_handle *h, const void *buf, int len, unsigned int timeout_ms) {
  int xfer = 0;
  int rc = libusb_bulk_transfer(h, EP_OUT, (unsigned char*)buf, len, &xfer, timeout_ms);
  if (rc) return rc;
  return (xfer == len) ? 0 : -1;
}

static inline int bulk_read_exact(libusb_device_handle *h, void *buf, int len, unsigned int timeout_ms) {
  int got = 0;
  while (got < len) {
    int xfer = 0;
    int rc = libusb_bulk_transfer(h, EP_IN, (unsigned char*)buf + got, len - got, &xfer, timeout_ms);
    if (rc) return rc;
    if (xfer <= 0) return -2;
    got += xfer;
  }
  return 0;
}

// ---- Frame helpers: [cmd, len, payload...] ----
static int pico_send_frame(Pico_t* pico, uint8_t cmd, const void* payload, uint8_t plen, unsigned int timeout_ms) {
  uint8_t hdr[2] = { cmd, plen };
  int rc = bulk_write(pico->handle, hdr, 2, timeout_ms);
  if (rc) return rc;
  if (plen && payload) rc = bulk_write(pico->handle, payload, plen, timeout_ms);
  return rc;
}

static int pico_query_frame(Pico_t* pico, uint8_t cmd,
                            const void* payload, uint8_t plen,
                            void* resp, int resp_len,
                            unsigned int wtimeout_ms, unsigned int rtimeout_ms) {
  int rc = pico_send_frame(pico, cmd, payload, plen, wtimeout_ms);
  if (rc) return rc;
  if (resp && resp_len > 0) return bulk_read_exact(pico->handle, resp, resp_len, rtimeout_ms);
  return 0;
}

// ---- Keep thin compatibility wrappers (optional) ----
void pico_write_low(Pico_t* pico, char* src, size_t size){
  // Interpret the first byte of src as CMD, and the rest as payload (legacy caller)
  uint8_t cmd = (uint8_t)src[0];
  const void* payload = (size > 1) ? (const void*)(src + 1) : NULL;
  uint8_t plen = (size > 1) ? (uint8_t)(size - 1) : 0;
  pico_send_frame(pico, cmd, payload, plen, /*timeout*/ 0);
}

void pico_write_low_timeout(Pico_t* pico, char* src, size_t size, unsigned int timeout){
  uint8_t cmd = (uint8_t)src[0];
  const void* payload = (size > 1) ? (const void*)(src + 1) : NULL;
  uint8_t plen = (size > 1) ? (uint8_t)(size - 1) : 0;
  pico_send_frame(pico, cmd, payload, plen, timeout);
}

// These two now assume the caller already knows how many bytes to read (fixed-size replies)
void pico_read_low(Pico_t* pico, char* buffer, size_t size){
  bulk_read_exact(pico->handle, buffer, (int)size, /*timeout*/ 0);
}

void pico_read_low_timeout(Pico_t* pico, char* buffer, size_t size, unsigned int timeout){
  bulk_read_exact(pico->handle, buffer, (int)size, timeout);
}

void pico_write_read_low(Pico_t* pico, char* src, size_t isize, char* buffer, size_t osize){
  pico_write_low(pico, src, isize);
  pico_read_low(pico, buffer, osize);
}

void pico_write_read_low_timeout(Pico_t* pico,
                                 char* src, size_t isize, unsigned int itmout,
                                 char* buf, size_t osize, unsigned int otmout){
  pico_write_low_timeout(pico, src, isize, itmout);
  pico_read_low_timeout(pico, buf, osize, otmout);
}

// ---- High-level helpers (updated to new protocol) ----

Message_t* pico_get_vhvs(Pico_t* pico){
  // Voltages array: CMD_GET_VOLTAGES -> 6 floats
  float arr[6];
  int rc = pico_query_frame(pico, CMD_GET_VOLTAGES, NULL, 0, arr, sizeof(arr), 500, 1000);
  if (rc) return message_wrap_error(rc);

  Message_t* rv = message_initialize();
  MessageBlock_t* block = block_construct('F', 6);
  for (size_t i = 0 ; i < 6 ; i++){
    void* ptr = (void*) (arr + i);
    block_insert(block, ptr);
  }
  message_append(rv, block);
  return rv;
}

Message_t* pico_get_ihvs(Pico_t* pico){
  // Currents array: CMD_GET_CURRENTS -> 6 floats
  float arr[6];
  int rc = pico_query_frame(pico, CMD_GET_CURRENTS, NULL, 0, arr, sizeof(arr), 500, 1000);
  if (rc) return message_wrap_error(rc);

  Message_t* rv = message_initialize();
  MessageBlock_t* block = block_construct('F', 6);
  for (size_t i = 0 ; i < 6 ; i++){
    void* ptr = (void*) (arr + i);
    block_insert(block, ptr);
  }
  message_append(rv, block);
  return rv;
}

Message_t* pico_get_vhv(Pico_t* pico, uint8_t channel){
  // Voltages array: CMD_GET_VOLTAGES -> 6 floats
  float arr[6];
  int rc = pico_query_frame(pico, CMD_GET_VOLTAGES, NULL, 0, arr, sizeof(arr), 500, 1000);
  if (rc) return message_wrap_error(rc);

  channel -= pico->channel_offset;
  if (channel >= 6) return message_wrap_error(-3);
  return message_wrap_float(arr[channel]);
}

Message_t* pico_get_ihv(Pico_t* pico, uint8_t channel){
  // Currents array: CMD_GET_CURRENTS -> 6 floats
  float arr[6];
  int rc = pico_query_frame(pico, CMD_GET_CURRENTS, NULL, 0, arr, sizeof(arr), 500, 1000);
  if (rc) return message_wrap_error(rc);

  channel -= pico->channel_offset;
  if (channel >= 6) return message_wrap_error(-3);
  return message_wrap_float(arr[channel]);
}

Message_t* pico_enable_trip(Pico_t* pico, uint8_t channel){
  uint8_t ch = channel - pico->channel_offset;
  int rc = pico_send_frame(pico, CMD_TRIP_ENABLE, &ch, 1, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_disable_trip(Pico_t* pico, uint8_t channel){
  uint8_t ch = channel - pico->channel_offset;
  int rc = pico_send_frame(pico, CMD_TRIP_DISABLE, &ch, 1, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_reset_trip(Pico_t* pico, uint8_t channel){
  uint8_t ch = channel - pico->channel_offset;
  int rc = pico_send_frame(pico, CMD_RESET_TRIP, &ch, 1, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_force_trip(Pico_t* pico, uint8_t channel){
  uint8_t ch = channel - pico->channel_offset;
  int rc = pico_send_frame(pico, CMD_TRIP_CHANNEL, &ch, 1, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_program_trip_threshold(Pico_t* pico, uint8_t channel, float threshold_uA){
  // Firmware expects microamps as float
  struct __attribute__((packed)) { uint8_t ch; float uA; } p = {
    .ch = (uint8_t)(channel - pico->channel_offset),
    .uA = threshold_uA
  };
  int rc = pico_send_frame(pico, CMD_SET_TRIP_THRESHOLD, &p, sizeof(p), 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_program_trip_count(Pico_t* pico, uint8_t channel, float count){
  // Count is integer; send u16 (LE)
  uint16_t cnt = (uint16_t)count;
  uint8_t payload[3] = { (uint8_t)(channel - pico->channel_offset),
                         (uint8_t)(cnt & 0xFF), (uint8_t)(cnt >> 8) };
  int rc = pico_send_frame(pico, CMD_SET_TRIP_REQUIREMENT, payload, 3, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_query_trip_enabled_all(Pico_t* pico){
  uint8_t mask = 0;
  int rc = pico_query_frame(pico, CMD_GET_TRIP_MASK, NULL, 0, &mask, 1, 500, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(mask);
}

Message_t* pico_query_trip_enabled(Pico_t* pico, uint8_t channel){
  Message_t* m = pico_query_trip_enabled_all(pico);
  int mask = message_unwrap_int(m);
  if (mask < 0) return message_wrap_int(mask); // propagate negative error
  int selection = (1 << (channel - pico->channel_offset));
  return message_wrap_int((mask & selection) ? 1 : 0);
}

Message_t* pico_query_trip_status(Pico_t* pico, uint8_t channel){
  Message_t* m = pico_query_trip_status_all(pico);
  int mask = message_unwrap_int(m);
  if (mask < 0) return message_wrap_int(mask); // propagate negative error
  int selection = (1 << (channel - pico->channel_offset));
  return message_wrap_int((mask & selection) ? 1 : 0);
}
Message_t* pico_query_trip_status_all(Pico_t* pico){
  uint8_t status = 0;
  int rc = pico_query_frame(pico, CMD_GET_TRIP_STATUS, NULL, 0, &status, 1, 500, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(status);
}


Message_t* pico_query_trip_currents(Pico_t* pico, uint8_t channel){
  // Get 6 floats (µA thresholds) and return the selected one
  float arr[6];
  int rc = pico_query_frame(pico, CMD_GET_TRIP_CURRENTS, NULL, 0, arr, sizeof(arr), 500, 1000);
  if (rc) return message_wrap_error(rc);

  channel -= pico->channel_offset;
  if (channel >= 6) return message_wrap_error(-3);
  return message_wrap_float(arr[channel]);
}

// Only for pico 0
Message_t* pico_query_current(Pico_t* pico){
  // AVG HV ADC, default 50 samples → raw float from device
  float v;
  int rc = pico_query_frame(pico, CMD_GET_HV_ADC, NULL, 0, &v, sizeof(v), 500, 500);
  if (rc) return message_wrap_error(rc);
  // preserve your legacy scaling (if you still want it):
  v *= 3.3f / 4096.0f;
  return message_wrap_float(v);
}

// Only for pico 1
Message_t* pico_query_pcb_temperature(Pico_t* pico){
  float v;
  int rc = pico_query_frame(pico, CMD_GET_HV_ADC, NULL, 0, &v, sizeof(v), 500, 500);
  if (rc) return message_wrap_error(rc);
  v *= 3.3f / 4096.0f;
  v = 1.8455f - v;
  v /= 0.01123f;
  return message_wrap_float(v);
}

Message_t* pico_get_slow_read(Pico_t* pico, uint8_t channel){
  (void)channel; // not channel-specific in new protocol
  uint8_t b = 0;
  int rc = pico_query_frame(pico, CMD_GET_SLOW_READ, NULL, 0, &b, 1, 500, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int((int)b);
}

Message_t* pico_get_buffer_status(Pico_t* pico, uint8_t channel){
  (void)channel;
  uint8_t b = 0;
  int rc = pico_query_frame(pico, CMD_GET_BUFFER_RUN, NULL, 0, &b, 1, 500, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int((int)b);
}

Message_t* pico_enable_pedestal(Pico_t* pico){
  int rc = pico_send_frame(pico, CMD_PED_ON, NULL, 0, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_disable_pedestal(Pico_t* pico){
  int rc = pico_send_frame(pico, CMD_PED_OFF, NULL, 0, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_update_pedestal(Pico_t* pico, uint8_t channel){
  (void)channel; // new proto does not need channel for force-peds
  // optional: send samples (u16). Omit for default 200.
  int rc = pico_send_frame(pico, CMD_FORCE_PEDS, NULL, 0, 1000);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_begin_current_buffering(Pico_t* pico){
  int rc = pico_send_frame(pico, CMD_BUFFER_START, NULL, 0, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_end_current_buffering(Pico_t* pico){
  int rc = pico_send_frame(pico, CMD_BUFFER_STOP, NULL, 0, 500);
  if (rc) return message_wrap_error(rc);
  return message_wrap_int(1);
}

Message_t* pico_query_current_buffer(Pico_t* pico, uint8_t channel){
  // Pull 10-float chunks repeatedly from channel ch_idx
  uint8_t ch = channel - pico->channel_offset;
  const unsigned int count = 10;
  const unsigned int bigcount = 800;

  MessageBlock_t* block = block_construct('F', count*bigcount);
  if (!block) return message_wrap_error(-5);

  struct timespec start, end;
  clock_gettime(CLOCK_MONOTONIC, &start);

  for (unsigned int ic = 0; ic < bigcount; ic++){
    float buf[count];
    int rc = pico_query_frame(pico, CMD_GET_BUFFER_CHUNK, &ch, 1, buf, sizeof(buf), 50, 500);
    if (rc) {
      // you might prefer to break and return partial data
      block_destroy(block);
      return message_wrap_error(rc);
    }
    for (unsigned int i = 0; i < count; i++) {
      block_insert(block, &buf[i]);
    }
  }

  clock_gettime(CLOCK_MONOTONIC, &end);
  double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
  printf("Elapsed time: %.9f seconds\n", elapsed);

  Message_t* rv = message_initialize();
  message_append(rv, block);
  return rv;
}

// ---- Processing loop remains the same (no changes needed) ----
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
    QueueItem_t* item = queue_pop(queue);
    task_t* task = (task_t*) (item->payload);
    sprintf(msg, "pico %d received command label %u", pico->id, task->command.name);
    log_write(logger, msg, LOG_VERBOSE);

    Message_t* rv = NULL;

    // (dispatch table unchanged; all callees updated)
    if (task->command.name == COMMAND_get_vhvs){
      rv = pico_get_vhvs(pico);
    } else if (task->command.name == COMMAND_get_ihvs){
      rv = pico_get_ihvs(pico);
    } else if (task->command.name == COMMAND_get_vhv){
      rv = pico_get_vhv(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_get_ihv){
      rv = pico_get_ihv(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_enable_trip){
      rv = pico_enable_trip(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_disable_trip){
      rv = pico_disable_trip(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_reset_trip){
      rv = pico_reset_trip(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_force_trip){
      rv = pico_force_trip(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_program_trip_threshold){
      rv = pico_program_trip_threshold(pico, task->command.char_parameter, task->command.float_parameter);
    } else if (task->command.name == COMMAND_program_trip_count){
      rv = pico_program_trip_count(pico, task->command.char_parameter, task->command.float_parameter);
    } else if (task->command.name == COMMAND_query_trip_enabled){
      rv = pico_query_trip_enabled(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_query_trip_status){
      rv = pico_query_trip_status(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_query_trip_currents){
      rv = pico_query_trip_currents(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_query_current){
      rv = pico_query_current(pico);
    } else if (task->command.name == COMMAND_query_pcb_temperature){
      rv = pico_query_pcb_temperature(pico);
    } else if (task->command.name == COMMAND_get_slow_read){
      rv = pico_get_slow_read(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_get_buffer_status){
      rv = pico_get_buffer_status(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_enable_pedestal){
      rv = pico_enable_pedestal(pico);
    } else if (task->command.name == COMMAND_disable_pedestal){
      rv = pico_disable_pedestal(pico);
    } else if (task->command.name == COMMAND_update_pedestal){
      rv = pico_update_pedestal(pico, task->command.char_parameter);
    } else if (task->command.name == COMMAND_begin_current_buffering){
      rv = pico_begin_current_buffering(pico);
    } else if (task->command.name == COMMAND_end_current_buffering){
      rv = pico_end_current_buffering(pico);
    } else if (task->command.name == COMMAND_query_current_buffer){
      rv = pico_query_current_buffer(pico, task->command.char_parameter);
    } else {
      sprintf(msg, "pico %d encountered command of unknown label %u. skipping.", pico->id, task->command.name);
      log_write(logger, msg, LOG_INFO);
    }

    pthread_mutex_lock(&(task->mutex));
    task->rv = rv;
    task->complete = 1;
    pthread_mutex_unlock(&(task->mutex));
    pthread_cond_signal(&(task->condition));
  }
}
