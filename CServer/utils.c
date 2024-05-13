#include "utils.h"

#include <string.h>

const char* CONFIG_PATH = "../../config.txt";
const int CONFIG_READ_LENGTH = 200;

int msleep(long msec) {
  struct timespec ts;
  int res;

  if (msec < 0) {
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

  for (int index = 0; index < strlen(input_string); index++) {
    if (input_string[index] == ':') {
      start_char = index;
    }
  }
  start_char += 0;

  char* output_string = malloc(CONFIG_READ_LENGTH);
  strcpy(output_string, &input_string[start_char + 1]);

  return &output_string[0];
}

char* extract_name(char* input_string) {
  int reached_colon = 0;
  int start_char = 0;

  for (int index = 0; index < strlen(input_string); index++) {
    if (input_string[index] == ':') {
      start_char = index;
    }
  }
  start_char += 1;

  char* output_string = malloc(CONFIG_READ_LENGTH);

  strncpy(output_string, input_string, start_char - 1);

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
  char* tentative_value;
  char* tentative_name;

  int correct_line = 0;

  while (correct_line == 0) {
    fgets(current_line, CONFIG_READ_LENGTH, ptr);

    if (current_line[0] != '\n') {
      if (current_line[0] != '/' && current_line[1] != '/') {
        tentative_value = extract_value(current_line);
        tentative_name = extract_name(current_line);

        if (strcmp(tentative_name, constant_name) == 0) {
          correct_line = 1;
        }
      }
    }
  }

  int close_stat = fclose(ptr);

  return tentative_value;
}

int write_fixed_location(const char* filename, long position, int value) {
  char error_msg[100];

  if (value != 0 && value != 1) {
    sprintf(error_msg,
            "write_fixed_location: Invalid value of %i. Only 0 or 1 allowed.",
            value);
    error_log(error_msg);
    printf(error_msg);

    return -1;
  }

  FILE* file = fopen(filename, "r+");
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

int error_log(const char* data) {
  /*
  char *error_log = load_config("Error_Log_File");
  printf("Error log: %s\n",error_log);
  */
  char* error_log = "../../Logs/error_log.log";

  FILE* fp = fopen(error_log, "a");
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

int write_log(char* filename, const char* data, int client_addr) {
  char error_msg[100];

  struct tm ts;
  time_t now;
  char date_buffer[80];
  time(&now);
  ts = *localtime(&now);
  strftime(date_buffer, sizeof(date_buffer), "%a %Y-%m-%d %H:%M:%S", &ts);

  char* file_string = "../../Logs/command_log.log";
  FILE* fp = fopen(file_string, "a");
  if (fp == NULL) {
    sprintf(error_msg, "Logging Error");
    error_log(error_msg);
    printf(error_msg);
    return -1;
  }

  if (fprintf(fp, "%lu ", (unsigned long)time(NULL)) < 0) {
    sprintf(error_msg, "Error writing logfile");
    error_log(error_msg);
    printf(error_msg);

    fclose(fp);
    return -1;
  } else if (fprintf(fp, "%s ", date_buffer) < 0) {
    ;
  } else if (fprintf(fp, data) < 0) {
    sprintf(error_msg, "Error writing logfile");
    error_log(error_msg);
    printf(error_msg);

    fclose(fp);
    return -1;
  } else if (fprintf(fp, " Client #%i\n", client_addr) < 0) {
    sprintf(error_msg, "Error writing logfile");
    error_log(error_msg);
    printf(error_msg);

    fclose(fp);
    return -1;
  }

  fclose(fp);

  return 0;
}
