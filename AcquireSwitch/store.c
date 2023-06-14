// C library headers
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include <math.h>

// Linux headers
#include <fcntl.h> // Contains file controls like O_RDWR
#include <errno.h> // Error integer and strerror() function
#include <termios.h> // Contains POSIX terminal control definitions
#include <unistd.h> // write(), read(), close()


const float adc_to_uA = 2.048 / pow(2, 15) / 8200.0 * 1.E6;


void main() {
  int serial_port = open("/dev/ttyACM0", O_RDWR);

  // Check for errors
  if (serial_port < 0) {
      printf("Error %i from open: %s\n", errno, strerror(errno));
  }







  struct termios tty;

  // Read in existing settings, and handle any error
  // NOTE: This is important! POSIX states that the struct passed to tcsetattr()
  // must have been initialized with a call to tcgetattr() overwise behaviour
  // is undefined
  if(tcgetattr(serial_port, &tty) != 0) {
      printf("Error %i from tcgetattr: %s\n", errno, strerror(errno));
  }








  cfsetispeed(&tty, 900);
  cfsetospeed(&tty, 900);



  
  unsigned char msg[] = { 'H' };
  sleep(0.1);
  write(serial_port, msg, sizeof(msg));


  uint8_t read_buf [1200];
  int n = read(serial_port, &read_buf, sizeof(read_buf));


  /*
  // get correct currents
  uint16_t final_currents[30];
  for (int i; i<30; i++){
    final_currents[i] = (read_buf[2*i]>>8)&read_buf[2*i+1];
  }
  */



  for (int i; i<60; i++) {
    printf("%" PRIu8 "\n",read_buf[i]);
  }



  printf("before \n");
  uint16_t current = ((((uint16_t) read_buf[sizeof(read_buf)-2]) << 8) | ((uint16_t) read_buf[sizeof(read_buf)-1]))*adc_to_uA;
  printf("%" PRIu16 "\n",current);
  printf("after \n");
}