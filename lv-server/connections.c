// Ed Callaghan
// Internals of e.g. socket connections
// September 2024

#include "connections.h"

// initiate connection point
int open_server(unsigned int port, int backlog){
  // instantiate socket
  // FIXME last argument == ???
  int rv = socket(AF_INET, SOCK_STREAM, 0);
  if (rv < 0){
    char msg[128];
    sprintf(msg, "failed to instantiate inet socket");
    exit_on_error(msg);
  }

  // set socket options
  // FIXME == ???
  int opt = 1;
  if (setsockopt(rv, SOL_SOCKET, SO_REUSEADDR | SO_REUSEPORT,
                 &opt, sizeof(opt))){
    char msg[128];
    sprintf(msg, "failed to set socket options");
    exit_on_error(msg);
  }

  // claim port
  struct sockaddr_in address;
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = INADDR_ANY;
  address.sin_port = htons(port);
  if (bind(rv, (struct sockaddr*) &address, sizeof(address)) < 0){
    char msg[128];
    sprintf(msg, "failed to bind inet socket to port %h", port);
    exit_on_error(msg);
  }

  // begin accepting connections
  if (listen(rv, backlog) < 0){
    char msg[128];
    sprintf(msg, "failed to listen on port %h", port);
    exit_on_error(msg);
  }

  return rv;
}

// actively listen for connections
void* foyer(void* args){
  int* casted = (int*) args;
  int sfd = *casted;

  int cfd;
  struct sockaddr_in address;
  int addrlen = sizeof(address);

  while (1){
    cfd = accept(sfd, (struct sockaddr*) &address, (socklen_t*) &addrlen);
    if (cfd < 0){
      char msg[128];
      sprintf(msg, "bad client connection");
      exit_on_error(msg);
    }

    pthread_t thread;
    pthread_create(&thread, NULL, client_handler, &cfd);
  }
}
