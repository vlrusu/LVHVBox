#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include <math.h>
#include <unistd.h>
#include <termios.h>


#include <wiringPi.h>
#include <wiringPiSPI.h>
#include <mcp23x0817.h>
#include <mcp23s17.h>
#include <softPwm.h>
#include <linux/spi/spidev.h>
#include <ad5685.h>

#define NSTEPS 100
#define MCPPINBASE 2000

#define SPICS 1

#define SPISPEED 40000000
//#define SPISPEED 320000

AD5685 dac[3];


int mygetch ( void ) 
{
  int ch;
  struct termios oldt, newt;

  tcgetattr ( STDIN_FILENO, &oldt );
  newt = oldt;
  newt.c_lflag &= ~( ICANON | ECHO );
  tcsetattr ( STDIN_FILENO, TCSANOW, &newt );
  ch = getchar();
  tcsetattr ( STDIN_FILENO, TCSANOW, &oldt );

  return ch;
}







void initialization(){

  
  wiringPiSetup () ;
  wiringPiSPISetup (SPICS, SPISPEED);


  //bring the MCP out of reset
  pinMode(26, OUTPUT);
  digitalWrite(26, HIGH);
  
  //setup MCP
  int retc = mcp23s17Setup (MCPPINBASE, SPICS, 0);
  printf("mcp setup done %d\n",retc);

  //sete RESET to DACs to high
  digitalWrite (MCPPINBASE+7, 1);
  pinMode(MCPPINBASE+7, OUTPUT);

  //sete LDAC to DACs to low
  digitalWrite (MCPPINBASE+3, 0);
  pinMode(MCPPINBASE+3, OUTPUT);


  
  AD5685_setup (&dac[0], MCPPINBASE, 4, MCPPINBASE, 2, MCPPINBASE, 0);
  AD5685_setup (&dac[1], MCPPINBASE, 5, MCPPINBASE, 2, MCPPINBASE, 0);
  AD5685_setup (&dac[2], MCPPINBASE, 6, MCPPINBASE, 2, MCPPINBASE, 0);  

}


int main(int argc, char *argv[])
{
	int opt;
	int cmderr = 0;

	/*
	while((opt = getopt(argc, argv, “:if:lrx”)) != -1) 
	  { 
	    switch(opt) 
	      { 
	      case ‘i’: 
	      case ‘l’: 
	      case ‘r’: 
                printf(“option: %c\n”, opt); 
                break; 
	      case ‘f’: 
                printf(“filename: %s\n”, optarg); 
                break; 
	      case ‘:’: 
                printf(“option needs a value\n”); 
                break; 
	      case ‘?’: 
                printf(“unknown option: %c\n”, optopt);
	      break; 
	      } 
	  } 
	*/
	initialization();

	int channel = atoi(argv[1]);
	float value = atof(argv[2]);

	value = value*2.3/1510.;
	int idac = (int) (channel/4);
	printf(" Chan %i HV idac %i  is set to %7.2f\n", channel, idac, value);	
	AD5685_setdac(&dac[idac],channel%4,value);

	
	
	return 0 ;
}   
