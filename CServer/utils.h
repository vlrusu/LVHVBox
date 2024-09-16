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
  uint32_t command_name;
  uint32_t command_type;
  uint8_t char_parameter;
  float float_parameter;
  int client_addr;
} command;

# define COMMAND_LENGTH 10000

int msleep(long msec);
int write_fixed_location(const char *filename, long position, int value);
int write_log(char filename[], const char *data, int client_addr);
int error_log(const char *data);


char* load_config(char* constant_name);
char* extract_value(char* input_string);
char* extract_name(char* input_string);

// ejc
void exit_on_error(char* msg){

#endif
