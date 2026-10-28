// Ed Callaghan
// Factoring out some ugly details
// September 2024

#include "i2c_routines.h"
#include "rs485_notify.h"

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

#define STATION_RESET_PIN 25

static int station_reset_pulse(void){
  if (setup_gpio(STATION_RESET_PIN) == -1) {
    error_log("station reset failed configuring GPIO25");
    return -1;
  }

  if (write_gpio_value(STATION_RESET_PIN, LOW) == -1) {
    error_log("station reset failed driving GPIO25 low");
    return -1;
  }

  int wait_failed = msleep(500) != 0;
  // Attempt to release reset even if the wait failed.
  int release_failed = write_gpio_value(STATION_RESET_PIN, HIGH) == -1;
  if (wait_failed) error_log("station reset failed waiting 500 ms");
  if (release_failed) error_log("station reset failed driving GPIO25 high");
  return (wait_failed || release_failed) ? -1 : 0;
}

Message_t* i2c_station_reset(void){
  return message_wrap_int(station_reset_pulse());
}

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

static int ltc2497_write_channel(uint8_t channelLTC) {
  unsigned char block[1] = {channelLTC};

  for (int attempt = 0; attempt < 15; attempt++) {
    if (write(lv_i2c, block, 1) == 1) {
      return 0;
    }

    msleep(20);
  }

  error_log("Failed to write LTC2497 channel to the i2c bus");
  printf("Failed to write LTC2497 channel to the i2c bus");

  return -1;
}

static int ltc2497_read_result(unsigned char block[3]) {
  for (int attempt = 0; attempt < 10; attempt++) {
    if (read(lv_i2c, block, 3) == 3) {
      return 0;
    }

    msleep(20);
  }

  error_log("Failed to read LTC2497 result from the i2c bus");
  printf("Failed to read LTC2497 result from the i2c bus");

  return -1;
}

static float ltc2497_block_to_voltage(unsigned char block[3]) {
  float max_reading = 8388608.0;
  float vref = 1.24;

  int val;
  if ((block[0] & 0x80)) {
    val = (int) (((block[0] & 0x3f) << 16) + (block[1] << 8) + (block[2] & 0xE0));
  } else {
    val = (int) (((~block[0] & 0x3f) << 16) + (~block[1] << 8) + (~block[2] & 0xE0));
  }

  return val * vref / max_reading;
}

float i2c_ltc2497(int address, int channelLTC) {
  unsigned char block[3];

  if (set_slave_addr(lv_i2c, address, 1) < 0) {
    error_log("Failed to set LTC2497 i2c address");
    printf("Failed to set LTC2497 i2c address");

    return -1;
  }

  if (ltc2497_write_channel((uint8_t) channelLTC) < 0) {
    return -1;
  }

  msleep(170);
  if (ltc2497_read_result(block) < 0) {
    return -1;
  }

  return ltc2497_block_to_voltage(block);
}

float i2c_read_low(uint8_t address, uint8_t channel, float scale){
  float acplscale = 8.2;
  float rv = i2c_ltc2497(address, channel);
  if (rv < 0) {
    return rv;
  }
  rv /= scale * acplscale;
  return rv;
}

static Message_t* i2c_read_low_all(uint8_t map[6], uint8_t LTCaddress[6], float scale){
  float acplscale = 8.2;
  float values[6];

  for (int base_channel = 0; base_channel < 2; base_channel++){
    for (int pair = 0; pair < 3; pair++){
      unsigned int channel_number = base_channel + (pair * 2);
      unsigned int mapped_channel = 5 - channel_number;
      uint8_t address = LTCaddress[mapped_channel];
      uint8_t channel = (5 << 5) + map[mapped_channel];

      if (set_slave_addr(lv_i2c, address, 1) < 0) {
        error_log("Failed to set LTC2497 i2c address");
        printf("Failed to set LTC2497 i2c address");
        return message_wrap_error(-1);
      }

      if (ltc2497_write_channel(channel) < 0) {
        return message_wrap_error(-1);
      }
    }

    msleep(170);

    for (int pair = 0; pair < 3; pair++){
      unsigned char block[3];
      unsigned int channel_number = base_channel + (pair * 2);
      unsigned int mapped_channel = 5 - channel_number;
      uint8_t address = LTCaddress[mapped_channel];

      if (set_slave_addr(lv_i2c, address, 1) < 0) {
        error_log("Failed to set LTC2497 i2c address");
        printf("Failed to set LTC2497 i2c address");
        return message_wrap_error(-1);
      }

      if (ltc2497_read_result(block) < 0) {
        return message_wrap_error(-1);
      }

      values[channel_number] = ltc2497_block_to_voltage(block) / (scale * acplscale);
    }
  }

  Message_t* rv = message_initialize();
  MessageBlock_t* block = block_construct('F', 6);
  for (size_t i = 0; i < 6; i++){
    void* ptr = (void*) (values + i);
    block_insert(block, ptr);
  }
  message_append(rv, block);
  return rv;
}

Message_t* i2c_read_6V_voltage(unsigned int channel_number){
  uint8_t map[6] = {4, 3, 4, 3, 4, 3};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  float scale = 0.00857905;

  if (channel_number == 6) {
    return i2c_read_low_all(map, LTCaddress, scale);
  }
  if (channel_number > 6) {
    return message_wrap_error(-3);
  }

  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float frv = i2c_read_low(address, channel, scale);
  Message_t* rv = message_wrap_float(frv);
  return rv;
}

Message_t* i2c_read_6V_current(unsigned int channel_number){
  uint8_t map[6] = {5, 2, 5, 2, 5, 2};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  float scale = 0.010;

  if (channel_number == 6) {
    return i2c_read_low_all(map, LTCaddress, scale);
  }
  if (channel_number > 6) {
    return message_wrap_error(-3);
  }

  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float frv = i2c_read_low(address, channel, scale);
  Message_t* rv = message_wrap_float(frv);
  return rv;
}

Message_t* i2c_read_48V_voltage(unsigned int channel_number){
  uint8_t map[6] = {6, 0, 6, 0, 6, 0};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  float scale = 0.0012089;

  if (channel_number == 6) {
    return i2c_read_low_all(map, LTCaddress, scale);
  }
  if (channel_number > 6) {
    return message_wrap_error(-3);
  }

  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float frv = i2c_read_low(address, channel, scale);
  Message_t* rv = message_wrap_float(frv);
  return rv;
}

Message_t* i2c_read_48V_current(unsigned int channel_number){
  uint8_t map[6] = {7, 1, 7, 1, 7, 1};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  float scale = 0.010;

  if (channel_number == 6) {
    return i2c_read_low_all(map, LTCaddress, scale);
  }
  if (channel_number > 6) {
    return message_wrap_error(-3);
  }

  // reverse polarity of channeling
  channel_number = 5 - channel_number;
  uint8_t address = LTCaddress[channel_number];
  uint8_t channel = (5 << 5) + map[channel_number];
  float frv = i2c_read_low(address, channel, scale);
  Message_t* rv = message_wrap_float(frv);
  return rv;
}

int i2c_lv_power_control(uint8_t channel, uint8_t pin_map[6], int value){
  if (channel > 6 || !pin_map || (value != HIGH && value != LOW)) return -1;

  if (channel == 6 && value == HIGH && station_reset_pulse() != 0) return -1;

  int failed = 0;
  if (value == HIGH || channel == 6){
    if (write_gpio_value(lv_global_enable, value) < 0){
      error_log("LV power control failed writing global enable");
      failed = 1;
    }
  }

  // Complete all requested writes, especially every channel during shutdown.
  unsigned int begin = channel == 6 ? 0 : channel;
  unsigned int end = channel == 6 ? 6 : channel + 1;
  for (unsigned int i = begin; i < end; ++i){
    if (MCP_pinWrite(lvpgoodMCP, pin_map[i], value) < 0){
      char error_msg[80];
      snprintf(error_msg, sizeof error_msg, "LV power control failed writing channel %u", i);
      error_log(error_msg);
      failed = 1;
    }
  }
  return failed ? -1 : 0;
}

Message_t* i2c_lv_power_on(uint8_t channel, uint8_t pin_map[6]){
  int irv = i2c_lv_power_control(channel, pin_map, HIGH);
  if (rs485_notify_power_on(channel, irv) != 0) {
    error_log("RS485 discovery notification unavailable; LV powerOn result unchanged");
  }
  Message_t* rv = message_wrap_int(irv);
  return rv;
}

Message_t* i2c_lv_power_off(uint8_t channel, uint8_t pin_map[6]){
  int irv = i2c_lv_power_control(channel, pin_map, LOW);
  Message_t* rv = message_wrap_int(irv);
  return rv;
}

int i2c_dac_write(uint8_t channel, uint32_t value, i2c_state_t* state){
  if (!state || channel >= LVHV_HV_CHANNELS || value > LVHV_HV_DAC_MAX) return -1;
  unsigned int idx = channel / 4;
  if (DAC8164_writeChannel(&hv_dacs[idx], channel, (uint16_t)value) < 0) return -1;
  // A failed/ambiguous transfer must not become an acknowledged cached setting.
  state->hv_dac[channel] = value;
  return 0;
}

Message_t* i2c_set_hv_by_dac(uint8_t channel, float value, i2c_state_t* state){
  command_t command = {.name = COMMAND_set_hv_by_dac, .type = TYPE_hv,
                       .char_parameter = channel, .float_parameter = value};
  if (!command_is_valid(&command)) return message_wrap_error(-3);
  return message_wrap_int(i2c_dac_write(channel, (uint32_t)value, state));
}

Message_t* i2c_query_hv_dac_cache(uint8_t channel, i2c_state_t* state){
  if (!state || channel >= LVHV_HV_CHANNELS) return message_wrap_error(-3);
  return message_wrap_unsigned_int(state->hv_dac[channel]);
}

void* i2c_loop(void* args){
  i2c_loop_args_t* casted = (i2c_loop_args_t*) args;
  PriorityQueue_t* queue = casted->queue;
  Logger_t* logger = casted->logger;
  uint8_t channel_map[6];
  memcpy(channel_map, casted->channel_map, sizeof(channel_map));
  char msg[128];

  // initialize state cache
  i2c_state_t state;
  memset(&state.hv_dac, 0, sizeof(state.hv_dac));

  while (1) {
    while (queue_size(queue) < 1){
      msleep(100);
    }

    // pop next task off the stack
    QueueItem_t* item = queue_pop(queue);
    task_t* task = (task_t*) (item->payload);
    snprintf(msg, sizeof(msg), "i2c received command %s (%" PRIu32 ")",
             command_name(task->command.name), task->command.name);
    log_write(logger, msg, LOG_VERBOSE);

    // execute i2c operation
    Message_t* rv;
    // lv commands
    if (!command_is_valid(&task->command)){
      rv = message_wrap_error(-3);
    }
    else if (task->command.name == COMMAND_powerOn){
      uint8_t channel = task->command.char_parameter;
      rv = i2c_lv_power_on(channel, channel_map);
    }
    else if (task->command.name == COMMAND_powerOff){
      uint8_t channel = task->command.char_parameter;
      rv = i2c_lv_power_off(channel, channel_map);
    }
    else if (task->command.name == COMMAND_station_reset){
      rv = i2c_station_reset();
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
    // Direct DAC writes are stepped by the Python ramp client.
    else if (task->command.name == COMMAND_set_hv_by_dac){
      uint8_t channel = task->command.char_parameter;
      rv = i2c_set_hv_by_dac(channel, task->command.float_parameter, &state);
    }
    else if (task->command.name == COMMAND_query_hv_dac_cache){
      uint8_t channel = task->command.char_parameter;
      rv = i2c_query_hv_dac_cache(channel, &state);
    }
    // otherwise, have encountered an unexpected command
    else{
      sprintf(msg, "i2c encountered command of unknown label %u. skipping this command.", task->command.name);
      log_write(logger, msg, LOG_INFO);
      rv = message_wrap_chars("ERROR");
    }

    // mark task as complete
    // sprintf(msg, "i2c return value = %f", rv);
    // log_write(logger, msg, LOG_VERBOSE);
    pthread_mutex_lock(&(task->mutex));
    task->rv = rv;
    task->complete = 1;
    pthread_mutex_unlock(&(task->mutex));
    pthread_cond_signal(&(task->condition));
  }
}
