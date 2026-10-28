#include "utils.h"
#include <string.h>

int msleep(long msec)
{
    struct timespec ts;
    int res;

    if (msec < 0)
    {
        errno = EINVAL;
        return -1;
    }

    ts.tv_sec = msec / 1000;
    ts.tv_nsec = (msec % 1000) * 1000000;

    do {
        res = nanosleep(&ts, &ts);
    } while (res && errno == EINTR);

    return res;
}

int write_fixed_location(const char *filename, long position, int value) {
  char error_msg[100];

  if (value != 0 && value != 1) {
    sprintf(error_msg, "write_fixed_location: Invalid value of %i. Only 0 or 1 allowed.", value);
    error_log(error_msg);
    printf(error_msg);

    return -1;
  }

  FILE *file = fopen(filename, "r+");
  if (file == NULL) {
    error_log("write_fixed_location: Error opening file");
    printf("write_fixed_location: Error opening file");
    return -1;
  }

  fseek(file, position, SEEK_SET);
  fprintf(file, "%d ", value);

  fclose(file);

  return 0;
}

int error_log(const char *data) {

  char *error_log = "/var/log/lvhv/errors.log";

  FILE *fp = fopen(error_log, "a");
  if (fp == NULL) {
    printf("Error_0 logging error\n");
    return -1;
  }
  if (fprintf(fp, data) < 0) {
    printf("Error_1 logging error\n");
    fclose(fp);
    return -1;
  } else if (fprintf(fp, " %lu \n", (unsigned long)time(NULL)) < 0) {
    printf("Error_2 logging error\n");
    fclose(fp);
    return -1;
  }

  fclose(fp);

  return 0;
}

// ejc
void exit_on_error(char* msg){
//fprintf(stderr, msg);
  perror(msg);
  exit(EXIT_FAILURE);
}
