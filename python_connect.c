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

#define SPISPEED 40000000
//#define SPISPEED 320000

AD5685 dac[3];



int test() {
	return 20;
}


void initialization(){
  wiringPiSetup () ;
  wiringPiSPISetup (0, SPISPEED);


  //bring the MCP out of reset
  pinMode(26, OUTPUT);
  digitalWrite(26, HIGH);

  //setup MCP
  int retc = mcp23s17Setup (MCPPINBASE, 0, 0);
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


void set_hv(int v0, int v1)
{
  int ch0=atoi(0);
  int ch1=atoi(1);
  float val1=atof(v0);
  float val2=atof(v1);

  val0 = val0*2.3/1510.;
  val1 = val1*2.3/1510.;

  int idac0 = (int) (ch0/4);
  int idac1 = (int) (ch1/4);

	AD5685_setdac(&dac[idac0],ch0%4,val0);
	AD5685_setdac(&dac[idac1],ch1%4,val1);
}


int get_hv(int ch)
{
	int channel = atoi(ch);
	float value = atof
}








	int channel = atoi(argv[1]);
	float value = atof(argv[2]);

	value = value*2.3/1510.;
	int idac = (int) (channel/4);
	printf(" Chan %i HV idac %i  is set to %7.2f\n", channel, idac, value);
	AD5685_setdac(&dac[idac],channel%4,value);
