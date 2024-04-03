#include <libusb-1.0/libusb.h>
#include <libudev.h>

// C library headers
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <math.h>
#include <pthread.h>
#include <signal.h> 
#include <time.h>
#include <inttypes.h>
#include <unistd.h>

// sys headers
#include <sys/msg.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/ioctl.h>

// linux headers
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <linux/spi/spidev.h>

// Linux headers
#include <fcntl.h>   // Contains file controls like O_RDWR
#include <errno.h>   // Error integer and strerror() function
#include <termios.h> // Contains POSIX terminal control definitions

// other headers
#include <netinet/in.h>
#include "dac8164.h"
#include "MCP23S08.h"
#include "gpio.h"
#include "utils.h"
#include <i2c/smbus.h>
#include "i2cbusses.h"

#include <sys/un.h>

#include "../commands.h"

#define CLIENT_SOCK_FILE "client.sock"
#define SERVER_SOCK_FILE "/tmp/serversock"


// ----- libusb constants and variables ----- //
#define HISTORY_LENGTH 100
#define VENDOR_ID_0 0xcaf0
#define VENDOR_ID_1 0xcaf1
#define PRODUCT_ID 0x4003

struct libusb_device_handle *device_handle_0 = NULL;
struct libusb_device_handle *device_handle_1 = NULL;

int use_pico0 = 1;
int use_pico1 = 1;

int write_data_0 = 0;
int write_data_1 = 0;


// ----- Thread-related variables -----

pthread_t acquisition_thread_0;
pthread_t acquisition_thread_1;
pthread_t command_execution_thread;
pthread_t status_thread_0;
pthread_t socket_creation_thread;

pthread_mutex_t usb0_mutex_lock;
pthread_mutex_t usb1_mutex_lock;

// socket constant
#define PORT 12000
DAC8164 dac[3]; // HV DAQ objects

// variables to store LV i2c connection info
int lv_i2cbus;
static int lv_i2c = 0;

// assorted values to be returned upon client request
float voltages_0[6];
float voltages_1[6];

float currents_0[6];
float currents_1[6];

// LV channel information
uint8_t powerChMap[6] = {5, 6, 7, 2, 3, 4};
uint8_t lv_mcp_reset = 3;
uint8_t lv_global_enable = 18;

int current_datafile_time_0 = 0;
int current_num_storages_0 = 0;
int current_max_storages_0 = 14E6;
int current_datafile_time_1 = 0;
int current_num_storages_1 = 0;
int current_max_storages_1 = 14E6;
char *filename_I_0;
FILE *fp_I_0;
char *filename_I_1;
FILE *fp_I_1;
float last_current_output[6];

int voltage_datafile_time_0 = 0;
int voltage_num_storages_0 = 0;
int voltage_max_storages_0 = 14E6;
int voltage_datafile_time_1 = 0;
int voltage_num_storages_1 = 0;
int voltage_max_storages_1 = 14E6;
char *filename_V_0;
FILE *fp_V_0;
char *filename_V_1;
FILE *fp_V_1;




#define full_current_history_length 8000

typedef struct
{
  float all_currents[12][HISTORY_LENGTH];
  uint8_t pico;
} arg_struct;


// ----- Structures used in server communications with clients ----- //

typedef struct {
  int client_addr;
} client_data ;

uint8_t spi_bpw = 8; // bits per word
uint32_t spi_speed = 40000000; // 10MHz
uint16_t spi_delay = 0;

int spiFds;

static const uint8_t spi_mode = 0;

static const char* spidev = "/dev/spidev0.0"; //this is the SPI device. Assume here that there is only one SPI bus

MCP* hvMCP;
MCP* lvpowerMCP;
MCP* lvpgoodMCP;

#define SPISPEED 40000000
#define NSTEPS 200
#define SPICS 0

// ----- Variables for GUI connection -----
const char *LIVE_STATUS_FILENAME = "../live_status.txt";
char pipe_path_base[14] = "/tmp/data_pipe";
char v_pipe_path_base[15] = "/tmp/vdata_pipe";

#define ALPHA 0.1 // Choose a value between 0 and 1. Smaller values result in heavier filtering.
#define DECIMATION_FACTOR 10
uint8_t use_pipe = 1; // when server tries to open pipe, will be set to 0 upon fail - will then assume pipe is not to be used
int num_pipes = 6;
int pipe_channels[6] = {0, 1, 2, 3, 4, 5};

// initialize command queue variables
int queue_key;
int queue_id;
int msqid;

int pico_queue_key;
int pico_queue_id;
int pico_msqid;

command add_command;

command parse_queue() {
  command return_command;
  long msgtyp = 0;
  msgrcv(msqid, (void *)&return_command, 56, msgtyp, MSG_NOERROR | IPC_NOWAIT);
  return return_command;
}

command parse_pico_queue() {
  command return_command;
  long msgtyp = 0;
  msgrcv(pico_msqid, (void *)&return_command, 56, msgtyp, MSG_NOERROR | IPC_NOWAIT);
  return return_command;
}

float i2c_ltc2497(int address, int channelLTC) {
  float max_reading = 8388608.0;
  float vref = 1.24;

  unsigned char block[I2C_SMBUS_BLOCK_MAX];

  set_slave_addr(lv_i2c, address, 1);

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

  msleep(500);

  //----- READ BYTES -----
  length = 3;                                //<<< Number of bytes to read
  if (read(lv_i2c, block, length) != length) // read() returns the number of bytes actually read, if it doesn't match then an error occurred (e.g. no response from the device)
  {
    // ERROR HANDLING: i2c transaction failed

    error_log("Failed to read from the i2c bus");
    printf("Failed to read from the i2c bus");

    return -1;
  }

  uint32_t val = ((block[0] & 0x3f) << 16) + (block[1] << 8) + (block[2] & 0xE0);

  return val * vref / max_reading;
}



int powerOn(uint8_t channel, int client_addr) {
  char* command_log = load_config("Command_Log_File");
  uint8_t local_powerChMap[6] = {5, 6, 7, 2, 3, 4};

  // log powerOn command
  char log_message[12];
  snprintf(log_message, 12, "powerOn: %i", channel);
  write_log(command_log, log_message, 1, client_addr);

  if (channel < 0 || channel > 6) {
    error_log("Invalid powerOn channel value");
    printf("Invalid powerOn channel value\n");

    return 0;
  }

  

  if (write_gpio_value(lv_global_enable, HIGH) == -1) {
    error_log("poweron error 0");
    printf("poweron error 0");
    //return -1;
  }
  
  if (channel == 6) {
    for (int i=0; i<6; i++) {
      if (MCP_pinWrite(lvpgoodMCP, local_powerChMap[i], HIGH) == -1) {
        //return -1;

        char error_msg[50];
        sprintf(error_msg, "mcp powerOn fail write channel %i", i);
        error_log(error_msg);

        // display error message
        printf(error_msg);
      }

    }
  } else {
    if (MCP_pinWrite(lvpgoodMCP, local_powerChMap[channel], HIGH) == -1) {
      //return -1;


      char error_msg[50];
      sprintf(error_msg, "mcp powerOn fail write channel %u", channel);
      error_log(error_msg);

      // display error message
      printf(error_msg);
    }

    
  }

  return 0;
}

int powerOff(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  uint8_t local_powerChMap[6] = {5, 6, 7, 2, 3, 4};

  // log powerOff command
  char log_message[13];
  snprintf(log_message, 12, "powerOff: %i", channel);
  write_log(command_log, log_message, 1, client_addr);

  if (channel < 0 || channel > 6) {
    error_log("Invalid powerOff channel value");
    printf("Invalid powerOff channel value\n");

    return 0;
  }


  if (channel == 6) {
    if (write_gpio_value(lv_global_enable, LOW) == -1) {
      error_log("poweroff error 0");
      printf("poweroff error 0");
      //return -1;
    }
    
    for (int i=0; i<6; i++) {
      if (MCP_pinWrite(lvpgoodMCP, local_powerChMap[i], LOW) == -1) {
        //return -1;

        char error_msg[50];
        sprintf(error_msg, "mcp powerOff fail write channel %i", i);
        error_log(error_msg);

        // display error message
        printf(error_msg);
      }


      
    }
  } else {
    if (MCP_pinWrite(lvpgoodMCP, local_powerChMap[channel], LOW) == -1) {
      //return -1;

      char error_msg[50];
      sprintf(error_msg, "mcp powerOff fail write channel %u", channel);
      error_log(error_msg);

      // display error message
      printf(error_msg);

    }

   
  }

  return 0;
}

int hv_initialization() {
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
  } else if (DAC8164_setup (&dac[0], hvMCP, 6, 7, 0, -1, -1) == -1) {
    error_log("hv_initialization DAC8164_setup dac0 failure");
    printf("hv_initialization DAC8164_setup dac0 failure");

    return -1;
  } else if (DAC8164_setup (&dac[1], hvMCP, 3, 7, 0, -1, -1) == -1) {
    error_log("hv_initialization DAC8164_setup dac1 failure");
    printf("hv_initialization DAC8164_setup dac1 failure");

    return -1;
  } else if (DAC8164_setup (&dac[2], hvMCP, 5, 7, 0, -1, -1) == -1) {
    error_log("hv_initialization DAC8164_setup dac2 failure");
    printf("hv_initialization DAC8164_setup dac2 failure");

    return -1;
  }

  return 0;
}

void set_hv(int channel, float value) {
  int idac = (int)(channel / 4);
  float alphas[12] = {0.9, 0.9, 0.885, 0.9, 0.9012, 0.9034, 0.9009, 0.9027, 0.8977, 0.9012, 0.9015, 1.};

  uint32_t digvalue = ((int)(alphas[channel] * 16383. * (value / 1631.3))) & 0x3FFF;

  DAC8164_writeChannel(&dac[idac], channel, digvalue);
}



// get_vhv
void get_vhv(uint8_t channel, int client_addr) {
  float return_val = 0;
  
  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    return_val = voltages_0[channel];
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    return_val = voltages_1[channel - 6];
  } else {
    return_val = 0;
  }

  int float_channel = (int)channel;

  write(client_addr, &return_val, sizeof(return_val));
}

// get_ihv
void get_ihv(uint8_t channel, int client_addr) {
  float return_val = 0;

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    return_val = currents_0[channel];
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    return_val = currents_1[channel - 6];
  } else {
    error_log("Invalid get_ihv channel value");
    printf("Invalid get_ihv channel value\n");

    write(client_addr, &return_val, sizeof(return_val));

    return;
  }

  write(client_addr, &return_val, sizeof(return_val));
}

// get_buffer_status
void get_buffer_status(uint8_t channel, int client_addr) {
  uint8_t send_val = 95;
  char *input_data;
  input_data = (char *)malloc(1);

  int return_val = 1;

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_0, 0x82, input_data, sizeof(input_data), 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel & channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_1, 0x82, input_data, sizeof(input_data), 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid get_buffer_status channel value");
    printf("Invalid get_buffer_status channel value\n");

    write(client_addr, &return_val, sizeof(return_val));

    return;
  }

  
  if ((*input_data & 1 << (channel)) == 0) {
    return_val = 0;
  }
 
  write(client_addr, &return_val, sizeof(return_val));
}

void get_slow_read(uint8_t channel, int client_addr) {
  uint8_t send_val = 97;

  char *input_data;
  input_data = (char *)malloc(1);

  int return_val = 0;

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_0, 0x82, input_data, sizeof(input_data), 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_1, 0x82, input_data, sizeof(input_data), 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid get_slow_read channel");
    printf("Invalid get_slow_read channel\n");

    write(client_addr, &return_val, sizeof(return_val));

    return;
  }

  
  return_val = (int) *input_data;
  printf("slow read value of: %i\n", return_val);

  write(client_addr, &return_val, sizeof(return_val));
}


// returns 10 values from full speed current buffer
void current_burst(uint8_t channel, int client_addr) {
  struct libusb_device_handle *device_handle;

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    device_handle = device_handle_0;
    pthread_mutex_lock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    device_handle = device_handle_1;
    pthread_mutex_lock(&usb1_mutex_lock);
  } else {
    error_log("Invalid current_burst channel value");
    printf("Invalid current_burst channel value\n");

    return;
  }

  uint8_t get_buffer = 89 + channel;
  char *current_input_data;
  current_input_data = (char *)malloc(64);
  float current_array[16];

  libusb_bulk_transfer(device_handle, 0x02, &get_buffer, 1, 0, 50);

  int return_val = libusb_bulk_transfer(device_handle, 0x82, current_input_data, 64, 0, 500);

  for (int i=0; i<10; i++) {
    current_array[i] = *(float *)&current_input_data[4*i];

  }

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_unlock(&usb1_mutex_lock);
  }

  write(client_addr, &current_array, sizeof(current_array));



}

void start_buffer(uint8_t channel, int client_addr) {
  printf("in start_buffer\n");

  uint8_t start_buffer = 87;

  struct libusb_device_handle *device_handle;

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    device_handle = device_handle_0;
    pthread_mutex_lock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    device_handle = device_handle_1;
    pthread_mutex_lock(&usb1_mutex_lock);
  } else {
    error_log("Invalid start_buffer channel value");
    printf("Invalid start_buffer channel value\n");

    return;
  }

  libusb_bulk_transfer(device_handle, 0x02, &start_buffer, 1, 0, 0);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_unlock(&usb1_mutex_lock);
  }
}


void stop_buffer(uint8_t channel, int client_addr) {
  uint8_t stop_buffer = 88;

  struct libusb_device_handle *device_handle;

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    device_handle = device_handle_0;
    pthread_mutex_lock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    device_handle = device_handle_1;
    pthread_mutex_lock(&usb1_mutex_lock);
  } else {
    error_log("Invalid stop_buffer channel value");
    printf("Invalid stop_buffer channel value\n");

    return;
  }

  libusb_bulk_transfer(device_handle, 0x02, &stop_buffer, 1, 0, 0);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    device_handle = device_handle_1;
    pthread_mutex_unlock(&usb1_mutex_lock);
  }
}


// rampHV
void ramp_hv(uint8_t channel, float voltage, int client_addr) {
  printf("in ramp_hv\n");
  //char *command_log = load_config("Command_Log_File");
  char *command_log = "Command_Log_File:../../Logs/command_log.log";

  // log ramp_hv command
  char log_message[12];
  snprintf(log_message, 12, "ramp_hv: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  int idac = (int)(channel / 4);
  float increment = voltage / NSTEPS;
  float current_value = 0;

  if (0 <= channel && channel < 12) {
    for (int itick=0; itick<NSTEPS; itick++) {
      usleep(50000);
      current_value += increment;

      set_hv(channel, current_value);
    }
  } else {
    error_log("Invalid ramp_hv channel value");
    printf("Invalid ramp_hv channel value\n");

    return;
  }

  
}


void down_hv(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");

  // log down_hv command
  char log_message[12];
  snprintf(log_message, 12, "down_hv: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  float current_voltage;
  if (0 <= channel && channel < 6) {
    current_voltage = voltages_0[channel];
  } else if (5 < channel && channel < 12) {
    current_voltage = voltages_1[channel - 6];
  } else {
    error_log("Invalid down_hv channel value");
    printf("Invalid down_hv channel value\n");

    return;
  }

  int idac = (int)(channel / 4);
  float increment = current_voltage / NSTEPS;

  for (int itick = 0; itick < NSTEPS; itick++) {
    usleep(50000);
    current_voltage -= increment;
    set_hv(channel, current_voltage);
  }

  set_hv(channel,0);

  
}

// trip
void trip(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  uint8_t send_val = 103 + (channel % 6);

  // log trip command
  char log_message[12];
  snprintf(log_message, 12, "tripped: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid trip channel value");
    printf("Invalid trip channel value\n");

    return;
  }



  
}

// reset_trip
void reset_trip(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  uint8_t send_val = 109 + (channel % 6);


  // log reset_trip command
  char log_message[15];
  snprintf(log_message, 15, "reset_trip: %u", channel);
  write_log(command_log, log_message, 0, client_addr);


  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid reset_trip channel value");
    printf("Invalid reset_trip channel value\n");

    return;
  }

  
}

// disable_trip
void disable_trip(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  uint8_t send_val = 115 + (channel % 6);

  // log disable_trip command
  char log_message[17];
  snprintf(log_message, 17, "disable_trip: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid disable_trip channel value");
    printf("Invalid disable_trip channel value\n");

    return;
  }

}

// enable_trip
void enable_trip(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  uint8_t send_val = 121 + (channel % 6);

  // log enable_trip command
  char log_message[16];
  snprintf(log_message, 16, "enable_trip: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid enable_trip channel value");
    printf("Invalid enable_trip channel value\n");

    return;
  }

  
}



// enable_ped
void enable_ped(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  uint8_t send_val = 37;

  // log enable_ped command
  char log_message[15];
  snprintf(log_message, 15, "enable_ped: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid enable_ped channel value");
    printf("Invalid enable_ped channel value\n");

    return;
  }
}

// disable_ped
void disable_ped(uint8_t channel, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  
  uint8_t send_val = 38;

  // log disable_ped command
  char log_message[16];
  snprintf(log_message, 16, "disable_ped: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid disable_ped channel value");
    printf("Invalid disable_ped channel value\n");

    return;
  }

  
}


// trip_status
void trip_status(uint8_t channel, int client_addr) {
  uint8_t send_val = 33;
  char *input_data;
  input_data = (char *)malloc(1);
  int return_val = 1;



  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_0, 0x82, input_data, sizeof(input_data), 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);

    if ((*input_data & 1 << (channel)) == 0) {
      return_val = 0;
    }



  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_1, 0x82, input_data, sizeof(input_data), 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);

    if ((*input_data & 1 << (channel-6)) == 0) {
      return_val = 0;
    }
  } else {
    error_log("Invalid trip_status channel value");
    printf("Invalid trip_status channel value\n");


  }
  free(input_data);

  

  if (client_addr != -9999) {
    write(client_addr, &return_val, sizeof(return_val));
  } else {
    write_fixed_location(LIVE_STATUS_FILENAME, 2 * channel, return_val); // writes at fixed location
  }
}

// set_trip
void set_trip(uint8_t channel, float value, int client_addr) {
  char *command_log = load_config("Command_Log_File");
  uint8_t send_val[3];
  send_val[0] = 76 + (channel % 6);
  uint16_t send_int;
  send_int = (uint16_t)(value / 1000 * 65535);
  uint8_t right_mask = -1;
  send_val[1] = send_int >> 8 & right_mask;
  send_val[2] = send_int & right_mask;
  uint16_t one = send_val[1] << 8;
  uint16_t two = send_val[2] + one;

  // log set_trip command
  char log_message[13];
  snprintf(log_message, 13, "set_trip: %u", channel);
  write_log(command_log, log_message, 0, client_addr);

  if (0 <= channel && channel < 6 && use_pico0 == 1) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val[0], sizeof(send_val), 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else if (5 < channel && channel < 12 && use_pico1 == 1) {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val[0], sizeof(send_val), 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  } else {
    error_log("Invalid set_trip channel value");
    printf("Invalid set_trip channel value\n");

    return;
  }

}

// readMonV48
void readMonV48(uint8_t channel, int client_addr) {
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t v48map[6] = {6, 0, 6, 0, 6, 0};

  float v48scale = 0.0012089;
  float acplscale = 8.2;
  float ret = 0;

  if (channel > 5 || channel < 0) {
    error_log("Invalid readMonV48 channel value");
    printf("Invalid readMonV48 channel value\n");

    write(client_addr, &ret, sizeof(ret));

    return;
  }

  uint8_t index = v48map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (v48scale * acplscale);

  write(client_addr, &ret, sizeof(ret));
}

// readMonI48
void readMonI48(uint8_t channel, int client_addr) {
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t i48map[6] = {7, 1, 7, 1, 7, 1};

  float i48scale = 0.010;
  float acplscale = 8.2;
  float ret = 0;

  if (channel > 5 || channel < 0) {
    error_log("Invalid readMonI48 channel value");
    printf("Invalid readMonI48 channel value\n");

    write(client_addr, &ret, sizeof(ret));

    return;
  }

  uint8_t index = i48map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (i48scale * acplscale);

  write(client_addr, &ret, sizeof(ret));
}
// readMonV6
void readMonV6(uint8_t channel, int client_addr) {
  uint8_t v6map[6] = {4, 3, 4, 3, 4, 3};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};

  float v6scale = 0.00857905;
  float acplscale = 8.2;
  float ret = 0;

  if (channel > 5 || channel < 0) {
    error_log("Invalid readMonV6 channel value");
    printf("Invalid readMonV6 channel value\n");

    write(client_addr, &ret, sizeof(ret));

    return;
  }

  uint8_t index = v6map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (v6scale * acplscale);

  write(client_addr, &ret, sizeof(ret));
}

// readMonI6
void readMonI6(uint8_t channel, int client_addr) {
  uint8_t addresses[3] = {0x14, 0x16, 0x26};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t i6map[6] = {5, 2, 5, 2, 5, 2};

  float i6scale = 0.010;
  float acplscale = 8.2;
  float ret = 0;

  if (channel > 5 || channel < 0) {
    error_log("Invalid readMonI6 channel value");
    printf("Invalid readMonI6 channel value\n");

    write(client_addr, &ret, sizeof(ret));

    return;
  }

  uint8_t index = i6map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (i6scale * acplscale);

  write(client_addr, &ret, sizeof(ret));
}

void *command_execution() {
  uint32_t current_command;
  uint32_t current_type;
  uint8_t char_parameter;
  float float_parameter;
  int client_addr;

  while (1) {
    command check_command = parse_queue();
    current_command = check_command.command_name;
    current_type = check_command.command_type;
    char_parameter = (uint8_t)check_command.char_parameter-97;
    //char_parameter = 0;


    float_parameter = check_command.float_parameter;
    client_addr = check_command.client_addr;



    //printf("current type: %u\n",current_type);





 



    // check if command is hv type, else do nothing
    if (current_type == TYPE_hv) {;
      // select proper hv function
      //printf("in typehv\n");

      fflush(stdout); // not sure why needed, investigate
      
      if (current_command == COMMAND_get_vhv) { // get_vhv
        get_vhv(char_parameter, client_addr);
      } else if (current_command == COMMAND_get_ihv) { // get_ihv
        get_ihv(char_parameter, client_addr);
      } else if (current_command == COMMAND_ramp_hv) { // ramp_hv
        ramp_hv(char_parameter, float_parameter, client_addr);
      } else if (current_command == COMMAND_down_hv) { // down_hv
        down_hv(char_parameter, client_addr);
      } else if (current_command == COMMAND_current_burst) { // under TYPE_hv to increase speed
        current_burst(char_parameter, client_addr);
      }
    }

    


    if (current_type == TYPE_lv) {
      fflush(stdout);

      // select proper lv function
      if (current_command == COMMAND_readMonV48) { // readMonV48
        readMonV48(char_parameter, client_addr);
      } else if (current_command == COMMAND_readMonI48) { // readMonI48
        readMonI48(char_parameter, client_addr);
      } else if (current_command == COMMAND_readMonV6) { // readMonV6
        readMonV6(char_parameter, client_addr);
      } else if (current_command == COMMAND_readMonI6) { // readMonI6
        readMonI6(char_parameter, client_addr);
      } else if (current_command == COMMAND_powerOn) { // powerOn
        int errval = powerOn(char_parameter, client_addr);

        if (errval == -1) {
          error_log("LV powerOn Error");
        }
      } else if (current_command == COMMAND_powerOff) { // powerOff
        usleep(1);
        int errval = powerOff(char_parameter, client_addr);

        if (errval == -1) {
          error_log("LV powerOff Error");
        }
      }
    }
    msleep(5);
  }
}

// ----- Code to handle socket stuff ----- //
void *handle_client(void *args) {
  client_data *client_information = args;
  int inner_socket = client_information->client_addr;
  char buffer[30];
  char flush_buffer[1];
  int command_valid;

  char* command_log = load_config("Command_Log_File");
  write_log(command_log, "New Client Connected", 3, inner_socket);

  while (1) {
    int return_val = read(inner_socket, buffer, 30);
    // if return_val is -1, terminate thread
    if (return_val == 0) {
      printf("Thread terminated \n");
      write_log(command_log, "Client Disconnected", 3, inner_socket);
      return 0;
    }

    if (return_val == 13) {

      // create command
      //add_command.command_name = memcpy(buffer[0]);

      uint32_t zero = buffer[3];
      uint32_t one = buffer[2] << 8;
      uint32_t two = buffer[1] << 16;
      uint32_t three = buffer[0] << 24;
      add_command.command_name = zero + one + two + three;
      //add_command.command_name = (uint32_t) 1354023252;

      uint32_t zero_0 = buffer[7];
      uint32_t one_0 = buffer[6] << 8;
      uint32_t two_0 = buffer[5] << 16;
      uint32_t three_0 = buffer[4] << 24;
      add_command.command_type = zero_0 + one_0 + two_0 + three_0;
      //add_command.command_type = (uint32_t) 1354023252;


      
      memcpy(&add_command.char_parameter, &buffer[8], 1);
      memcpy(&add_command.float_parameter, &buffer[9], 4);

      add_command.client_addr = inner_socket;


    

      // check if command is valid
      //command_valid = is_command_valid(add_command.command_type, add_command.command_name);
      
      // add command to linux kernel queue
      if (add_command.command_type == TYPE_pico) {
        msgsnd(pico_msqid, (void *)&add_command, sizeof(add_command), IPC_NOWAIT);
      } else if (add_command.command_type == TYPE_hv || add_command.command_type == TYPE_lv) {



        int snd_success = msgsnd(msqid, (void *)&add_command, sizeof(add_command), 0);
      }
    }

  }
}

// ----- Code to handle socket stuff ----- //
void *live_status(void *args) {
  char buffer[9];
  char flush_buffer[1];

  while (1) {
    for (int ichannel = 0; ichannel < 6; ichannel++) {
      // create command
      add_command.command_name = COMMAND_trip_status;
      add_command.command_type = TYPE_pico;
      add_command.char_parameter = ichannel + 97;
      add_command.float_parameter = 0;
      add_command.client_addr = -9999;

      // add command to queue
      msgsnd(pico_msqid, (void *)&add_command, sizeof(add_command), IPC_NOWAIT);

    }
    sleep(2);
  }
}



void *create_connections() {
  int server_fd, new_socket, valread;
  struct sockaddr_in address;
  int opt = 1;
  int addrlen = sizeof(address);

  // Creating socket file descriptor
  if ((server_fd = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
    perror("socket failed");
    exit(EXIT_FAILURE);
  }

  // Forcefully attaching socket to the port 8080
  if (setsockopt(server_fd, SOL_SOCKET,
                 SO_REUSEADDR | SO_REUSEPORT, &opt,
                 sizeof(opt))) {
    perror("setsockopt");
    exit(EXIT_FAILURE);
  }
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = INADDR_ANY;
  address.sin_port = htons(PORT);

  // Forcefully attaching socket to the port 8080
  if (bind(server_fd, (struct sockaddr *)&address,
           sizeof(address)) < 0) {
    perror("bind failed");
    exit(EXIT_FAILURE);
  }

  if (listen(server_fd, 3) < 0) {
    perror("listen");
    exit(EXIT_FAILURE);
  }

  while (1) {
    if ((new_socket = accept(server_fd, (struct sockaddr *)&address,
                             (socklen_t *)&addrlen)) < 0) {
      perror("accept");
      exit(EXIT_FAILURE);
    }

    pthread_t client_thread;
    pthread_create(&client_thread, NULL, handle_client, &new_socket);
  }
}








int write_pipe_currents(int fd[num_pipes], float store_all_currents_internal[6][HISTORY_LENGTH]) {
      char buffer[1024];
      int write_success = 0;

      for (int pipe_id=0; pipe_id<num_pipes; pipe_id++) {
        for (uint32_t time_index = 0; time_index < HISTORY_LENGTH; time_index++) {
    
          for (uint8_t channel = 0; channel < 6; channel++) {
            // Apply the first-order low-pass filter
            float input_value = store_all_currents_internal[channel][time_index];
            float filtered_value = ALPHA * input_value + (1 - ALPHA) * last_current_output[channel];
            last_current_output[channel] = filtered_value;

            // Decimation by 5: Only write every 5th sample
            if (time_index % DECIMATION_FACTOR == 0 && use_pipe == 1) {
              int length = snprintf(buffer, sizeof(buffer), "%f ", filtered_value);

              write_success = write(fd[pipe_id], buffer, length); // Write to the pipe

              if (write_success == -1) {
                use_pipe = 0;
                error_log("Current pipe disconnected");
                return -1;
              }
            }
          }

          if (time_index % DECIMATION_FACTOR == 0 && use_pipe == 1) {
            int length = snprintf(buffer, sizeof(buffer), "\n");
            write_success = write(fd[pipe_id], buffer, length); // Write the timestamp to the pipe

            if (write_success == -1) {
            use_pipe = 0;
            error_log("Current pipe disconnected");
            return -1;
            }
          }
        }
      }
      return 0;
}


int write_pipe_voltages(int pico, int vfd[6], float voltages_0[6]) {
  int write_success = 0;

  if (pico == 0) {
    char buffer[1024]; // A buffer to format and write data
    for (int channel = 0; channel < 6; channel++) {
      // only write to pipe if connection was properly established earlier
      for (int pipe_id=0; pipe_id<num_pipes; pipe_id++) {
        if (use_pipe == 1) {
          int length = snprintf(buffer, sizeof(buffer), "%f ", voltages_0[channel]);
          write_success = write(vfd[pipe_id], buffer, length); // Write to the pipe
        }

        if (write_success == -1) {
          use_pipe = 0;
          error_log("Voltage pipe disconnected");
          return -1;
        }
      }

    }
  }
  int seconds = time(NULL);

  if (pico == 0 && use_pipe == 1) {
    char buffer[1024]; // A buffer to format and write data
    int length = snprintf(buffer, sizeof(buffer), "\n");
    for (int pipe_id=0; pipe_id<num_pipes; pipe_id++) {
      write_success = write(vfd[pipe_id], buffer, length); // Write to the pipe

      if (write_success == -1) {
        use_pipe = 0;
        error_log("Voltage pipe disconnected");
        return -1;
      }
    }
  }

  return 0;
}




int initialize_libusb(int pico) {


  // Set debugging output to max level
	libusb_set_option( NULL, LIBUSB_OPTION_LOG_LEVEL, LIBUSB_LOG_LEVEL_WARNING );

  // Open our ADU device that matches our vendor id and product id
  if (pico == 0) {

    device_handle_0 = libusb_open_device_with_vid_pid(NULL, VENDOR_ID_0, PRODUCT_ID);

    if (device_handle_0 == NULL) {
      use_pico0 = 0;
    } else {
      libusb_set_auto_detach_kernel_driver(device_handle_0, 1);
      // Claim interface 0 on the device
      libusb_claim_interface(device_handle_0, 1);
    }

  } else {

    device_handle_1 = libusb_open_device_with_vid_pid(NULL, VENDOR_ID_1, PRODUCT_ID);
    if (device_handle_1 == NULL) {
      use_pico1 = 0;
    } else {
      libusb_set_auto_detach_kernel_driver(device_handle_1, 1);
      // Claim interface 0 on the device
      libusb_claim_interface(device_handle_1, 1);
    }

  }



  return 0;
}




int initialize_pipes(int fd[num_pipes], int vfd[num_pipes]) {
  char *pipe_path = malloc(15);
  char *v_pipe_path = malloc(16);
  struct stat st_i;

  for (int pipe_id=0; pipe_id<num_pipes; pipe_id++) {
    strncpy(pipe_path, pipe_path_base, 15);
    pipe_path[14] = 48+pipe_channels[pipe_id];
    if (stat(pipe_path, &st_i) == -1)
    {
      if (mkfifo(pipe_path, 0666) == -1)
      {
        use_pipe = 0; // ensure that pipe isn't used if failed
      }
    }

    fd[pipe_id] = open(pipe_path, O_WRONLY | O_NONBLOCK);
    if (fd[pipe_id] == -1)
    {
      use_pipe = 0; // ensure that pipe isn't used if failed
    }
  }

  struct stat st[num_pipes];
  for (int pipe_id=0; pipe_id<num_pipes; pipe_id++) {
    sleep(0.1);
    memcpy(v_pipe_path, &v_pipe_path_base, 15);
    v_pipe_path[15] = pipe_channels[pipe_id]+48;

    if (stat(v_pipe_path, &st[pipe_id]) == -1)
    {
      if (mkfifo(v_pipe_path, 0666) == -1)
      {
        // ensure that pipe isn't used - would result in failure
        use_pipe = 0;
      }
    }

    vfd[pipe_id] = open(v_pipe_path, O_WRONLY | O_NONBLOCK);
    if (vfd[pipe_id] == -1)
    {
      // ensure that pipe isn't used - would result in failure
      use_pipe = 0;
    }
  }

  free(pipe_path);
  free(v_pipe_path);

  return 0;
}


int write_currents_0(float all_currents[12][HISTORY_LENGTH]) {
  char *file_suffix = ".txt";

  if (current_num_storages_0 >= current_max_storages_0) {
    current_datafile_time_0 = time(NULL);
    current_num_storages_0 = 0;
    fclose(fp_I_0);

    char current_precursor[23] = "../../Data/Currents_0_";
    strcpy(filename_I_0, &current_precursor[0]);

    char str_time[10];
    sprintf(str_time, "%i", current_datafile_time_0);
    strcat(filename_I_0, str_time);
    strcat(filename_I_0, file_suffix);

    fp_I_0 = fopen(filename_I_0, "a");
    if (fp_I_0 == NULL) {
      printf("Error opening the current file %s", filename_I_0);
    }
  } else {
    current_num_storages_0 += HISTORY_LENGTH;
  }
  
  // save data in current log
  for (uint32_t time_index=0; time_index<HISTORY_LENGTH; time_index++) {
    for (uint8_t channel=0; channel<6; channel++) {
      fprintf(fp_I_0, "%f ", all_currents[channel][time_index]);
    }
    fprintf(fp_I_0, "%f\n", (float)time(NULL));
  }

  return 0;
}

int write_currents_1(float all_currents[12][HISTORY_LENGTH]) {
  char *file_suffix = ".txt";

  if (current_num_storages_1 >= current_max_storages_1) {
    current_datafile_time_1 = time(NULL);
    current_num_storages_1 = 0;
    fclose(fp_I_1);

    char current_precursor[23] = "../../Data/Currents_1_";
    strcpy(filename_I_1, &current_precursor[0]);

    char str_time[10];
    sprintf(str_time, "%i", current_datafile_time_1);
    strcat(filename_I_1, str_time);
    strcat(filename_I_1, file_suffix);

    fp_I_1 = fopen(filename_I_1, "a");
    if (fp_I_1 == NULL) {
      printf("Error opening the current file %s", filename_I_1);
    }
  } else {
    current_num_storages_1 += HISTORY_LENGTH;
  }
  
  // save data in current log
  for (uint32_t time_index=0; time_index<HISTORY_LENGTH; time_index++) {
    for (uint8_t channel=0; channel<6; channel++) {
      fprintf(fp_I_1, "%f ", all_currents[channel+6][time_index]);
    }
    fprintf(fp_I_1, "%f\n", (float)time(NULL));
  }

  return 0;
}




int write_voltages_0(float voltages[6]) {
  char *file_suffix = ".txt";
   
  if (voltage_num_storages_0 >= voltage_max_storages_0) {
    voltage_datafile_time_0 = time(NULL);
    voltage_num_storages_0 = 0;
    fclose(fp_V_0);

    char voltage_precursor[23] = "../../Data/Voltages_0_";
    strcpy(filename_V_0, &voltage_precursor[0]);

    char str_time[10];
    sprintf(str_time, "%i", voltage_datafile_time_0);
    strcat(filename_V_0, str_time);
    strcat(filename_V_0, file_suffix);

    fp_V_0 = fopen(filename_V_0, "a");
    if (fp_V_0 == NULL) {
      printf("Error opening the current file %s", filename_V_0);
    }
  } else {
    voltage_num_storages_0 += HISTORY_LENGTH;
  }
  
  // save data in voltage log
  for (uint8_t channel=0; channel<6; channel++) {
    fprintf(fp_V_0, "%f ", voltages[channel]);
  }
  fprintf(fp_V_0, "%f\n", (float)time(NULL));

  return 0;
}




int write_voltages_1(float voltages[6]) {
  char *file_suffix = ".txt";
   
  if (voltage_num_storages_1 >= voltage_max_storages_1) {
    voltage_datafile_time_1 = time(NULL);
    voltage_num_storages_1 = 0;
    fclose(fp_V_1);

    char voltage_precursor[23] = "../../Data/Voltages_1_";
    strcpy(filename_V_1, &voltage_precursor[0]);

    char str_time[10];
    sprintf(str_time, "%i", voltage_datafile_time_1);
    strcat(filename_V_1, str_time);
    strcat(filename_V_1, file_suffix);

    fp_V_1 = fopen(filename_V_1, "a");
    if (fp_V_1 == NULL) {
          printf("Error opening the current file %s", filename_V_1);
        }

  } else {
    voltage_num_storages_1 += HISTORY_LENGTH;
  }
  
  // save data in voltage log
    for (uint8_t channel=0; channel<6; channel++) {
      fprintf(fp_V_1, "%f ", voltages[channel]);
    }
    fprintf(fp_V_1, "%f\n", (float)time(NULL));

    return 0;
}






int request_averaged_currents(float currents[12][HISTORY_LENGTH], int pico) {
  float floatval;
  char *input_data;
  input_data = (char *)malloc(64);
  char current_char = 'H';

  // fill up array
  for (uint16_t time_index = 0; time_index < HISTORY_LENGTH;)
  {
    if (pico == 0)
    {
      pthread_mutex_lock(&usb0_mutex_lock);
      libusb_bulk_transfer(device_handle_0, 0x02, &current_char, 1, 0, 0);
      libusb_bulk_transfer(device_handle_0, 0x82, input_data, 48, 0, 0);
      pthread_mutex_unlock(&usb0_mutex_lock);
    }
    else
    {
      pthread_mutex_lock(&usb1_mutex_lock);
      libusb_bulk_transfer(device_handle_1, 0x02, &current_char, 1, 0, 0);
      libusb_bulk_transfer(device_handle_1, 0x82, input_data, 48, 0, 0);
      pthread_mutex_unlock(&usb1_mutex_lock);
    }

    // check if new data from SmartSwitch
    floatval = *(float *)&input_data[0];
    if (floatval != -100)
    {

      for (uint32_t i = 0; i < 12; i++)
      {
        floatval = *(float *)&input_data[4 * i];
        if (pico == 0) {
          if (i < 6)
          {
            currents[i][time_index] = floatval;
          }
          else
          {
            currents[i-6][time_index+1] = floatval;
          }
        } else {
          if (i < 6)
          {
            currents[i+6][time_index] = floatval;
          }
          else
          {
            currents[i][time_index+1] = floatval;
          }
        }
      }
      time_index += 2;
    }
  }


  if (pico == 0) {
    for (uint8_t i = 0; i < 6; i++)
    {
      currents_0[i] = *(float *)&input_data[24+4*i];
    }
  } else {
    for (uint8_t i = 0; i < 6; i++)
    {
      currents_1[i] = *(float *)&input_data[24+4*i];
    }
  }

  free(input_data);


  return 0;
}


int request_voltages(int pico) {
  char voltage_char = 'V';
  char *input_data;
  input_data = (char *)malloc(24);

  if (pico == 0) {
    pthread_mutex_lock(&usb0_mutex_lock);
    libusb_bulk_transfer(device_handle_0, 0x02, &voltage_char, 1, 0, 0);
    libusb_bulk_transfer(device_handle_0, 0x82, input_data, 24, 0, 0);
    pthread_mutex_unlock(&usb0_mutex_lock);
  } else {
    pthread_mutex_lock(&usb1_mutex_lock);
    libusb_bulk_transfer(device_handle_1, 0x02, &voltage_char, 1, 0, 0);
    libusb_bulk_transfer(device_handle_1, 0x82, input_data, 24, 0, 0);
    pthread_mutex_unlock(&usb1_mutex_lock);
  }

  if (pico == 0) {
    for (uint32_t i = 0; i < 6; i++) {
      voltages_0[i] = *(float *)&input_data[4 * i];
    }
  } else {
    for (uint32_t i = 0; i < 6; i++) {
      voltages_1[i] = *(float *)&input_data[4 * i];
    }
  }
  
  free(input_data);

  return 0;
}


int initialize_txt(int pico) {
  time_t seconds;

  char *current_precursor;
  char *file_suffix = ".txt";
  char str_time[10];

  // ----- Initialize current ----- //
  if (pico == 0) {
    current_datafile_time_0 = time(NULL);
    filename_I_0 = malloc(50);
    current_precursor = "../../Data/Currents_0_";
    strcpy(filename_I_0, &current_precursor[0]);

    sprintf(str_time, "%i", current_datafile_time_0);
    strcat(filename_I_0, str_time);
    strcat(filename_I_0, file_suffix);

    fp_I_0 = fopen(filename_I_0, "a");

  } else {
    current_datafile_time_1 = time(NULL);
    filename_I_1 = malloc(50);
    current_precursor = "../../Data/Currents_1_";
    strcpy(filename_I_1, &current_precursor[0]);

    sprintf(str_time, "%i", current_datafile_time_1);
    strcat(filename_I_1, str_time);
    strcat(filename_I_1, file_suffix);

    fp_I_1 = fopen(filename_I_1, "a");
  }
  
  // ----- Initialize voltage ----- //
  char *voltage_precursor;
  if (pico == 0) {
    voltage_datafile_time_0 = time(NULL);
    filename_V_0 = malloc(50);
    voltage_precursor = "../../Data/Voltages_0_";
    strcpy(filename_V_0, &voltage_precursor[0]);

    sprintf(str_time, "%i", voltage_datafile_time_0);
    strcat(filename_V_0, str_time);
    strcat(filename_V_0, file_suffix);

    fp_V_0 = fopen(filename_V_0, "a");
  } else {
    voltage_datafile_time_1 = time(NULL);
    filename_V_1 = malloc(50);
    voltage_precursor = "../../Data/Voltages_1_";
    strcpy(filename_V_1, &voltage_precursor[0]);

    sprintf(str_time, "%i", voltage_datafile_time_1);
    strcat(filename_V_1, str_time);
    strcat(filename_V_1, file_suffix);

    fp_V_1 = fopen(filename_V_1, "a");
  }
}



// ----- Code to handle HV data acquisition & storage ----- //

void *acquire_data(void *arguments) {
  arg_struct *common = arguments;
  int pico = common->pico;
  float last_output[6]; // State for each channel's filter
  int fd[num_pipes];
  int vfd[num_pipes];

  if (initialize_libusb(pico) == -1) {
    char error_msg[100];
    sprintf(error_msg, "initialize_libusb failed for pico %i", pico);
    error_log(error_msg);
    printf(error_msg);
  }

  if (pico == 0 && use_pico0 == 1) {
    int pipe_initialization_success = initialize_pipes(fd, vfd);

    if (write_data_0 == 1) {
      int txt_init_success_0 = initialize_txt(0);
    }
  } else if (pico == 1 && use_pico1 == 1 && write_data_1 == 1) {
    int txt_init_success_1 = initialize_txt(1);
  }
  msleep(200);

  while (1) {
    command check_command = parse_pico_queue();
    uint32_t current_command = check_command.command_name;
    uint32_t current_type = check_command.command_type;
    uint8_t char_parameter = (uint8_t)check_command.char_parameter - 97;
    float float_parameter = check_command.float_parameter;
    int client_addr = check_command.client_addr;


    // check if command is pico type, else do nothing
    if (current_type == TYPE_pico)
    {

      // select proper hv function
      if (current_command == COMMAND_trip)
      { // trip
        trip(char_parameter, client_addr);
      }
      else if (current_command == COMMAND_reset_trip)
      { // reset trip
        reset_trip(char_parameter, client_addr);
      }
      else if (current_command == COMMAND_disable_trip)
      { // disable trip
        disable_trip(char_parameter, client_addr);
      }
      else if (current_command == COMMAND_enable_trip)
      { // enable trip
        enable_trip(char_parameter, client_addr);
      }
      else if (current_command == COMMAND_set_trip)
      { // set trip
        set_trip(char_parameter, float_parameter, client_addr);
      }
      else if (current_command == COMMAND_trip_status)
      { // trip status
        trip_status(char_parameter, client_addr);
      }
      else if (current_command == COMMAND_enable_ped)
      { // enable ped
        enable_ped(char_parameter, client_addr);
      }
      else if (current_command == COMMAND_disable_ped)
      { // disable ped
        disable_ped(char_parameter, client_addr);
      } 
      else if (current_command == COMMAND_current_start) 
      {
        start_buffer(char_parameter, client_addr);
      } 
      else if (current_command == COMMAND_current_stop) 
      {
        stop_buffer(char_parameter, client_addr);
      } 
      else if (current_command == COMMAND_current_buffer_run) 
      {
        get_buffer_status(char_parameter, client_addr);
      } 
      else if (current_command == COMMAND_get_slow_read) 
      {
        get_slow_read(char_parameter, client_addr);
      }
      
    }

    
    if (pico == 0 && use_pico0 == 1) {
      int current_success_0 = request_averaged_currents(common->all_currents, 0);
      int voltage_success_0 = request_voltages(0);
    }
    

    if (pico == 1 && use_pico1 == 1) {
      int current_success_1 = request_averaged_currents(common->all_currents, 1);
      int voltage_success_1 = request_voltages(1);
    }

    // ----- Write/send voltages/currents -----
    if (pico == 0 && use_pico0 == 1) {
      int pipe_voltage_success = write_pipe_voltages(0, vfd, voltages_0);
      int pipe_current_success = write_pipe_currents(fd, common->all_currents);

      if (write_data_0 == 1) {
        int current_write_success = write_currents_0(common->all_currents);
        int voltage_write_success = write_voltages_0(voltages_0);
      }
    }

    if (pico == 1 && use_pico1 == 1 && write_data_1 == 1) {
      int current_write_success = write_currents_1(common->all_currents);
      int voltage_write_success = write_voltages_1(voltages_1);
    }
    
  }
}




int lv_initialization() {
  char error_msg[100];

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
    if (MCP_pinMode(lvpgoodMCP, powerChMap[i], OUTPUT) == -1) {
      sprintf(error_msg, "lv_initialization MCP_pinMode pin %u failure", powerChMap[i]);
      error_log(error_msg);
      printf(error_msg);

      return -1;
    }

    if (MCP_pinWrite(lvpgoodMCP, powerChMap[i],0) == -1) {
      sprintf(error_msg, "lv_initialization MCP_pinWrite pin %u failure", powerChMap[i]);
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



void sigintHandler(int sig_num) {
  /* Reset handler to catch SIGINT next time. 
  Refer http://en.cppreference.com/w/c/program/signal */
  signal(SIGINT, sigintHandler);

  pthread_mutex_destroy(&usb0_mutex_lock);
  pthread_mutex_destroy(&usb1_mutex_lock);


  sleep(0.1);
  
  if (use_pico0 == 1) {
    pthread_cancel(acquisition_thread_0);
    //pthread_cancel(status_thread_0);
  }

  if (use_pico1 == 1) {
    pthread_cancel(acquisition_thread_1);
  }

  pthread_cancel(command_execution_thread);
  pthread_cancel(socket_creation_thread);

  sleep(1);

  if (use_pico0 == 1) {
    libusb_device *device_0 = libusb_get_device(device_handle_0);
    libusb_unref_device(device_0);
    free(device_handle_0);

    if (write_data_0 == 1) {
      fclose(fp_I_0);
      fclose(fp_V_0);
    }
  }

  if (use_pico1 == 1) {
    libusb_device *device_1 = libusb_get_device(device_handle_1);
    libusb_unref_device(device_1);
    free(device_handle_1);

    if (write_data_1 == 1) {
      fclose(fp_I_1);
      fclose(fp_V_1);
    }
  }

  free(hvMCP);
  free(lvpgoodMCP);
} 



int main( int argc, char **argv ) {
  char error_msg[100];

  // initialize mutexes
  pthread_mutex_init(&usb0_mutex_lock, NULL);
  pthread_mutex_init(&usb1_mutex_lock, NULL);

  // initialize queues
  const char *pathname = "/home/mu2e/LVHVBox/CServer/build";
  queue_id = 0;
  queue_key = ftok(pathname, queue_id);
  msqid = msgget(queue_key, IPC_CREAT);

  pico_queue_id = 1;
  pico_queue_key = ftok(pathname, pico_queue_id);
  pico_msqid = msgget(pico_queue_key, IPC_CREAT);




  hvMCP=(MCP*)malloc(sizeof(struct MCP*));
  lvpgoodMCP=(MCP*)malloc(sizeof(struct MCP*));

  signal(SIGINT, sigintHandler); 
  signal(SIGPIPE, SIG_IGN);


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


  
  
// Export the GPIO pins

  if (setup_gpio(lv_mcp_reset) == -1) {
    error_log("main setup_gpio lv_mcp_reset failure");
    printf("main setup_gpio lv_mcp_reset failure");

    return 1;
  }

  // Turn off the GPIO pin (set it to 1)
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

  
  if (MCP_setup(hvMCP,2) == -1) {
    error_log("main MCP_set hvMCP failure");
    printf("main MCP_set hvMCP failure");

    return -1;
  } else if (MCP_setup(lvpgoodMCP,1) == -1) {
    error_log("main MCP_set lvpgoodMCP failure");
    printf("main MCP_set lvpgoodMCP failure");

    return -1;
  }
  

  if (hv_initialization() == -1) {
    error_log("HV Initialization failure, program will terminate");
    printf("HV Initialization failure, program will terminate");

    return -1;
  } else if (lv_initialization() == -1) {
    error_log("LV Initialization failure, program will terminate");
    printf("LV Initialization failure, program will terminate");

    return -1;
  }

  FILE *file = fopen(LIVE_STATUS_FILENAME, "w");
  fclose(file);

  for (int i = 0; i < 6; i++) {
    // writes 1
    if (write_fixed_location(LIVE_STATUS_FILENAME, 2 * i, 0) == -1) {
      return -1;
    }
  }

  // ----- initialize pico 0 communications, etc ----- //
  arg_struct args_0;
  args_0.pico = 0;

  arg_struct args_1;
  args_1.pico = 1;



  if (libusb_init(NULL) != 0) {
    error_log("libusb_init failure");
    printf("libusb_init failure");

    return 0;
  }



  
  device_handle_0 = libusb_open_device_with_vid_pid(NULL, VENDOR_ID_0, PRODUCT_ID);
  if (device_handle_0 == NULL) {
    use_pico0 = 0;
    printf("Pico 0 will not be used.\n");
  }

  device_handle_1 = libusb_open_device_with_vid_pid(NULL, VENDOR_ID_1, PRODUCT_ID);
  if (device_handle_1 == NULL) {
    use_pico1 = 0;
    printf("Pico 1 will not be used.\n");
  }
  

  // create data acquisition thread
  if (use_pico0 == 1) {
    pthread_create(&acquisition_thread_0, NULL, acquire_data, &args_0);
  }
  if (use_pico1 == 1) {
    pthread_create(&acquisition_thread_1, NULL, acquire_data, &args_1);
  }

  // create statusing thread
  if (use_pico0 == 1) {
    pthread_create(&status_thread_0, NULL, live_status, &args_0);
  }

  // create socket initialization thread
  pthread_create(&socket_creation_thread, NULL, create_connections, NULL);

  // create hv execution thread
  pthread_create(&command_execution_thread, NULL, command_execution, NULL);

  pause();

  return 0;
}
