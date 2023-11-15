#include "utils.h"

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


void write_fixed_location(const char *filename, long position, int value)
{
  if (value != 0 && value != 1)
  {
    printf("Invalid value. Only 0 or 1 allowed.\n");
    return;
  }

  FILE *file = fopen(filename, "r+");
  if (file == NULL)
  {
    perror("Error opening file");
    return;
  }

  fseek(file, position, SEEK_SET);
  fprintf(file, "%d ", value);

  fclose(file);
}
