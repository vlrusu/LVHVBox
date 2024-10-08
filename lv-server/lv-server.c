// Ed Callaghan
// Spin-off server strictly mediating LV control / queries via i2c
// September 2024

#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <linux/spi/spidev.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stddef.h>
#include <sys/ioctl.h>
#include <sys/msg.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>

// home-rolled
#include "../commands.h"
#include "connections.h"
#include "handler.h"
#include "i2cbusses.h"
#include "gpio.h"
#include "utils.h"
#include "Logging.h"
#include "PriorityQueue.h"
#include "i2c_routines.h"
#include "spi_routines.h"

// i2c globals
extern uint8_t lv_mcp_reset;
extern uint8_t lv_global_enable;
extern MCP* lvpgoodMCP;

int main(int argc, char** argv){
  int rv;
  unsigned int port = 12000;
  int backlog = 3;
  char* lpath = NULL;
  char c;
  int stop = 0;
  while ((!stop) && ((c = getopt(argc, argv, "p:b:l:")) != -1)){
    char msg[256];
    switch(c){
      case 'p':
        sscanf(optarg, "%h", port);
        break;
      case 'b':
        sscanf(optarg, "%h", backlog);
        break;
      case '?':
        sprintf(msg, "unsupported command-line option (-%c)", c);
        exit_on_error(msg);
        break;
      case 'l':
        lpath = optarg;
        break;
      case 255:
        stop = 1;
        break;
      default:
        sprintf(msg, "impossible parsing state");
        exit_on_error(msg);
        break;
    }
  }

  Logger_t logger;
  log_init(&logger, lpath, 10, 1);

  // initialize spi driver interface
  rv = initialize_spi();
  if (rv != 0){
    return rv;
  }

  // initialize gpio pins and adcs
  // TODO read from config (including globals initialized in i2c_routines)
  lv_mcp_reset = 3;
  lv_global_enable = 18;
  lvpgoodMCP = (MCP*) malloc(sizeof(struct MCP*));
  uint8_t channel_map [6] = {4, 3, 2, 7, 6, 5};
  rv = initialize_i2c(channel_map);
  if (rv != 0){
    return rv;
  }

  // define queue
  PriorityQueue_t queue;
  queue_init(&queue, 1024);

  // start i2c loop
  i2c_loop_args_t i2c_loop_args;
  i2c_loop_args.queue = &queue;
  i2c_loop_args.logger = &logger;
  memcpy(i2c_loop_args.channel_map, channel_map, sizeof(i2c_loop_args.channel_map));
  pthread_t i2c_thread;
  pthread_create(&i2c_thread, NULL, i2c_loop, &i2c_loop_args);

  // start server
  int sfd = open_server(port, backlog);
  foyer_args_t foyer_args;
  foyer_args.fd = sfd;
  foyer_args.queue = &queue;
  foyer_args.logger = &logger;
  pthread_t foyer_thread;
  pthread_create(&foyer_thread, NULL, foyer, &foyer_args);

  // wait forever
  pthread_join(foyer_thread, NULL);

  // clean up logging
  log_destroy(&logger);

  return 0;
}
