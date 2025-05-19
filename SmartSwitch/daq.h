// daq.h
#ifndef DAQ_H
#define DAQ_H

#include <stdint.h>
#include "hardware/pio.h"

void get_all_averaged_currents(PIO pio_a, PIO pio_b, PIO pio_c, uint sm[]);
void store_average_currents();

#endif // DAQ_H
