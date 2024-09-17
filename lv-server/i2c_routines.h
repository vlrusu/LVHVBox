// Ed Callaghan
// Factoring out some ugly details
// September 2024

#ifndef I2C_ROUTINES_H
#define I2C_ROUTINES_H

#include <i2c/smbus.h>
#include <inttypes.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <linux/spi/spidev.h>
#include <stdio.h>
#include "../commands.h"
#include "gpio.h"
#include "i2cbusses.h"
#include "MCP23S08.h"
#include "utils.h"
#include "PriorityQueue.h"
#include "Task.h"

/* for another day...
typedef struct {
  int i2c_bus;
  int i2c;
  uint8_t mcp_reset;
  uint8_t global_enable;
  uint8_t channel_map[6];
  MCP* mcp;
} i2c_config_t;
*/

int initialize_i2c(uint8_t channel_map[6]);
float i2c_ltc2497(int, int);

float i2c_read_low(uint8_t, uint8_t, float);
float i2c_read_6V_voltage(unsigned int);
float i2c_read_6V_current(unsigned int);
float i2c_read_48V_voltage(unsigned int);
float i2c_read_48V_current(unsigned int);

typedef struct {
  PriorityQueue_t* queue;
} i2c_loop_args_t;

void* i2c_loop(void*);

#endif
