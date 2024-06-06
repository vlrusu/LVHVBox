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
#include "dac8164.h"
#include "gpio.h"
#include "i2cbusses.h"
#include "MCP23S08.h"
#include "connections.h"
#include "utils.h"
#include "Logging.h"
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

int initialize_i2c_lv(uint8_t channel_map[6]);
int initialize_i2c_hv();
int initialize_i2c(uint8_t lv_channel_map[6]);
float i2c_ltc2497(int, int);

float i2c_read_low(uint8_t, uint8_t, float);
float i2c_read_6V_voltage(unsigned int);
float i2c_read_6V_current(unsigned int);
float i2c_read_48V_voltage(unsigned int);
float i2c_read_48V_current(unsigned int);
int i2c_lv_power_control(uint8_t channel, uint8_t pin_map[6], int value);
int i2c_lv_power_on(uint8_t, uint8_t[6]);
int i2c_lv_power_off(uint8_t, uint8_t[6]);
float i2c_deferred_hv_query(int, uint8_t);
float i2c_ramp_hv(int, uint8_t, float);

typedef struct {
  PriorityQueue_t* queue;
  uint8_t channel_map[6];
  Logger_t* logger;
  unsigned int port;
} i2c_loop_args_t;

void* i2c_loop(void*);

#endif
