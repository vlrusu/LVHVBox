#include "utils.h"

const char* CONFIG_PATH = "../../config.txt";

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

char* load_config(char* constant_name) {

  FILE* ptr;
  char ch;

  // Opening file in reading mode
  ptr = fopen(CONFIG_PATH, "r");

  if (NULL == ptr) {
      printf("file can't be opened \n");
  }

  char return_string[100];
  int location = 0;
  char temp_char;
  int after_colon = 0;

  // check for end of line
  while (temp_char != ';') {
    temp_char = fgetc(ptr);

    if (after_colon == 1 && temp_char != ';') {
      //printf("temp char: %c\n",temp_char);
      return_string[location] = temp_char;
      location += 1;
    }

    if (temp_char == ':') {
      after_colon = 1;
    }

  }
  fclose(ptr);

  // populate return_val
  char* return_val = malloc(location);


  char* dest = malloc(location);
  
  memset(dest, '\0', sizeof(dest));
  strncpy(dest, return_string, location);

  return dest;
}
