// Ed Callaghan
// Factoring out the ugliness related to to usb-control of the picos
// October 2024

#ifndef PICO_ROUTINES_H
#define PICO_ROUTINES_H

#include "../commands.h"
#include "utils.h"
#include "Logging.h"
#include "Messages.h"
#include "Pico.h"
#include "PriorityQueue.h"
#include "Task.h"

// override ambiguous legacy definitions
#define COMMAND_force_trip COMMAND_trip
#define COMMAND_query_trip_enabled COMMAND_trip_enabled
#define COMMAND_query_trip_status COMMAND_trip_status
#define COMMAND_query_current COMMAND_pico_current
#define COMMAND_query_pcb_temperature COMMAND_pcb_temp
#define COMMAND_get_buffer_status COMMAND_current_buffer_run
#define COMMAND_enable_pedestal COMMAND_enable_ped
#define COMMAND_disable_pedestal COMMAND_disable_ped
#define COMMAND_update_pedestal COMMAND_update_ped
#define COMMAND_begin_current_buffering COMMAND_current_start
#define COMMAND_end_current_buffering COMMAND_current_stop
#define COMMAND_query_current_buffer COMMAND_current_burst
#define COMMAND_program_trip_threshold COMMAND_set_trip
#define COMMAND_program_trip_count COMMAND_set_trip_count

typedef struct {
  PriorityQueue_t* queue;
  Pico_t* pico;
  Logger_t* logger;
} pico_loop_args_t;

void pico_write_low(Pico_t*, char*, size_t);
void pico_write_low_timeout(Pico_t*, char*, size_t, unsigned int, Logger_t*);
void pico_read_low(Pico_t*, char*, size_t);
void pico_read_low_timeout(Pico_t*, char*, size_t, unsigned int, Logger_t*);
void pico_write_read_low(Pico_t*, char*, size_t, char*, size_t);
void pico_write_read_low_timeout(Pico_t* pico, char*, size_t, unsigned int,
                                               char*, size_t, unsigned int, Logger_t*);
Message_t* pico_get_vhv(Pico_t*, uint8_t, Logger_t*);
Message_t* pico_get_ihv(Pico_t*, uint8_t);
Message_t* pico_enable_trip(Pico_t* ,uint8_t);
Message_t* pico_disable_trip(Pico_t*, uint8_t);
Message_t* pico_reset_trip(Pico_t*, uint8_t);
Message_t* pico_force_trip(Pico_t*, uint8_t);
Message_t* pico_program_trip_threshold(Pico_t*, uint8_t, float);
Message_t* pico_program_trip_count(Pico_t*, uint8_t, float);
Message_t* pico_query_trip_enabled_all(Pico_t*);
Message_t* pico_query_trip_enabled(Pico_t*, uint8_t);
Message_t* pico_query_trip_status_all(Pico_t*);
Message_t* pico_query_trip_status(Pico_t*, uint8_t);
Message_t* pico_query_current(Pico_t*);
Message_t* pico_query_pcb_temperature(Pico_t*);
Message_t* pico_get_slow_read(Pico_t*, uint8_t);
Message_t* pico_get_buffer_status(Pico_t*, uint8_t);
Message_t* pico_enable_pedestal(Pico_t*);
Message_t* pico_disable_pedestal(Pico_t*);
Message_t* pico_update_pedestal(Pico_t*, uint8_t);
Message_t* pico_begin_current_buffering(Pico_t*);
Message_t* pico_end_current_buffering(Pico_t*);
Message_t* pico_query_current_buffer(Pico_t*, uint8_t, Logger_t*);
void* pico_loop(void*);

#endif
