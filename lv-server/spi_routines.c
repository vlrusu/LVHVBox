// Ed Callaghan
// Factoring out some ugly details
// September 2024

#include "spi_routines.h"

// globals -.-
uint8_t spi_bpw = 8;           // bits per word
uint32_t spi_speed = 40000000; // 10MHz
uint16_t spi_delay = 0;
static const uint8_t spi_mode = 0;
int spiFds;
static const char* spidev = "/dev/spidev0.0"; //this is the SPI device. Assume here that there is only one SPI bus

int initialize_spi(){
  char error_msg[128];

  if ((spiFds = open (spidev, O_RDWR)) < 0){
    sprintf(error_msg, "Unable to open SPI device: %s", spidev);
    error_log(error_msg);
    printf(error_msg);

    return 0;
  }

  if (ioctl (spiFds, SPI_IOC_WR_MODE, &spi_mode) < 0){
    sprintf(error_msg, "SPI Mode Change failure: %s", spidev);
    error_log(error_msg);
    printf(error_msg);

    return 0;
  }

  if (ioctl (spiFds, SPI_IOC_WR_BITS_PER_WORD, &spi_bpw) < 0){
    sprintf(error_msg, "SPI BPW Change failure: %s", spidev);
    error_log(error_msg);
    printf(error_msg);

    return 0;
  }

  if (ioctl (spiFds, SPI_IOC_WR_MAX_SPEED_HZ, &spi_speed) < 0){
    sprintf(error_msg, "SPI Speed Change failure: %s", spidev);
    error_log(error_msg);
    printf(error_msg);

    return 0;
  }
}
