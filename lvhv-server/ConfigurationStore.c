// Ed Callaghan
// A value lookup built using a classic hash table under the hood
// January 2025

#include "ConfigurationStore.h"

void config_init(ConfigurationStore_t* config){
  config->table = malloc(sizeof(HashTable_t));
  hashtable_init(config->table, 128);
}

void config_destroy(ConfigurationStore_t* config){
  hashtable_destroy(config->table);
}

HTValue_t config_lookup(ConfigurationStore_t* config, char* key){
  HTValue_t rv = hashtable_lookup(config->table, (HTKey_t) key);
  return rv;
}

char* config_lookup_string(ConfigurationStore_t* config, char* key){
  MessageBlock_t* block = config_lookup(config, key);
  if (block->type != 'C'){
    // error-out
  }
  char* rv = block->bytes;
  return rv;
}

int config_lookup_int(ConfigurationStore_t* config, char* key){
  MessageBlock_t* block = config_lookup(config, key);
  if (block->type != 'I'){
    // error-out
  }
  if (block->used != 1){
    // error-out
  }
  int* ptr;
  as_ints(block, &ptr);
  int rv = *ptr;
  return rv;
}

float config_lookup_float(ConfigurationStore_t* config, char* key){
  MessageBlock_t* block = config_lookup(config, key);
  if (block->type != 'F'){
    // error-out
  }
  if (block->used != 1){
    // error-out
  }
  float* ptr;
  as_floats(block, &ptr);
  float rv = *ptr;
  return rv;
}

void config_load_from(ConfigurationStore_t* config, char* path){
  int fd = open(path, O_RDONLY);

  char line[1024];
  while (read_line(fd, (char*) &line)){
    char* type = (char*) malloc(2);
    char* key = (char*) malloc(256);
    char* value = (char*) malloc(256);
    if (empty_line((char*) &line)){
      continue;
    }
    if (parse_config_line((char*) &line, type, key, value)){
      // wrap rhs value
      MessageBlock_t* block;
      if (strcmp(type, "C") == 0){
        unsigned int length = (unsigned int) strlen(value);
        block = block_construct('C', length);
        for (unsigned int i = 0 ; i < length ; i++){
          block_insert(block, value+i);
        }
      }
      else if (strcmp(type, "I") == 0){
        int casted = atoi(value);
        block = block_construct('I', 1);
        block_insert(block, &casted);
      }
      else if (strcmp(type, "U") == 0){
        unsigned int casted = (unsigned int) strtoul(value, NULL, 0);
        block = block_construct('U', 1);
        block_insert(block, &casted);
      }
      else if (strcmp(type, "F") == 0){
        float casted = atof(value);
        block = block_construct('F', 1);
        block_insert(block, &casted);
      }
      else if (strcmp(type, "D") == 0){
        unsigned int casted = (unsigned int) strtod(value, NULL);
        block = block_construct('D', 1);
        block_insert(block, &casted);
      }
      else{
        // error-out
      }

      hashtable_insert(config->table, (HTKey_t) key, (HTValue_t) block);
    }
    else{
      // error-out
    }
  }

  close(fd);
}

int read_line(int fd, char* out){
  char buff;
  unsigned int count = 0;
  do {
    ssize_t nread = read(fd, &buff, 1);
    if (nread == 1){
      sprintf(out+count, "%s", &buff);
      count++;
    }
    else{
      // error-out
      break;
    }
  } while (buff != '\n');
}

int empty_line(char* buff){
  while (*buff != '\n'){
    if (*buff == ' '){
      continue;
    }
    if (*buff == '\t'){
      continue;
    }
    return 0;
  }
  return 1;
}

int parse_config_line(char* buff, char* type, char* key, char* value){
  char typecode[32];
  int parsed = sscanf(buff, "%s %s = %s;\n\n", typecode, key, value);
  if (parsed != 3){
    return 0;
  }

  char* ptr = (char*) &typecode;
  if (strcmp(ptr, "string") == 0){
    *type = 'C';
  }
  else if (strcmp(ptr, "int") == 0){
    *type = 'I';
  }
  else if (strcmp(ptr, "uint") == 0){
    *type = 'U';
  }
  else if (strcmp(ptr, "float") == 0){
    *type = 'F';
  }
  else if (strcmp(ptr, "double") == 0){
    *type = 'D';
  }
  else{
    // error-out
  }
  *(type+1) = (char) 0;

  unsigned int length = (unsigned int) strlen(key);
  length = (unsigned int) strlen(key);
  if (strlen(key) < 1){
    // error-out
  }
  length = (unsigned int) strlen(value);
  if (length < 1){
    // error-out
  }
  if (value[length-1] != ';'){
    // error-out
  }
  value[length-1] = (char) 0;

  return 1;
}
