#ifndef UTILS_H
#define UTILS_H

#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int msleep(long msec);
void write_fixed_location(const char *filename, long position, int value);

#endif