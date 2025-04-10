// Ed Callaghan
// Level-based logging with optional fork to stdout
// October 2024

#include "Logging.h"

void log_init(Logger_t* logger, char* path,
              unsigned int print_limit, int print){
  logger->path = NULL;
  if (path != NULL){
    logger->path = malloc(strlen(path));
    sprintf(logger->path, "%s", path);
    logger->fd = open(logger->path,
                      O_WRONLY | O_CREAT | O_APPEND,
                      S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH);
  }
  logger->print_limit = print_limit;
  logger->print = print;
  pthread_mutex_init(&(logger->mutex), NULL);
}

void log_destroy(Logger_t* logger){
  if (log_valid(logger)){
    free(logger->path);
    logger->path = NULL;
    close(logger->fd);
  }
  pthread_mutex_destroy(&(logger->mutex));
}

int log_valid(Logger_t* logger){
  if (logger->path == NULL){
    return 0;
  }
  return 1;
}

void log_write(Logger_t* logger, char* msg, unsigned int level){
  pthread_mutex_lock(&(logger->mutex));

  time_t now;
  time(&now);
  char* stime = malloc(32);
  ctime_r(&now, stime);
  size_t len = strlen(stime);
  if (0 < len){
    stime[strlen(stime) - 1] = '\0';
  }

  // assume no more than two-digit log levels, plus " ( ): \n" separators
  // time (level): msg
  char* formatted = malloc(strlen(stime) + 2 + strlen(msg) + 7);
  sprintf(formatted, "%s (%u): %s\n", stime, level, msg);
  free(stime);

  if (log_valid(logger)){
    write(logger->fd, formatted, strlen(formatted));
  }
  if ((logger->print) && (level <= logger->print_limit)){
    printf("%s", formatted);
  }
  free(formatted);

  pthread_mutex_unlock(&(logger->mutex));
}
