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
#include "ConfigurationStore.h"
#include "Logging.h"
#include "PriorityQueue.h"
#include "Pico.h"
#include "i2c_routines.h"
#include "spi_routines.h"
#include "pico_routines.h"

// i2c globals
extern uint8_t lv_mcp_reset;
extern uint8_t lv_global_enable;
extern MCP* lvpgoodMCP;
extern MCP* hvMCP;

int main(int argc, char* argv[]){
  int rv;
  unsigned int port = 12000;
  int backlog = 3;
  char* lpath = NULL;
  char* cpath = NULL;
  int c;
  int stop = 0;
  while ((!stop) && ((c = getopt(argc, argv, "p:b:l:c:")) != -1)){
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
      case 'c':
        cpath = optarg;
        break;
      default:
        sprintf(msg, "impossible parsing state");
        exit_on_error(msg);
        break;
    }
  }

  Logger_t logger;
  log_init(&logger, lpath, 10, 1);

  // initialize configuration table
  char msg[] = "initializing configuration table";
  log_write(&logger, (char*) &msg, LOG_INFO);
  ConfigurationStore_t* config = malloc(sizeof(ConfigurationStore_t));
  config_init(config);
  if (access(cpath, R_OK) == 0){
	  config_load_from(config, cpath);
  }
  else{
    char* m = (char*) malloc(1024);
    sprintf(m, "warning: no readable config at %s", cpath);
    log_write(&logger, m, LOG_INFO);
    free(m);
  }

  // initialize spi driver interface
  log_write(&logger, "initializing spi interface", LOG_DETAIL);
  rv = initialize_spi();
  if (rv != 0){
    log_write(&logger, "failed to initialize spi interface", LOG_INFO);
    return rv;
  }

  // initialize gpio pins and adcs
  // TODO read from config (including globals initialized in i2c_routines)
  log_write(&logger, "initializing MCP pins for i2c interface", LOG_DETAIL);
  lv_mcp_reset = 3;
  lv_global_enable = 18;
  lvpgoodMCP = (MCP*) malloc(sizeof(struct MCP*));
  uint8_t channel_map [6] = {4, 3, 2, 7, 6, 5};
  hvMCP = (MCP*) malloc(sizeof(struct MCP*));
  rv = initialize_i2c(channel_map);
  if (rv != 0){
    log_write(&logger, "failed to initialize i2c interface", LOG_INFO);
    return rv;
  }

  // initialize usb interface and pico handles
  log_write(&logger, "initializing libusb and raspberri pico connections", LOG_DETAIL);
  if (libusb_init(NULL) != 0){
    char msg[64];
    sprintf(msg, "failed to initialize libusb context");
    log_write(&logger, msg, LOG_INFO);
    exit_on_error(msg);
  }
  libusb_set_option(NULL, LIBUSB_OPTION_LOG_LEVEL, LIBUSB_LOG_LEVEL_WARNING);
  Pico_t pico_a;
  pico_init(&pico_a, PICO_VENDOR_ID_0, 0, 0);
  Pico_t pico_b;
  pico_init(&pico_b, PICO_VENDOR_ID_1, 1, 6);

  // define queues
  PriorityQueue_t i2c_queue;
  queue_init(&i2c_queue, 1024);
  PriorityQueue_t pico_a_queue;
  queue_init(&pico_a_queue, 1024);
  PriorityQueue_t pico_b_queue;
  queue_init(&pico_b_queue, 1024);

  // start i2c loop
  i2c_loop_args_t i2c_loop_args;
  i2c_loop_args.queue = &i2c_queue;
  i2c_loop_args.logger = &logger;
  i2c_loop_args.port = port;
  memcpy(i2c_loop_args.channel_map, channel_map, sizeof(i2c_loop_args.channel_map));
  pthread_t i2c_thread;

  // start pico loops
  if (pico_a.handle != NULL){
    pico_loop_args_t pico_a_loop_args;
    pico_a_loop_args.pico = &pico_a;
    pico_a_loop_args.queue = &pico_a_queue;
    pico_a_loop_args.logger = &logger;
    pthread_t pico_a_thread;
    pthread_create(&pico_a_thread, NULL, pico_loop, &pico_a_loop_args);
  }
  if (pico_b.handle != NULL){
    pico_loop_args_t pico_b_loop_args;
    pico_b_loop_args.pico = &pico_b;
    pico_b_loop_args.queue = &pico_b_queue;
    pico_b_loop_args.logger = &logger;
    pthread_t pico_b_thread;
    pthread_create(&pico_b_thread, NULL, pico_loop, &pico_b_loop_args);
  }

  // start server
  int sfd = open_server(port, backlog);
  foyer_args_t foyer_args;
  foyer_args.fd = sfd;
  foyer_args.i2c_queue = &i2c_queue;
  foyer_args.pico_a_queue = &pico_a_queue;
  foyer_args.pico_b_queue = &pico_b_queue;
  foyer_args.logger = &logger;
  pthread_t foyer_thread;
  pthread_create(&foyer_thread, NULL, foyer, &foyer_args);

  pthread_create(&i2c_thread, NULL, i2c_loop, &i2c_loop_args);

  // wait forever
  pthread_join(foyer_thread, NULL);

  // clean up
  libusb_exit(NULL);
  log_destroy(&logger);

  return 0;
}
