// Ed Callaghan
// A simple string-to-message hash table, for storing configuration
// January 2024

#include "HashTable.h"

// from knuth's Art of Computer Programming
unsigned int knuth_hash_function(char* key){
  unsigned int size = strlen(key);
  unsigned int rv = size;
  for (unsigned int i = 0 ; i < size ; i++){
    rv = ((rv << 5) ^ (rv >> 27)) ^ (key[i]);
  }
  return rv;
}

int htkey_equal(HTKey_t lhs, HTKey_t rhs){
  if (strcmp((char*) lhs, (char*) rhs) == 0){
    return 1;
  }
  else{
    return 0;
  }
}

void htentry_init(HTEntry_t* entry, HTKey_t key, HTValue_t value){
  //entry = malloc(sizeof(HTEntry_t));
  entry->key = key;
  entry->value = value;
  entry->next = 0;
}

void htentry_destroy(HTEntry_t* entry){
  free(entry->key);
  block_destroy(entry->value);
  free(entry);
}

void htbucket_init(HTBucket_t* bucket){
  //bucket = malloc(sizeof(HTBucket_t));
  bucket->first = 0;
  bucket->count = 0;
}

void htbucket_destroy(HTBucket_t* bucket){
  HTEntry_t* entry = bucket->first;
  while (entry != 0){
    HTEntry_t* next = entry->next;
    htentry_destroy(entry);
    entry = next;
  }
  free(bucket);
}

void htbucket_append(HTBucket_t* bucket, HTEntry_t* entry){
  if (bucket->first == 0){
    bucket->first = entry;
  }
  else{
    HTEntry_t* current = bucket->first;
    while (current->next != 0){
      current = current->next;
    }
    current->next = entry;
  }
}

HTValue_t htbucket_lookup(HTBucket_t* bucket, HTKey_t key){
  HTValue_t rv;
  HTEntry_t* entry = bucket->first;
  while ((entry != 0) && (!htkey_equal(entry->key, key))){
    entry = entry->next;
  }
  if (entry == 0){
    rv = (HTValue_t) 0;
  }
  else{
    rv = entry->value;
  }
  return rv;
}

void hashtable_init(HashTable_t* table, unsigned int size){
  table->size = size;
  table->buckets = malloc(table->size * sizeof(HTBucket_t));
  for (unsigned int i = 0 ; i < table->size ; i++){
    htbucket_init(&table->buckets[i]);
  }
}

void hashtable_destroy(HashTable_t* table){
  for (unsigned int i = 0 ; i < table->size ; i++){
    htbucket_destroy(&table->buckets[i]);
  }
  free(table);
  table = 0;
}

unsigned int hashtable_hash(HashTable_t* table, HTKey_t key){
  unsigned int hash = knuth_hash_function((char*) key);
  unsigned int rv = hash % table->size;
  return rv;
}

void hashtable_insert(HashTable_t* table, HTKey_t key, HTValue_t value){
  HTEntry_t* entry = (HTEntry_t*) malloc(sizeof(HTEntry_t));
  htentry_init(entry, key, value);
  unsigned int idx = hashtable_hash(table, key);
  HTBucket_t* bucket = &table->buckets[idx];
  htbucket_append(bucket, entry);
}

HTValue_t hashtable_lookup(HashTable_t* table, HTKey_t key){
  unsigned int idx = hashtable_hash(table, key);
  HTBucket_t* bucket = &table->buckets[idx];
  HTValue_t rv = htbucket_lookup(bucket, key);
  return rv;
}
