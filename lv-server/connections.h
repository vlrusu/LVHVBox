// Ed Callaghan
// Internals of e.g. socket connections
// September 2024

#ifndef CONNECTIONS_H
#define CONNECTIONS_H

#include <sys/socket.h>
#include <sys/types.h>
#include <netinet/in.h>
#include <stddef.h>

#include "handler.h"

int open_server(unsigned int, int);
void* foyer(void*);

#endif
