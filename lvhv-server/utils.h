#ifndef UTILS_H
#define UTILS_H

#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

# define COMMAND_LENGTH 10000

int msleep(long msec);
int write_fixed_location(const char *filename, long position, int value);
int error_log(const char *data);


// ejc
void exit_on_error(char* msg);

#endif
