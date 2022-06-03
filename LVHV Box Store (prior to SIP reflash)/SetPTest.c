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

#include <ad5318.h>
#include <LTC2634.h>

enum MCPs{MCPCAL0, MCPCAL1, MCPCALIB, MCPCAL2, MCPCAL3, MCPHV0, MCPHV1, MCPHV2, MCPHV3};

const int MCPCALIBCHAN[8] = {0,1,2,3,8,9,10,11};

int default_gains_cal[96] = {370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370};
int default_gains_hv[96] = {370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370,370};
int default_threshs_cal[96] = {417,386,454,395,429,407,410,438,438,408,408,407,410,431,419,407,427,404,426,434,453,423,419,415,421,444,423,440,446,448,437,428,453,414,413,423,409,419,455,443,413,428,429,451,406,408,404,410,417,416,421,446,444,350,417,395,443,409,420,452,409,452,445,405,426,350,442,417,408,414,448,454,427,404,449,430,426,411,444,441,438,441,430,420,437,404,436,437,433,418,432,455,431,433,430,413};
int default_threshs_hv[96] = {410,406,433,415,448,446,432,446,434,413,431,437,445,446,411,444,431,404,440,438,437,445,440,451,434,441,433,437,437,426,437,438,448,428,443,452,435,452,432,445,445,440,434,434,436,439,433,434,432,438,422,427,432,350,438,442,435,434,440,436,434,436,454,432,441,443,444,442,432,424,440,440,436,442,419,449,441,438,449,453,432,433,432,450,437,423,428,427,423,442,426,436,454,433,452,437};

const int default_caldac[8] = {1023,1023,1023,1023,1023,1023,1023,1023};

#define MCPPINBASE 2000
#define CALDACPINBASE 3000
#define PWMRANGE 1000
#define LED 14
#define CALPULSERPWM0 12
#define CALPULSERPWM1 13

#define SPISPEED 1000000
//#define SPISPEED 320000

typedef struct {
  LTC2634* _ltc;
  int _thresh;
  int _gain;
} Straw;

LTC2634 dac_cal;
LTC2634 dac_hv;

Straw strawsCal[2];
Straw strawsHV[2];

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
  wiringPiSPISetup (0, SPISPEED);
  wiringPiSPISetupMode (1, SPISPEED,SPI_MODE_2);


  softPwmCreate (LED, 0, PWMRANGE) ;
  //  softPwmCreate (CALPULSERPWM0, 0, PWMRANGE) ;
  //  softPwmCreate (CALPULSERPWM1, 0, PWMRANGE) ;
  pinMode(12,PWM_OUTPUT);
  pinMode(13,PWM_OUTPUT);

  //  pwmSetClock(10);
  
  pwmWrite(12, 0);
  pwmWrite(13, 0);


  //    pwmWrite(12, 0);
    //   pwmWrite(13, 0);
  
  //setup MCP
  int retc = mcp23s17Setup (MCPPINBASE, 0, 0);
  

    printf("mcp setup done %d\n",retc);

  // outputs for calpulse enable pins 8 and 9
  pinMode (MCPPINBASE+8, OUTPUT);
  pinMode (MCPPINBASE+9, OUTPUT);
  digitalWrite (MCPPINBASE+8, 0);
  digitalWrite (MCPPINBASE+9, 0);


  LTC2634_setup (&dac_cal, MCPPINBASE, 0, MCPPINBASE, 2, MCPPINBASE, 1);
  LTC2634_setup (&dac_hv, MCPPINBASE, 3, MCPPINBASE, 2, MCPPINBASE, 1);




  printf("ltc setup done\n");

  // Set default thresholds and gains
  for (int i = 0 ; i < 2 ; i++){
    strawsCal[i]._ltc =  &dac_cal;
    strawsHV[i]._ltc = &dac_hv;
    if (i == 0){
      strawsCal[i]._thresh = 1;
      strawsCal[i]._gain = 2;
      strawsHV[i]._thresh = 0;
      strawsHV[i]._gain = 2;
    }else{
      strawsCal[i]._thresh = 0;
      strawsCal[i]._gain = 3;
      strawsHV[i]._thresh = 1;
      strawsHV[i]._gain = 3;
    }

    LTC2634_write(strawsCal[i]._ltc,strawsCal[i]._gain,default_gains_cal[i]);
    LTC2634_write(strawsCal[i]._ltc,strawsCal[i]._thresh,default_threshs_cal[i]);
    LTC2634_write(strawsHV[i]._ltc,strawsHV[i]._gain,default_gains_hv[i]);
    LTC2634_write(strawsHV[i]._ltc,strawsHV[i]._thresh,default_threshs_hv[i]);

  }

  //setup CALDAC
  ad5318Setup(CALDACPINBASE, 1);
  for (int i=0;i<8;i++)
    analogWrite(CALDACPINBASE+i,default_caldac[i]);




}

//write gain.thres
void setPreampGain(int channel, int value){
  if (channel < 2){
    LTC2634_write(strawsCal[channel]._ltc,strawsCal[channel]._gain,value);

    default_gains_cal[channel] = value;
  }
  if (channel >= 2){
    LTC2634_write(strawsHV[channel - 2]._ltc,strawsHV[channel - 2]._gain,value);

    default_gains_hv[channel-2] = value;
  }
}

void setPreampThreshold(int channel, int value){
  if (channel < 2){

    LTC2634_write(strawsCal[channel]._ltc,strawsCal[channel]._thresh,value);
    default_threshs_cal[channel] = value;
  }
  if (channel >= 2){

    LTC2634_write(strawsHV[channel - 2]._ltc,strawsHV[channel - 2]._thresh,value);

    default_threshs_hv[channel-2] = value;
  }
}

void setCalDAC(int channel, int value){
    analogWrite(CALDACPINBASE+channel, value);
}

void pulserOn(int pwmpulse, int channel){


  //FIXME - this should be a mask, and the mapping is incorrect. need to be able to choose all on, or just one on

  printf("set pulser to %d\n",pwmpulse);

  pwmWrite(12, pwmpulse);
  pwmWrite(13, pwmpulse);

  digitalWrite (MCPPINBASE+8+channel, 1);
  
}

void pulserOff(){


  pwmWrite(12, 0);
  pwmWrite(13, 0);


  
}

int main(int argc, char *argv[])
{
	int opt;
	int cmderr = 0;
	initialization();

	//	printf("Press any key to continue.\n");
	//	mygetch();

	while((opt = getopt(argc, argv, ":itgp:cy")) != -1){
		switch(opt){  
            case 'i':
				//				pulserOn(0,800);
	      printf("Initialization completed.\n");
				break;
			case 't':
				if (argc==5){
					int channel = atoi(argv[2]);
					int ishv = atoi(argv[3]);
					int value = atoi(argv[4]);
					setPreampThreshold(channel+2*ishv, value);
					if (ishv)
						printf("Set threshold: Chan %i HV  is set to %i.\n", channel, value);
					else
						printf("Set threshold: Chan %i CAL is set to %i.\n", channel, value);
				}else cmderr = 1;
				break;
			case 'g':
				if (argc==5){
					int channel = atoi(argv[2]);
					int ishv = atoi(argv[3]);
					int value = atoi(argv[4]);
					setPreampGain(channel+2*ishv, value);
					if (ishv)
						printf("Set gain     : Chan %i HV  is set to %i.\n", channel, value);
					else
						printf("Set gain     : Chan %i CAL is set to %i.\n", channel, value);
				}else cmderr = 1;
				break;
			case 'p':
				if (optarg==0){
					pulserOff();
					printf("Pulser is turned off.\n");
				}
				else{
					if (argc==4){
						int value = atoi(argv[2]);
						int channel = atoi(argv[3]);
						pulserOn(value, channel);
						printf("For channel 3 turn on -p 1 \n");

						printf("Pulser is turned on  to %i for channel %i\n", value, channel);
					}
					else cmderr = 1;
				}
				break;
			case 'c':
				if (argc==4){
					int channel = atoi(argv[2]);
					int value = atoi(argv[3]);
					setCalDAC(channel, value);
					printf("Set caldac   : Pulser is set to %i.\n", value);
				}else cmderr = 1;
				break;

		case 'y':
		  printf ("Does nthingyet\n");
		  //		  digitalWrite ( MCPPINBASE+16*MCPHV1+1, 1) ;
		   break;
		  
			case '?':
				cmderr = 1;
				break;
		}
	}

	if (cmderr==1){
		printf("Invalid commands.\n");
		printf("Possible commands:\n");
		printf("	setADRAC i                                   | Initialization\n");
		printf("	setADRAC t [channel] [ishv] [threshold]      | Set threshold\n");
		printf("	setADRAC g [channel] [ishv] [gain]           | Set gain\n");
		printf("	setADRAC p 1 [channel] [value]               | Turn on pulser\n");
		printf("	setADRAC p 0                                 | Turn off pulser\n");
		printf("	setADRAC c [channel] [value]                 | Set Caldac\n");
	}
	
	return 0 ;
}   
