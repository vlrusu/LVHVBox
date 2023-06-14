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
#include <fcntl.h> // Contains file controls like O_RDWR
#include <errno.h> // Error integer and strerror() function
#include <termios.h> // Contains POSIX terminal control definitions
#include <unistd.h> // write(), read(), close()

#include <inttypes.h>





#define VENDOR_ID      0xcafe
#define PRODUCT_ID     0x4003


#define TRANSFER_SIZE    8  


const float adc_to_V  = 2.048 / pow(2, 15) * 1000;
const float adc_to_uA = 2.048 / pow(2, 15) / 8200.0 * 1.E6;




int main( int argc, char **argv )
{
    struct libusb_device_handle * device_handle = NULL; // Our ADU's USB device handle
	  char value_str[8]; // 8-byte buffer to store string values read from device 
			  //(7 byte string + NULL terminating character)

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
  device_handle = libusb_open_device_with_vid_pid( NULL, VENDOR_ID, PRODUCT_ID );
    

  libusb_set_auto_detach_kernel_driver( device_handle, 1 );
  // Claim interface 0 on the device
  result = libusb_claim_interface( device_handle, 1 );
 



  uint16_t inner_loop = 1;


  uint32_t count = 1000;
  float all_data[30*count*inner_loop];

  char send_data = 'h';
  char* input_data;
  input_data = (char *)malloc(60*inner_loop);



  uint16_t one;
  uint16_t two;

  int status;

  uint32_t start, end, elapsed;

  struct timeval tv;
  gettimeofday(&tv,NULL);
  start = 1000000 * tv.tv_sec + tv.tv_usec;

  for (uint32_t iteration=0; iteration < count; iteration++) {



    for (int i=0; i<inner_loop; i++) {
      libusb_bulk_transfer(device_handle, 0x02, &send_data, 1, 0, 0);
    }
    libusb_bulk_transfer(device_handle, 0x82, input_data, 60*inner_loop, 0, 0);
    
 

    
    for (int i=0; i<30*inner_loop; i++) {
      one = input_data[2*i+1] << 8;
      two = input_data[2*i];


      all_data[30*inner_loop*iteration + i] = (one | two) * adc_to_uA;
    }
    
    
    
    

  }
  gettimeofday(&tv,NULL);
  end = 1000000 * tv.tv_sec + tv.tv_usec;

  float frequency = (1.E6)/(end-start)*30*count*inner_loop;
  printf("%f \n", frequency);

  


  

  //printf("%" PRIu32 "\n",output_data[0]);
  //printf("%u", (unsigned int)input_data[0]);
  //printf("hello");
  //printf("%f \n", all_data[300]);



  char *filename = "hv_currents.txt";

  // open the file for writing
  FILE *fp = fopen(filename, "w");
  if (fp == NULL)
  {
      printf("Error opening the file %s", filename);
      return -1;
  }

  for (int i=0; i<count*inner_loop*30; i++) {
    fprintf(fp, "%f\n", all_data[i]);
  }
  

  // close the file
  fclose(fp);






















     // we are done with our device and will now release the interface we previously claimed as well as the device
    libusb_release_interface( device_handle, 0 );
    libusb_close( device_handle );

    // shutdown libusb
    libusb_exit( NULL );

    return 0;
}
