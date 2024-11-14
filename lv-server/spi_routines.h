// Ed Callaghan
// Factoring out some ugly details
// September 2024

#ifndef SPI_ROUTINES_H
#define SPI_ROUTINES_H

// unclear if these are used / necessary
#define SPISPEED 40000000
#define NSTEPS 200
#define SPICS 0

#include <fcntl.h>
#include <stdlib.h>
#include <linux/spi/spidev.h>
#include <sys/ioctl.h>
#include "utils.h"

int initialize_spi();

#endif
