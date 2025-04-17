// Ed Callaghan
// Command interface
// September 2024

#ifndef COMMAND_H
#define COMMAND_H

#include <inttypes.h>

typedef struct {
  uint32_t name;
  uint32_t type;
  uint8_t char_parameter;
  float float_parameter;
} command_t;

#endif
