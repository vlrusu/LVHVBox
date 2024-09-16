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
#include "BinaryHeap.h"

// globals -.-
uint8_t spi_bpw = 8;           // bits per word
uint32_t spi_speed = 40000000; // 10MHz
uint16_t spi_delay = 0;
static const uint8_t spi_mode = 0;
int spiFds;

static const char* spidev = "/dev/spidev0.0"; //this is the SPI device. Assume here that there is only one SPI bus

int main(int argc, char** argv){
  unsigned int port = 12000;
  int backlog = 3;
  char c;
  int stop = 0;
  while ((!stop) && ((c = getopt(argc, argv, "p:b:")) != -1)){
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
      case 255:
        stop = 1;
        break;
      default:
        sprintf(msg, "impossible parsing state");
        exit_on_error(msg);
        break;
    }
  }

  int sfd = open_server(port, backlog);
  pthread_t foyer_thread;
  pthread_create(&foyer_thread, NULL, foyer, &sfd);

  pause();

  return 0;
}
