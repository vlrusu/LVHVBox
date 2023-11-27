#ifndef UTILS_H
#define UTILS_H

#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

typedef struct
{
  char command_name;
  char command_type;
  uint8_t char_parameter;
  float float_parameter;
  int client_addr;
} command;

# define COMMAND_LENGTH 100

int msleep(long msec);
int write_fixed_location(const char *filename, long position, int value);


#endif