// Ed Callaghan
// A simple string-to-message hash table, for storing configuration
// January 2024

#ifndef HASHTABLE_H
#define HASHTABLE_H

#include <stdlib.h>
#include <string.h>
#include "Messages.h"

typedef char* HTKey_t;
typedef MessageBlock_t* HTValue_t;

// within a bucket, entries are stored as a simple linked list
typedef struct HTEntry {
  HTKey_t key;
  HTValue_t value;
  struct HTEntry* next;
} HTEntry_t;

typedef struct {
  HTEntry_t* first;
  unsigned int count;
} HTBucket_t;

typedef struct {
  HTBucket_t* buckets;
  unsigned int size;
} HashTable_t;

unsigned int knuth_hash_function(char*);

int htkey_equal(HTKey_t, HTKey_t);

// table takes ownership of key/value pair, and is responsible for destruction
void htentry_init(HTEntry_t*, HTKey_t, HTValue_t);
void htentry_destroy(HTEntry_t*);

void htbucket_init(HTBucket_t*);
void htbucket_destroy(HTBucket_t*);
void htbucket_append(HTBucket_t*, HTEntry_t*);
HTValue_t htbucket_lookup(HTBucket_t*, HTKey_t);

void hashtable_init(HashTable_t*, unsigned int);
void hashtable_destroy(HashTable_t*);
unsigned int hashtable_hash(HashTable_t*, HTKey_t);
void hashtable_insert(HashTable_t*, HTKey_t, HTValue_t);
HTValue_t hashtable_lookup(HashTable_t*, HTKey_t);

#endif
