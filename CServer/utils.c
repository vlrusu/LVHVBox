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


int write_fixed_location(const char *filename, long position, int value) {
  if (value != 0 && value != 1)
  {
    perror("write_fixed_location: Invalid value. Only 0 or 1 allowed.\n");
    return -1
  }

  FILE *file = fopen(filename, "r+");
  if (file == NULL)
  {
    perror("write_fixed_location: Error opening file");
    return -1;
  }

  fseek(file, position, SEEK_SET);
  fprintf(file, "%d ", value);

  fclose(file);

  return 0;
}





void enqueue(command array[COMMAND_LENGTH], command insert_item, int rear) {
    if (rear == COMMAND_LENGTH - 1)
       printf("Overflow \n");
    else
    {      
        rear = rear + 1;
        array[rear] = insert_item;
    }
} 
 
void dequeue(command array[COMMAND_LENGTH], int front, int rear) {
    if (front == - 1 || front > rear) {
        printf("Underflow \n");
        return ;
    } else {
      for (int i=0; i<COMMAND_LENGTH-1; i++) {
        array[i] = array[i+1];
      }
    }
    rear -= 1;
}


