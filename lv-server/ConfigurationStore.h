// Ed Callaghan
// A value lookup built using a classic hash table under the hood
// January 2025

#ifndef CONFIGURATIONSTORE_H
#define CONFIGURATIONSTORE_H

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include "HashTable.h"

typedef struct {
  HashTable_t* table;
} ConfigurationStore_t;

void config_init(ConfigurationStore_t*);
void config_destroy(ConfigurationStore_t*);
HTValue_t config_lookup(ConfigurationStore_t*, char*);
char* config_lookup_string(ConfigurationStore_t*, char*);
int config_lookup_int(ConfigurationStore_t*, char*);
float config_lookup_float(ConfigurationStore_t*, char*);
void config_load_from(ConfigurationStore_t*, char*);
int read_line(int, char*);
int empty_line(char*);
int parse_config_line(char*, char*, char*, char*);

#endif
