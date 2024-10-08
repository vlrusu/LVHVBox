// Ed Callaghan
// Level-based logging with optional fork to stdout
// October 2024

#ifndef LOGGING_H
#define LOGGING_H

#define LOG_INFO 2
#define LOG_DETAIL 4
#define LOG_VERBOSE 6

#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

// TODO this should contain a queue, so that writes into the log
// are decoupled from io latency
typedef struct {
  char* path;
  int fd;
  unsigned int print_limit;
  int print;
  pthread_mutex_t mutex;
} Logger_t;

void log_init(Logger_t*, char*, unsigned int, int);
void log_destroy(Logger_t*);
int log_valid(Logger_t*);
void log_write(Logger_t*, char*, unsigned int);

#endif
