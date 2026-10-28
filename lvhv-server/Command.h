// Ed Callaghan
// Command interface
// September 2024

#ifndef COMMAND_H
#define COMMAND_H

#include <inttypes.h>
#include "messaging/Protocol.h"

typedef struct {
  uint32_t name;
  uint32_t type;
  uint8_t char_parameter;
  float float_parameter;
} command_t;

// Return the protocol command name, or "unknown" for an unrecognized ID.
const char* command_name(uint32_t name);
// Validate command/subsystem, physical channel and numeric arguments before IO.
int command_is_valid(const command_t* command);

#endif
