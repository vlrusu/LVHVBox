// Human-readable names for the command IDs defined by the wire protocol.
#include "Command.h"
#include "../commands.h"

const char* command_name(uint32_t name){
  switch (name){
    case COMMAND_pcb_temp: return "pcb_temp";
    case COMMAND_pico_current: return "pico_current";
    case COMMAND_current_burst: return "current_burst";
    case COMMAND_current_start: return "current_start";
    case COMMAND_current_stop: return "current_stop";
    case COMMAND_update_ped: return "update_ped";
    case COMMAND_current_buffer_run: return "current_buffer_run";
    case COMMAND_trip: return "trip";
    case COMMAND_reset_trip: return "reset_trip";
    case COMMAND_disable_trip: return "disable_trip";
    case COMMAND_enable_trip: return "enable_trip";
    case COMMAND_trip_status: return "trip_status";
    case COMMAND_trip_currents: return "trip_currents";
    case COMMAND_trip_enabled: return "trip_enabled";
    case COMMAND_set_trip: return "set_trip";
    case COMMAND_set_trip_count: return "set_trip_count";
    case COMMAND_enable_ped: return "enable_ped";
    case COMMAND_disable_ped: return "disable_ped";
    case COMMAND_start_usb: return "start_usb";
    case COMMAND_stop_usb: return "stop_usb";
    case COMMAND_get_slow_read: return "get_slow_read";
    case COMMAND_get_vhv: return "get_vhv";
    case COMMAND_get_ihv: return "get_ihv";
    case COMMAND_ramp_hv: return "ramp_hv";
    case COMMAND_set_hv_by_dac: return "set_hv_by_dac";
    case COMMAND_down_hv: return "down_hv";
    case COMMAND_powerOn: return "powerOn";
    case COMMAND_powerOff: return "powerOff";
    case COMMAND_readMonV48: return "readMonV48";
    case COMMAND_readMonI48: return "readMonI48";
    case COMMAND_readMonV6: return "readMonV6";
    case COMMAND_readMonI6: return "readMonI6";
    case COMMAND_query_hv_dac_cache: return "query_hv_dac_cache";
    case COMMAND_get_vhvs: return "get_vhvs";
    case COMMAND_get_ihvs: return "get_ihvs";
    default: return "unknown";
  }
}
