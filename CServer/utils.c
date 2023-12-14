#include "utils.h"

const char* CONFIG_PATH = "../../config.txt";
const int CONFIG_READ_LENGTH = 200;

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

char* extract_value(char* input_string) {
  int reached_colon = 0;
  int start_char = 0;

  for (int index = 0; index<strlen(input_string); index++) {
    if (input_string[index] == ':') {
      start_char = index;
    }
  }
  start_char += 0;
  
  /*
  char* output_string = malloc(strlen(input_string) - start_char-2);
  strncpy(output_string, &input_string[start_char+1], strlen(input_string)-start_char-2);

  printf("length: %i\n", strlen(input_string) - start_char);

  printf("return string: %s\n",output_string);
  */


  /*
  char* output_string = malloc(50);
  for (int i=0; i<strlen(input_string)-start_char - 2; i++) {
    output_string[i] = input_string[1 + i + start_char];
  }
  */
 char* output_string = malloc(CONFIG_READ_LENGTH);
 strcpy(output_string, &input_string[start_char+1]);





  return &output_string[0];

}

char* extract_name(char* input_string) {


  int reached_colon = 0;
  int start_char = 0;

  for (int index = 0; index<strlen(input_string); index++) {
    if (input_string[index] == ':') {
      start_char = index;
    }
  }
  start_char += 1;


  char* output_string = malloc(CONFIG_READ_LENGTH);
  
  strncpy(output_string, input_string, start_char-1);


  return output_string;
}


char* load_config(char* constant_name) {

  FILE* ptr;
  char ch;

  // Opening file in reading mode
  ptr = fopen(CONFIG_PATH, "r+");
  if (NULL == ptr) {
      printf("file can't be opened \n");
  }


  char current_line[200];
  char *tentative_value;
  char *tentative_name;
  
  int correct_line = 0;

  
  while (correct_line == 0) {
    
    fgets(current_line, CONFIG_READ_LENGTH, ptr);

    tentative_value = extract_value(current_line);
    tentative_name = extract_name(current_line);
    
    if (strcmp(tentative_name, constant_name) == 0) {
      correct_line = 1;
    }
  }
  

  

  int close_stat = fclose(ptr);
  
  return tentative_value;
}


int write_fixed_location(const char *filename, long position, int value) {
  if (value != 0 && value != 1)
  {
    perror("write_fixed_location: Invalid value. Only 0 or 1 allowed.\n");
    return -1;
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

int error_log(const char *data) {
  char *error_log = load_config("Error_Log_File");
  printf("Error log: %s\n",error_log);

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

int write_log(char *filename, const char *data, int datatype) {
  FILE *fp = fopen(filename, "a");
  if (fp == NULL) {
    printf("Error logging datatype %i\n", datatype);
    return -1;
  }

  if (fprintf(fp, data) < 0) {
    printf("Error writing logfile, datatype %i\n", datatype);
    fclose(fp);
    return -1;
  } else if (fprintf(fp, " %lu", (unsigned long)time(NULL)) < 0) {
    printf("Error writing logfile, datatype %i\n", datatype);
    fclose(fp);
    return -1;
  } else if (fprintf(fp, " %i\n", datatype) < 0) {
    printf("Error writing logfile, datatype %i\n", datatype);
    fclose(fp);
    return -1;
  }

  fclose(fp);

  return 0;
}







