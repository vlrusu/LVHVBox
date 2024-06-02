// Ed Callaghan
// Factoring out some ugly details
// September 2024

#include "i2c_routines.h"

// globals -.-
// lv
int lv_i2cbus;
int lv_i2c = 0;
uint8_t lv_mcp_reset;
uint8_t lv_global_enable;
MCP* lvpgoodMCP;
// hv
MCP* hvMCP;
DAC8164 hv_dacs[3];

int initialize_i2c_lv(uint8_t channel_map[6]){
  char error_msg[100];

  if (MCP_setup(lvpgoodMCP, 1) == -1) {
    error_log("main MCP_set lvpgoodMCP failure");
    printf("main MCP_set lvpgoodMCP failure");

    return -1;
  }

  if (setup_gpio(lv_mcp_reset) == -1) {
    error_log("main setup_gpio lv_mcp_reset failure");
    printf("main setup_gpio lv_mcp_reset failure");

    return 1;
  }

  // Turn off the GPIO pin (set it to 0)
  if (write_gpio_value(lv_mcp_reset, 0) == -1) {
    error_log("main write_gpio_value lv_mcp_reset failure");
    printf("main write_gpio_value lv_mcp_reset failure");
    
    return 1;
  }

  // Turn on the GPIO pin (set it to 1)
  if (write_gpio_value(lv_mcp_reset, 1) == -1) {
    error_log("main write_gpio_value lv_mcp_reset failure");
    printf("main write_gpio_value lv_mcp_reset failure");

    return 1;
  }

  if (setup_gpio(lv_global_enable) == -1) {
    error_log("lv_initialization setup_gpio lv_global_enable failure");
    printf("lv_initialization setup_gpio lv_global_enable failure");

    return -1;
  } else if (write_gpio_value(lv_global_enable, LOW) == -1) {
    error_log("lv_initialization write_gpio_value lv_global_enable failure");
    printf("lv_initialization write_gpio_value lv_global_enable failure");

    return -1;
  }

  for (int i=0; i<6; i++) {
    if (MCP_pinMode(lvpgoodMCP, channel_map[i], OUTPUT) == -1) {
      sprintf(error_msg, "lv_initialization MCP_pinMode pin %u failure", channel_map[i]);
      error_log(error_msg);
      printf(error_msg);

      return -1;
    }

    if (MCP_pinWrite(lvpgoodMCP, channel_map[i], OUTPUT) == -1) {
      sprintf(error_msg, "lv_initialization MCP_pinWrite pin %u failure", channel_map[i]);
      error_log(error_msg);
      printf(error_msg);

      return -1;
    }
  }

  int file;
  int i;
  int res;
  int oldvalue;

  char lv_i2cname[20];

  lv_i2cbus = lookup_i2c_bus("3");
  sprintf(lv_i2cname, "/dev/i2c-%d", 3);
  lv_i2c = open_i2c_dev(lv_i2cbus, lv_i2cname, sizeof(lv_i2cname), 0);


  if (lv_i2c < 0) { // return -1 in case of not acquiring file
    error_log("lv_initialization i2c file not acquired");
    printf("lv_initialization i2c file not acquired");

    return -1;
  }

 

  return 0;
}

int initialize_i2c_hv(){
  if (MCP_setup(hvMCP, 2) == -1) {
    error_log("main MCP_set hvMCP failure");
    printf("main MCP_set hvMCP failure");

    return -1;
  }

  if (MCP_pinMode(hvMCP, 4, OUTPUT) == -1) {
    error_log("hv_initialization MCP_pinMode pin 4 failure");
    printf("hv_initialization MCP_pinMode pin 4 failure");

    return -1;
  } else if (MCP_pinWrite(hvMCP, 4, LOW) == -1) {
    error_log("hv_initialization MCP_pinWrite pin 4 failure");
    printf("hv_initialization MCP_pinWrite pin 4 failure");

    return -1;
  } else if (MCP_pinMode(hvMCP, 2, OUTPUT) == -1) {
    error_log("hv_initialization MCP_pinMode pin 2 failure");
    printf("hv_initialization MCP_pinMode pin 2 failure");

    return -1;
  } else if (MCP_pinWrite(hvMCP, 2, LOW) == -1) {
    error_log("hv_initialization MCP_pinWrite pin 2 failure");
    printf("hv_initialization MCP_pinWrite pin 2 failure");

    return -1;
  } else if (DAC8164_setup (&hv_dacs[0], hvMCP, 6, 7, 0, -1, -1) == -1) {
    error_log("hv_initialization DAC8164_setup dac0 failure");
    printf("hv_initialization DAC8164_setup dac0 failure");

    return -1;
  } else if (DAC8164_setup (&hv_dacs[1], hvMCP, 3, 7, 0, -1, -1) == -1) {
    error_log("hv_initialization DAC8164_setup dac1 failure");
    printf("hv_initialization DAC8164_setup dac1 failure");

    return -1;
  } else if (DAC8164_setup (&hv_dacs[2], hvMCP, 5, 7, 0, -1, -1) == -1) {
    error_log("hv_initialization DAC8164_setup dac2 failure");
    printf("hv_initialization DAC8164_setup dac2 failure");

    return -1;
  }

  return 0;
}

int initialize_i2c(uint8_t lv_channel_map[6]){
  int rv = 0;
  rv += initialize_i2c_lv(lv_channel_map);
  rv += initialize_i2c_hv();
  return rv;
}

float i2c_ltc2497(int address, int channelLTC) {
  float max_reading = 8388608.0;
  float vref = 1.24;

  unsigned char block[I2C_SMBUS_BLOCK_MAX];

  set_slave_addr(lv_i2c, address, 1);

  msleep(200);

  //----- WRITE BYTES -----
  block[0] = channelLTC;
  int length = 1;                             //<<< Number of bytes to write
  if (write(lv_i2c, block, length) != length) // write() returns the number of bytes actually written, if it doesn't match then an error occurred (e.g. no response from the device)
  {
    /* ERROR HANDLING: i2c transaction failed */

    error_log("Failed to write to the i2c bus");
    printf("Failed to write to the i2c bus");

    return -1;
  }

  msleep(200);

  //----- READ BYTES -----
  length = 3;                                //<<< Number of bytes to read
  if (read(lv_i2c, block, length) != length) // read() returns the number of bytes actually read, if it doesn't match then an error occurred (e.g. no response from the device)
  {
    // ERROR HANDLING: i2c transaction failed

    error_log("Failed to read from the i2c bus");
    printf("Failed to read from the i2c bus");

    return -1;
  }

  int val;
  if ((block[0] & 0x80)) {
    val = (int) (((block[0] & 0x3f) << 16) + (block[1] << 8) + (block[2] & 0xE0));
  } else {
    val = (int) (((~block[0] & 0x3f) << 16) + (~block[1] << 8) + (~block[2] & 0xE0));
  }

  

  return val * vref / max_reading;
}

float i2c_read_low(uint8_t address, uint8_t channel, float scale){
  float acplscale = 8.2;
  float rv = i2c_ltc2497(address, channel);
  rv /= scale * acplscale;
  return rv;
}

float i2c_read_6V_voltage(unsigned int channel_number){
  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t map[6] = {4, 3, 4, 3, 4, 3};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float scale = 0.00857905;
  float rv = i2c_read_low(address, channel, scale);
  return rv;
}

float i2c_read_6V_current(unsigned int channel_number){
  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t map[6] = {5, 2, 5, 2, 5, 2};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float scale = 0.010;
  float rv = i2c_read_low(address, channel, scale);
  return rv;
}

float i2c_read_48V_voltage(unsigned int channel_number){
  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t map[6] = {6, 0, 6, 0, 6, 0};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float scale = 0.0012089;
  float rv = i2c_read_low(address, channel, scale);
  return rv;
}

float i2c_read_48V_current(unsigned int channel_number){
  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t map[6] = {7, 1, 7, 1, 7, 1};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float scale = 0.010;
  float rv = i2c_read_low(address, channel, scale);
  return rv;
}

int i2c_lv_power_control(uint8_t channel, uint8_t pin_map[6], int value){
  if ((channel < 0 ) || (6 < channel)){
    return 0;
  }

  if ((value == HIGH) || (channel == 6)){
    if (write_gpio_value(lv_global_enable, value) == -1){
      //error_log("poweron error 0");
      //return -1;
    }
  }

  if (channel == 6){
    for (int i = 0; i < 6; i++){
      if (MCP_pinWrite(lvpgoodMCP, pin_map[i], value) == -1){
        char error_msg[50];
        sprintf(error_msg, "mcp powerOn fail write channel %i", i);
        //error_log(error_msg);
        //return -1;
      }

    }
  }
  else{
    if (MCP_pinWrite(lvpgoodMCP, pin_map[channel], value) == -1){
      char error_msg[50];
      sprintf(error_msg, "mcp powerOn fail write channel %u", channel);
      //error_log(error_msg);
      //return -1;
    }
  }

  return 0;
}

int i2c_lv_power_on(uint8_t channel, uint8_t pin_map[6]){
  int rv = i2c_lv_power_control(channel, pin_map, HIGH);
  return rv;
}

int i2c_lv_power_off(uint8_t channel, uint8_t pin_map[6]){
  int rv = i2c_lv_power_control(channel, pin_map, LOW);
  return rv;
}

void* i2c_loop(void* args){
  i2c_loop_args_t* casted = (i2c_loop_args_t*) args;
  PriorityQueue_t* queue = casted->queue;
  Logger_t* logger = casted->logger;
  uint8_t channel_map[6];
  memcpy(channel_map, casted->channel_map, sizeof(channel_map));

  char msg[128];
  while (1) {
    while (queue_size(queue) < 1){
      msleep(100);
    }

    // pop next task off the stack
    QueueItem_t* item = queue_pop(queue);
    task_t* task = (task_t*) (item->payload);
    sprintf(msg, "i2c received command label %u", task->command.name);
    log_write(logger, msg, LOG_VERBOSE);

    // execute i2c operation
    float rv;
    // lv commands
    if (task->command.name == COMMAND_powerOn){
      uint8_t channel = task->command.char_parameter;
      rv = i2c_lv_power_on(channel, channel_map);
    }
    else if (task->command.name == COMMAND_powerOff){
      uint8_t channel = task->command.char_parameter;
      rv = i2c_lv_power_off(channel, channel_map);
    }
    else if (task->command.name == COMMAND_readMonV6){
      rv = i2c_read_6V_voltage(task->command.char_parameter);
    }
    else if (task->command.name == COMMAND_readMonI6){
      rv = i2c_read_6V_current(task->command.char_parameter);
    }
    else if (task->command.name == COMMAND_readMonV48){
      rv = i2c_read_48V_voltage(task->command.char_parameter);
    }
    else if (task->command.name == COMMAND_readMonI48){
      rv = i2c_read_48V_current(task->command.char_parameter);
    }
    // hv commands these require pico-based hv polling
    // to protect against biasing the hv too quickly
//  else if (task->command.name == COMMAND_ramp_hv){
//    rv = i2c_ramp_hv(task->command.char_parameter, task->command.float_parameter);
//  }
//  else if (task->command.name == COMMAND_down_hv){
//    rv = i2c_ramp_hv(task->command.char_parameter, 0.0);
//  }
    // otherwise, have encountered an unexpected command
    else{
      sprintf(msg, "i2c encountered command of unknown label %u. skipping this command.", task->command.name);
      log_write(logger, msg, LOG_INFO);
    }

    // mark task as complete
    sprintf(msg, "i2c return value = %f", rv);
    log_write(logger, msg, LOG_VERBOSE);
    pthread_mutex_lock(&(task->mutex));
    task->rv = rv;
    task->complete = 1;
    pthread_mutex_unlock(&(task->mutex));
    pthread_cond_signal(&(task->condition));
  }
}
