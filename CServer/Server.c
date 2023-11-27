#include <libusb-1.0/libusb.h>
#include <libudev.h>

// C library headers
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <math.h>

#include <pthread.h>

// Linux headers
#include <fcntl.h>   // Contains file controls like O_RDWR
#include <errno.h>   // Error integer and strerror() function
#include <termios.h> // Contains POSIX terminal control definitions
#include <unistd.h>  // write(), read(), close()

#include <time.h>
#include <inttypes.h>

#include <sys/socket.h>
#include <netinet/in.h>

#include <signal.h> 

#include <mcp23s08.h>
#include <softPwm.h>
#include <linux/spi/spidev.h>
#include "dac8164.h"

#include "MCP23S08.h"
#include "gpio.h"
#include "utils.h"

#include <sys/ioctl.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <i2c/smbus.h>
#include "i2cbusses.h"

#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <errno.h>

#define LVPINBASE 1000 // LV mcp pin base
#define HVPINBASE 2000 // HV mcp pin base

// ----- libusb constants and variables ----- //
#define HISTORY_LENGTH 100
#define VENDOR_ID_0 0xcaf0
#define VENDOR_ID_1 0xcaf1
#define PRODUCT_ID 0x4003

uint8_t usb0_lock = 0;
uint8_t usb1_lock = 0;
uint8_t desire_lock_0 = 0;
uint8_t desire_lock_1 = 0;
struct libusb_device_handle *device_handle_0 = NULL;
struct libusb_device_handle *device_handle_1 = NULL;

// socket constant
#define PORT 12000

DAC8164 dac[3]; // HV DAQ objects

// variables to store LV i2c connection info
int lv_i2cbus;
static int lv_i2c = 0;

// thread locking vars
pthread_mutex_t lock;
pthread_mutex_t usb0_mutex_lock;
pthread_mutex_t usb1_mutex_lock;

// assorted values to be returned upon client request
float voltages_0[6];
float voltages_1[6];

float currents_0[6];
float currents_1[6];

// LV channel information
uint8_t powerChMap[6] = {5, 6, 7, 2, 3, 4};
uint8_t lv_mcp_reset = 3;
uint8_t lv_global_enable = 18;

typedef struct
{
  float all_currents[6][HISTORY_LENGTH];
  float all_currents_stored[6][HISTORY_LENGTH];
  uint8_t array_indicator;
  uint8_t pico;
} arg_struct;

// ----- Structures used in server communications with clients ----- //
typedef struct
{
  char command_name;
  char command_type;
  uint8_t char_parameter;
  float float_parameter;
  int client_addr;
} command;


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

const char *LIVE_STATUS_FILENAME = "live_status.txt";

#define PIPE_PATH "/tmp/data_pipe"
#define V_PIPE_PATH "/tmp/vdata_pipe"
#define ALPHA 0.1 // Choose a value between 0 and 1. Smaller values result in heavier filtering.
#define DECIMATION_FACTOR 5


float i2c_ltc2497(int address, int channelLTC)
{

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
    printf("Failed to write to the i2c bus.\n");
    return -1;
  }

  msleep(500);

  //----- READ BYTES -----
  length = 3;                                //<<< Number of bytes to read
  if (read(lv_i2c, block, length) != length) // read() returns the number of bytes actually read, if it doesn't match then an error occurred (e.g. no response from the device)
  {
    // ERROR HANDLING: i2c transaction failed
    printf("Failed to read from the i2c bus.\n");
    return -1;
  }

  uint32_t val = ((block[0] & 0x3f) << 16) + (block[1] << 8) + (block[2] & 0xE0);

  return val * vref / max_reading;
}



void powerOn(uint8_t channel) {

  write_gpio_value(lv_global_enable, HIGH);
  
  if (channel == 6) {
    for (int i=0; i<6; i++) {
      MCP_pinWrite(lvpgoodMCP, powerChMap[i], HIGH);
    }
  } else {
    MCP_pinWrite(lvpgoodMCP, powerChMap[channel], HIGH);
    

  }

}

void powerOff(uint8_t channel) {
  if (channel == 6) {
    write_gpio_value(lv_global_enable, LOW);
    
    for (int i=0; i<6; i++) {
      MCP_pinWrite(lvpgoodMCP, powerChMap[i], LOW);
    }
  } else {
    MCP_pinWrite(lvpgoodMCP, powerChMap[channel], LOW);
  }
}

void hv_initialization(){
  MCP_pinMode(hvMCP, 4, OUTPUT);
  MCP_pinMode(hvMCP, 4, LOW);

  MCP_pinMode(hvMCP, 2, OUTPUT);
  MCP_pinWrite(hvMCP, 2, LOW);

  DAC8164_setup (&dac[0], hvMCP, 6, 7, 0, -1, -1);
  DAC8164_setup (&dac[1], hvMCP, 3, 7, 0, -1, -1);
  DAC8164_setup (&dac[2], hvMCP, 5, 7, 0, -1, -1);

}

void set_hv(int channel, float value)
{
  int idac = (int)(channel / 4);

  float alpha = 1.;
  if (channel == 0)
    alpha = 0.90;
  if (channel == 1)
    alpha = 0.90;
  if (channel == 2)
    alpha = 0.885;
  if (channel == 3)
    alpha = 0.90;
  if (channel == 4)
    alpha = 0.9012;
  if (channel == 5)
    alpha = 0.9034;
  if (channel == 6)
    alpha = 0.9009;
  if (channel == 7)
    alpha = 0.9027;
  if (channel == 8)
    alpha = 0.8977;
  if (channel == 9)
    alpha = 0.9012;
  if (channel == 10)
    alpha = 0.9015;
  if (channel == 11)
    alpha = 1.; // BURNED BOARD - FIX ME!!

  uint32_t digvalue = ((int)(alpha * 16383. * (value / 1631.3))) & 0x3FFF;

  DAC8164_writeChannel(&dac[idac], channel, digvalue);
}


// variables to manage command queue
# define SIZE 100


command incoming_commands[SIZE];
int command_array[SIZE];
int Rear = -1;
int Front = 0;

command add_command;

void enqueue(command array[SIZE], command insert_item) {
    if (Rear == SIZE - 1)
       printf("Overflow \n");
    else
    {      
        Rear = Rear + 1;
        array[Rear] = insert_item;
    }
} 
 
void dequeue(command array[SIZE]) {
    if (Front == - 1 || Front > Rear) {
        printf("Underflow \n");
        return ;
    } else {
      for (int i=0; i<SIZE-1; i++) {
        array[i] = array[i+1];
      }
    }
    Rear -= 1;
}


// assorted command functions

// get_vhv
void get_vhv(uint8_t channel, int client_addr) {
  float return_val;

  if (channel < 6) {
    return_val = voltages_0[channel];
  } else {
    return_val = voltages_1[channel - 6];
  }

  int float_channel = (int)channel;

  write(client_addr, &return_val, sizeof(&return_val));
}

// get_ihv
void get_ihv(uint8_t channel, int client_addr)
{
  float return_val;
  if (channel < 6) {
    return_val = currents_0[channel];
  } else {
    return_val = currents_1[channel - 6];
  }

  write(client_addr, &return_val, sizeof(&return_val));
}

// rampHV
void ramp_hv(uint8_t channel, float voltage) {
  printf("In ramp \n");
  printf("desired voltage: %f \n", voltage);
  int idac = (int)(channel / 4);
  float increment = voltage / NSTEPS;
  float current_value = 0;

  for (int itick=0; itick<NSTEPS; itick++) {
    usleep(50000);
    current_value += increment;

    set_hv(channel, current_value);
  }
}


void down_hv(uint8_t channel) {
  float current_voltage;
  if (channel < 6)
  {
    current_voltage = voltages_0[channel];
  }
  else
  {
    current_voltage = voltages_1[channel - 6];
  }

  int idac = (int)(channel / 4);
  float increment = current_voltage / NSTEPS;

  for (int itick = 0; itick < NSTEPS; itick++)
  {
    usleep(50000);
    current_voltage -= increment;
    set_hv(channel, current_voltage);
  }

  set_hv(channel,0);

}

// trip
void trip(uint8_t channel, int client_addr)
{
  uint8_t send_val = 103 + (channel % 6);

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
  }
}

// reset_trip
void reset_trip(uint8_t channel, int client_addr)
{
  uint8_t send_val = 109 + (channel % 6);

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, sizeof(send_val), 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, sizeof(send_val), 0, 0);
  }
}

// disable_trip
void disable_trip(uint8_t channel, int client_addr)
{
  uint8_t send_val = 115 + (channel % 6);

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
  }
}

// enable_trip
void enable_trip(uint8_t channel, int client_addr)
{
  uint8_t send_val = 121 + (channel % 6);

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
  }
}

// enable_ped
void enable_ped(uint8_t channel, int client_addr)
{
  uint8_t send_val = 34;

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
  }
}

// disable_ped
void disable_ped(uint8_t channel, int client_addr)
{
  uint8_t send_val = 35;

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
  }
}


// trip_status
void trip_status(uint8_t channel, int client_addr)
{
  uint8_t send_val = 33;

  char *input_data;
  input_data = (char *)malloc(1);

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_0, 0x82, input_data, sizeof(input_data), 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val, 1, 0, 0);
    libusb_bulk_transfer(device_handle_1, 0x82, input_data, sizeof(input_data), 0, 0);
  }

  int return_val = 1;

  if ((*input_data & 1 << (channel)) == 0)
  {
    return_val = 0;
  }

  if (client_addr != -9999)
    write(client_addr, &return_val, sizeof(&return_val));
  else
    write_fixed_location(LIVE_STATUS_FILENAME, 2 * channel, return_val); // writes at fixed location
}

// set_trip
void set_trip(uint8_t channel, float value, int client_addr)
{
  uint8_t send_val[3];
  send_val[0] = 76 + (channel % 6);

  uint16_t send_int;
  send_int = (uint16_t)(value / 1000 * 65535);
  printf("send int: %u \n", (unsigned int)send_int);

  uint8_t right_mask = -1;

  send_val[1] = send_int >> 8 & right_mask;
  send_val[2] = send_int & right_mask;

  uint16_t one = send_val[1] << 8;
  uint16_t two = send_val[2] + one;

  if (channel < 6)
  {
    libusb_bulk_transfer(device_handle_0, 0x02, &send_val[0], sizeof(send_val), 0, 0);
  }
  else
  {
    libusb_bulk_transfer(device_handle_1, 0x02, &send_val[0], sizeof(send_val), 0, 0);
  }
}

// readMonV48
void readMonV48(uint8_t channel, int client_addr)
{
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t v48map[6] = {6, 0, 6, 0, 6, 0};

  float v48scale = 0.0012089;
  float acplscale = 8.2;

  uint8_t index = v48map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  float ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (v48scale * acplscale);

  write(client_addr, &ret, sizeof(&ret));
}

// readMonI48
void readMonI48(uint8_t channel, int client_addr)
{
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t i48map[6] = {7, 1, 7, 1, 7, 1};

  float i48scale = 0.010;
  float acplscale = 8.2;

  uint8_t index = i48map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  float ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (i48scale * acplscale);

  write(client_addr, &ret, sizeof(&ret));
}

// readMonV6
void readMonV6(uint8_t channel, int client_addr)
{
  uint8_t v6map[6] = {4, 3, 4, 3, 4, 3};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};

  float v6scale = 0.00857905;
  float acplscale = 8.2;

  uint8_t index = v6map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  float ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (v6scale * acplscale);
  printf("return val: %f \n", ret);

  write(client_addr, &ret, sizeof(&ret));
}

// readMonI6
void readMonI6(uint8_t channel, int client_addr)
{
  uint8_t addresses[3] = {0x14, 0x16, 0x26};
  uint8_t LTCaddress[6] = {0x26, 0x26, 0x16, 0x16, 0x14, 0x14};
  uint8_t i6map[6] = {5, 2, 5, 2, 5, 2};

  float i6scale = 0.010;
  float acplscale = 8.2;

  uint8_t index = i6map[channel];
  uint8_t channelLTC = (5 << 5) + index;
  uint8_t address = LTCaddress[channel];

  float ret = i2c_ltc2497(address, channelLTC);
  ret = ret / (i6scale * acplscale);

  write(client_addr, &ret, sizeof(&ret));
}

void *hv_request() {
  while (1) {
    command *check_command = &incoming_commands[Front];
    char current_command = check_command->command_name;
    char current_type = check_command->command_type;
    uint8_t char_parameter = (uint8_t)check_command->char_parameter;
    float float_parameter = check_command->float_parameter;
    int client_addr = check_command->client_addr;

    // check if command is hv type, else do nothing
    if (current_type == 'a')
    {
      // select proper hv function
      if (current_command == 'a') { // get_vhv
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        get_vhv(char_parameter, client_addr);
      } else if (current_command == 'b') { // get_ihv
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        get_ihv(char_parameter, client_addr);
      }
    }
    sleep(0.1);
  }
}

// acquire and execute commands in loop
void *hv_execution() {
  while (1)
  {
    command *check_command = &incoming_commands[Front];
    char current_command = check_command->command_name;
    char current_type = check_command->command_type;
    uint8_t char_parameter = (uint8_t)check_command->char_parameter;
    float float_parameter = check_command->float_parameter;
    int client_addr = check_command->client_addr;

    // check if command is hv type, else do nothing
    if (current_type == 'a') {
      // select proper hv function
      if (current_command == 'c') { // ramp_hv
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        ramp_hv(char_parameter, float_parameter);

      } else if (current_command == 'd') { // down_hv

        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        down_hv(char_parameter);
      }
    }

    sleep(0.1);
  }
}

// acquire and execute commands in loop
void *lv_execution() {
  while (1) {
    char current_command = incoming_commands[0].command_name;
    char current_type = incoming_commands[0].command_type;
    uint8_t char_parameter = incoming_commands[0].char_parameter;
    float float_parameter = incoming_commands[0].float_parameter;
    int client_addr = incoming_commands[0].client_addr;

    // check if command is hv type, else do nothing
    if (current_type == 'b')
    {

      // select proper lv function
      if (current_command == 'g') { // readMonV48
        readMonV48(char_parameter, client_addr);
      } else if (current_command == 'h') { // readMonI48
        readMonI48(char_parameter, client_addr);
      } else if (current_command == 'i') { // readMonV6
        readMonV6(char_parameter, client_addr);
      } else if (current_command == 'j') { // readMonI6
        readMonI6(char_parameter, client_addr);
      } else if (current_command == 'e') { // powerOn
        powerOn(char_parameter);
      } else if (current_command == 'f') { // powerOff
        powerOff(char_parameter);
      }

      pthread_mutex_lock(&lock);
      dequeue(incoming_commands);
      pthread_mutex_unlock(&lock);
    }

    sleep(1);
  }
}

// ----- Code to handle socket stuff ----- //
void *handle_client(void *args) {
  client_data *client_information = args;

  int inner_socket = client_information->client_addr;

  char buffer[9];
  char flush_buffer[1];

  while (1)
  {
    // read command into buffer
    int return_val = read(inner_socket, buffer, 9);
    // read(inner_socket, NULL, 1);

    // if return_val is -1, terminate thread
    if (return_val == 0) {

      printf("Thread terminated \n");
      return 0;
    }

    if (return_val == 9)
    {
      printf("Received Command: %s \n", buffer);

      // acquire lock
      pthread_mutex_lock(&lock);

      // create command

      add_command.command_name = buffer[0];
      add_command.command_type = buffer[1];
      add_command.char_parameter = buffer[2] - 97;
      add_command.float_parameter = atof(&buffer[3]);
      printf("float parameter: %f \n", add_command.float_parameter);
      add_command.client_addr = inner_socket;

      // add command to queue
      enqueue(incoming_commands, add_command);

      // release lock
      pthread_mutex_unlock(&lock);
    }
  }
}

// ----- Code to handle socket stuff ----- //
void *live_status(void *args)
{
  char buffer[9];
  char flush_buffer[1];

  while (1)
  {

    for (int ichannel = 0; ichannel < 6; ichannel++)
    {
      // acquire lock
      pthread_mutex_lock(&lock);

      // create command
      add_command.command_name = 'o';
      add_command.command_type = 'c';
      add_command.char_parameter = ichannel;
      add_command.float_parameter = 0;
      add_command.client_addr = -9999;

      // add command to queue
      enqueue(incoming_commands, add_command);

      // release lock
      pthread_mutex_unlock(&lock);
    }
    sleep(1);
  }
}

void *create_connections()
{

  int server_fd, new_socket, valread;
  struct sockaddr_in address;
  int opt = 1;
  int addrlen = sizeof(address);

  // Creating socket file descriptor
  if ((server_fd = socket(AF_INET, SOCK_STREAM, 0)) < 0)
  {
    perror("socket failed");
    exit(EXIT_FAILURE);
  }

  // Forcefully attaching socket to the port 8080
  if (setsockopt(server_fd, SOL_SOCKET,
                 SO_REUSEADDR | SO_REUSEPORT, &opt,
                 sizeof(opt)))
  {
    perror("setsockopt");
    exit(EXIT_FAILURE);
  }
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = INADDR_ANY;
  address.sin_port = htons(PORT);

  // Forcefully attaching socket to the port 8080
  if (bind(server_fd, (struct sockaddr *)&address,
           sizeof(address)) < 0)
  {
    perror("bind failed");
    exit(EXIT_FAILURE);
  }
  if (listen(server_fd, 3) < 0)
  {
    perror("listen");
    exit(EXIT_FAILURE);
  }

  while (1)
  {
    if ((new_socket = accept(server_fd, (struct sockaddr *)&address,
                             (socklen_t *)&addrlen)) < 0)
    {
      perror("accept");
      exit(EXIT_FAILURE);
    }
    printf("inside\n");

    pthread_t client_thread;
    pthread_create(&client_thread, NULL, handle_client, &new_socket);
  }
}

// ----- Code to handle HV data acquisition & storage ----- //

void *acquire_data(void *arguments)
{
  arg_struct *common = arguments;

  uint8_t pico = common->pico;


  // Initialize libusb
  int result = libusb_init( NULL );
  if ( result < 0 )
  {
      printf( "Error initializing libusb: %s\n", libusb_error_name( result ) );
      exit( -1 );
  }

  // Set debugging output to max level
	libusb_set_option( NULL, LIBUSB_OPTION_LOG_LEVEL, LIBUSB_LOG_LEVEL_WARNING );

  // Open our ADU device that matches our vendor id and product id
  if (pico == 0)
  {
    device_handle_0 = libusb_open_device_with_vid_pid(NULL, VENDOR_ID_0, PRODUCT_ID);
    libusb_set_auto_detach_kernel_driver(device_handle_0, 1);
    // Claim interface 0 on the device
    result = libusb_claim_interface(device_handle_0, 1);
  }
  else
  {
    device_handle_1 = libusb_open_device_with_vid_pid(NULL, VENDOR_ID_1, PRODUCT_ID);
    libusb_set_auto_detach_kernel_driver(device_handle_1, 1);
    // Claim interface 0 on the device
    result = libusb_claim_interface(device_handle_1, 1);
  }

  uint16_t inner_loop = 1;

  char current_char = 'H';
  char voltage_char = 'V';

  char *input_data;
  input_data = (char *)malloc(64 * inner_loop);

  char *voltage_input_data;
  voltage_input_data = (char *)malloc(24);

  float floatval = 0;
  float floatval_voltage = 0;

  uint8_t allow_read = 1;

  struct stat st;
  if (stat(V_PIPE_PATH, &st) == -1)
  {
    if (mkfifo(V_PIPE_PATH, 0666) == -1)
    {
      perror("Failed to create named pipe");
    }
  }

  int vfd = open(V_PIPE_PATH, O_WRONLY | O_NONBLOCK);
  if (vfd == -1)
  {
    perror("Error opening pipe");
  }

  while (1)
  {
    command *check_command = &incoming_commands[Front];
    char current_command = check_command->command_name;
    char current_type = check_command->command_type;
    uint8_t char_parameter = (uint8_t)check_command->char_parameter;
    float float_parameter = check_command->float_parameter;
    int client_addr = check_command->client_addr;

    // check if command is pico type, else do nothing
    if (current_type == 'c')
    {

      // select proper hv function
      if (current_command == 'k')
      { // trip
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        trip(char_parameter, client_addr);
      }
      else if (current_command == 'l')
      { // reset trip
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        reset_trip(char_parameter, client_addr);
      }
      else if (current_command == 'm')
      { // disable trip
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        disable_trip(char_parameter, client_addr);
      }
      else if (current_command == 'n')
      { // enable trip
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        enable_trip(char_parameter, client_addr);
      }
      else if (current_command == 'p')
      { // set trip
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        set_trip(char_parameter, float_parameter, client_addr);
      }
      else if (current_command == 'o')
      { // trip status
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        trip_status(char_parameter, client_addr);
      }
      else if (current_command == '%')
      { // enable ped
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        enable_ped(char_parameter, client_addr);
      }
      else if (current_command == '&')
      { // disable ped
        pthread_mutex_lock(&lock);
        dequeue(incoming_commands);
        pthread_mutex_unlock(&lock);
        disable_ped(char_parameter, client_addr);
      }
    }

    // check if other pico command needs to be sent
    if (pico == 0)
    {
      if (usb0_lock == 0 && desire_lock_0 == 0)
      {
        allow_read = 1;
        pthread_mutex_lock(&usb0_mutex_lock);
        usb0_lock = 1;
        pthread_mutex_unlock(&usb0_mutex_lock);
      }
      else
      {
        allow_read = 0;
      }
    }
    else
    {
      if (usb1_lock == 0 && desire_lock_1 == 0)
      {
        allow_read = 1;
        pthread_mutex_lock(&usb1_mutex_lock);
        usb1_lock = 1;
        pthread_mutex_unlock(&usb1_mutex_lock);
      }
      else
      {
        allow_read = 0;
      }
    }

    if (allow_read == 1) {

      char *filename_V;

      // fill up array
      for (uint16_t time_index = 0; time_index < HISTORY_LENGTH;)
      {
        if (pico == 0)
        {
          libusb_bulk_transfer(device_handle_0, 0x02, &current_char, 1, 0, 0);
          libusb_bulk_transfer(device_handle_0, 0x82, input_data, 48, 0, 0);
        }
        else
        {
          libusb_bulk_transfer(device_handle_1, 0x02, &current_char, 1, 0, 0);
          libusb_bulk_transfer(device_handle_1, 0x82, input_data, 48, 0, 0);
        }

        // check if new data from SmartSwitch
        floatval = *(float *)&input_data[0];
        if (floatval != -100)
        {

          for (uint32_t i = 0; i < 12; i++)
          {
            floatval = *(float *)&input_data[4 * i];

            if (i < 6)
            {
              common->all_currents[i][time_index] = floatval;
            }
            else
            {
              common->all_currents[i - 6][time_index + 1] = floatval;
            }
          }
          time_index += 2;
        }
      }

      if (pico == 0)
      {
        for (uint8_t i = 0; i < 6; i++)
        {
          currents_0[i] = *common->all_currents[i];
        }
        filename_V = "../Voltages_0.txt";
      }
      else
      {
        for (uint8_t i = 0; i < 6; i++)
        {
          currents_1[i] = *common->all_currents[i];
        }
        filename_V = "../Voltages_1.txt";
      }

      // copy array to storage array
      for (uint8_t channel = 0; channel < 6; channel++)
      {
        for (uint16_t time = 0; time < HISTORY_LENGTH; time++)
        {
          memcpy(&common->all_currents_stored[channel][time], &common->all_currents[channel][time], sizeof(&common->all_currents[channel][time]));
        }
      }
      common->array_indicator += 1;

      // ----- Request and store one voltage value -----

      if (pico == 0)
      {
        libusb_bulk_transfer(device_handle_0, 0x02, &voltage_char, 1, 0, 0);
        libusb_bulk_transfer(device_handle_0, 0x82, voltage_input_data, 24, 0, 0);
        usb0_lock = 0;
      }
      else
      {
        libusb_bulk_transfer(device_handle_1, 0x02, &voltage_char, 1, 0, 0);
        libusb_bulk_transfer(device_handle_1, 0x82, voltage_input_data, 24, 0, 0);
        usb1_lock = 0;
      }

      if (pico == 0)
      {
        for (uint32_t i = 0; i < 6; i++)
        {
          floatval_voltage = *(float *)&voltage_input_data[4 * i];
          voltages_0[i] = floatval_voltage;
        }
      }
      else
      {
        for (uint32_t i = 0; i < 6; i++)
        {
          floatval_voltage = *(float *)&voltage_input_data[4 * i];
          voltages_1[i] = floatval_voltage;
        }
      }

      // save voltages in txt file

      FILE *fp_V = fopen(filename_V, "a");
      if (fp_V == NULL)
      {
        printf("Error opening the voltage file %s", filename_V);
      }
      time_t seconds;

      // append to voltages txt file
      if (pico == 0)
      {
        char buffer[1024]; // A buffer to format and write data
        for (int channel = 0; channel < 6; channel++)
        {
          fprintf(fp_V, "%f ", voltages_0[channel]);
          int length = snprintf(buffer, sizeof(buffer), "%f ", voltages_0[channel]);
          write(vfd, buffer, length); // Write to the pipe
        }
      }
      else
      {
        for (int channel = 0; channel < 6; channel++)
        {
          fprintf(fp_V, "%f ", voltages_1[channel]);
        }
      }
      seconds = time(NULL);
      fprintf(fp_V, "%f\n", (float)seconds);


      if (pico == 0)
      {
        char buffer[1024]; // A buffer to format and write data
        int length = snprintf(buffer, sizeof(buffer), "\n");
        write(vfd, buffer, length); // Write to the pipe
      }

      fclose(fp_V);
    }
  }
}

void *save_txt(void *arguments)
{
  char *filename_I;
  char *filename_V;

  arg_struct *common = arguments;

  time_t seconds;

  uint8_t pico = common->pico;

  uint8_t old_array_indicator = 0;

  float store_all_currents_internal[6][HISTORY_LENGTH];

  float last_output[6] = {0}; // State for each channel's filter
  struct stat st;
  if (stat(PIPE_PATH, &st) == -1)
  {
    if (mkfifo(PIPE_PATH, 0666) == -1)
    {
      perror("Failed to create named pipe");
    }
  }

  int fd = open(PIPE_PATH, O_WRONLY | O_NONBLOCK);
  if (fd == -1)
  {
    perror("Error opening pipe");
  }

  if (pico == 0)
  {
    filename_I = "../Currents_0.txt";
  }
  else
  {
    filename_I = "../Currents_1.txt";
  }

  FILE *fp_I = fopen(filename_I, "w");
  if (fp_I == NULL)
  {
    printf("Error opening the current file %s", filename_I);
  }

  while (1)
  {
    uint8_t array_indicator = common->array_indicator;

    if (array_indicator != old_array_indicator)
    {
      old_array_indicator = array_indicator;

      for (uint8_t channel = 0; channel < 6; channel++)
      {
        for (uint16_t time = 0; time < HISTORY_LENGTH; time++)
        {
          memcpy(&store_all_currents_internal[channel][time], &common->all_currents_stored[channel][time], sizeof(&common->all_currents_stored[channel][time]));
        }
      }

      // open the current file for writing
      if (pico == 0)
      {

        char buffer[1024]; // A buffer to format and write data
        time_t seconds;

        for (uint32_t time_index = 0; time_index < HISTORY_LENGTH; time_index++)
        {
          for (uint8_t channel = 0; channel < 6; channel++)
          {
            // Apply the first-order low-pass filter
            float input_value = store_all_currents_internal[channel][time_index];
            float filtered_value = ALPHA * input_value + (1 - ALPHA) * last_output[channel];
            last_output[channel] = filtered_value;

            // Decimation by 5: Only write every 5th sample
            if (time_index % DECIMATION_FACTOR == 0)
            {
              int length = snprintf(buffer, sizeof(buffer), "%f ", filtered_value);
              fprintf(fp_I, "%f ", filtered_value);
              write(fd, buffer, length); // Write to the pipe
            }
          }

          if (time_index % DECIMATION_FACTOR == 0)
          {
            int length = snprintf(buffer, sizeof(buffer), "\n");
            fprintf(fp_I, "\n");
            write(fd, buffer, length); // Write the timestamp to the pipe
          }
        }

        /*

              for (uint32_t time_index=0; time_index<HISTORY_LENGTH; time_index++) {
                for (uint8_t channel=0; channel<6; channel++) {
                  fprintf(fp_I, "%f ", store_all_currents_internal[channel][time_index]);
                }
                seconds = time(NULL);
                fprintf(fp_I, "%f\n", (float)seconds);
              }

              // close the current file
              fclose(fp_I);
        */
      }
    }
  }
  fclose(fp_I);
}



int lv_initialization() {
  export_gpio(lv_global_enable);
  set_gpio_direction_out(lv_global_enable);
  write_gpio_value(lv_global_enable, LOW);

  for (int i=0; i<6; i++) {
    MCP_pinMode(lvpgoodMCP, powerChMap[i], OUTPUT);

    MCP_pinWrite(lvpgoodMCP, powerChMap[i],0);
  }


  int file;
  int i;
  int res;
  int oldvalue;

  char lv_i2cname[20];

  lv_i2cbus = lookup_i2c_bus("3");
  sprintf(lv_i2cname, "/dev/i2c-%d", 3);
  lv_i2c = open_i2c_dev(lv_i2cbus, lv_i2cname, sizeof(lv_i2cname), 0);
}







int main( int argc, char **argv ) {
  hvMCP=(MCP*)malloc(sizeof(struct MCP*));
  lvpgoodMCP=(MCP*)malloc(sizeof(struct MCP*));



  char *test_var = load_config("CServer_Path");
  printf("CServer Path: %s\n",test_var);



  /**
   * @brief setup SPI comm
   * 
   */

  if ((spiFds = open (spidev, O_RDWR)) < 0){
    printf("Unable to open SPI device: %s\n",spidev);
    return 0;
  }

  if (ioctl (spiFds, SPI_IOC_WR_MODE, &spi_mode)            < 0){
    printf("SPI Mode Change failure: %s\n",spidev);
    return 0;
  }

  if (ioctl (spiFds, SPI_IOC_WR_BITS_PER_WORD, &spi_bpw) < 0){
    printf("SPI BPW Change failure: %s\n",spidev);
    return 0;
  }

  if (ioctl (spiFds, SPI_IOC_WR_MAX_SPEED_HZ, &spi_speed)   < 0){
    printf("SPI Speed Change failure: %s\n",spidev);
    return 0;
  }


/**
 * @brief setup MCPs with their appropriate addresses
 * 
 */
  
// Export the GPIO pins

    if (export_gpio(lv_mcp_reset) == -1) {
        return 1;
    }


// Set the GPIO pin direction to "out"
    if (set_gpio_direction_out(lv_mcp_reset) == -1) {
        return 1;
    }


    
    // Turn off the GPIO pin (set it to 1)
    if (write_gpio_value(lv_mcp_reset, 0) == -1) {
        return 1;
    }

    // Turn on the GPIO pin (set it to 1)
    if (write_gpio_value(lv_mcp_reset, 1) == -1) {
        return 1;
    }

  
  MCP_setup(hvMCP,2);
  MCP_setup(lvpgoodMCP,1);
  

  hv_initialization();
  lv_initialization();


  FILE *file = fopen(LIVE_STATUS_FILENAME, "w");
  fclose(file);

  for (int i = 0; i < 6; i++)
  {
    write_fixed_location(LIVE_STATUS_FILENAME, 2 * i, 0); // writes 1
  }

  // ----- initialize pico 0 communications, etc ----- //
  arg_struct args_0;
  args_0.array_indicator = 0;
  args_0.pico = 0;

  // create data acquisition thread
  pthread_t acquisition_thread_0;
  pthread_create(&acquisition_thread_0, NULL, acquire_data, &args_0);

  // create statusing thread
  pthread_t status_thread_0;
  pthread_create(&status_thread_0, NULL, live_status, &args_0);

  // create txt save thread
  pthread_t save_thread_0;
  pthread_create(&save_thread_0, NULL, save_txt, &args_0);

  // ----- initialize pico 1 communications, etc ----- //
  /*
  struct arg_struct args_1;
  args_1.array_indicator = 0;
  args_1.pico = 1;

  // create data acquisition thread
  pthread_t acquisition_thread_1;
  pthread_create(&acquisition_thread_1, NULL, acquire_data, &args_1);

  // create txt save thread
  pthread_t save_thread_1;
  pthread_create(&save_thread_1, NULL, save_txt, &args_1);
  */

  // create socket initialization thread
  pthread_t socket_creation_thread;
  pthread_create(&socket_creation_thread, NULL, create_connections, NULL);

  // create hv execution thread
  pthread_t hv_execution_thread;
  pthread_create(&hv_execution_thread, NULL, hv_execution, NULL);

  // create hv request thread
  pthread_t hv_request_thread;
  pthread_create(&hv_request_thread, NULL, hv_request, NULL);

  // create lv command execution thread
  pthread_t lv_command_thread;
  pthread_create(&lv_command_thread, NULL, lv_execution, NULL);

  while (1)
  {
    sleep(100);
  }

  // pthread_cancel(acquisition_thread_0);
  // pthread_cancel(save_thread_0);

  // pthread_cancel(acquisition_thread_1);
  // pthread_cancel(save_thread_1);

  // pthread_cancel(socket_creation_thread);

  return 0;
}
