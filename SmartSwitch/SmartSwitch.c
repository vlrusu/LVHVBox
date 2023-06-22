#include <stdio.h>
#include <math.h>
#include "string.h"
#include "pico/stdlib.h"
#include "pico/types.h"
#include "pico/platform.h"
#include "hardware/gpio.h"
#include <stdlib.h>
#include "pico/stdlib.h"
#include "hardware/sync.h"
#include "hardware/adc.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "combined.pio.h"
#include <inttypes.h>

#include "clock.pio.h"
#include "channel.pio.h"


// Channel count
#define mAdc  12		// Maximum number of ADCs to read
#define nAdc  6		// Number of SmartSwitches
#define mChn  6		// Number of channels for trip processing

#define pico 1



// Readout
#define nSampleFast 10		// No. of samples to average before checking for trip
#define nSampleSlow 100		// No. of "Fast" samples to combine for upload
//#define nSampleFast 1		// No. of samples to average before checking for trip
//#define nSampleSlow 1		// No. of "Fast" samples to combine for upload
#define nClk 18// Clock cycles for complete readout

struct Pins {
  uint8_t crowbarPins[mChn];
  uint8_t dataPinsV[nAdc];
  uint8_t dataPinsI[nAdc];
  uint8_t headerPins[nAdc];
  uint8_t P1_0;
  uint8_t sclk;
  uint8_t csPin;
  uint8_t enablePin;
} all_pins;


/*
// Converstion from ADC to microamps
const float adc_to_V  = 2.048 / pow(2, 15) * 1000;			// ADC full-scale voltage / ADC full scale reading * divider ratio
//const float adc_to_uA = 2.048 / pow(2, 15) / (10716.52) * 1.E6;	// ADC full-scale voltage / ADC full scale reading / shunt resistance * uA per amp
const float adc_to_uA = (2.048 / pow(2, 15)) / (22.56* 470.0) * 1.E6;
*/

// Converstion from ADC to microamps
const float adc_to_V  = 2.048 / pow(2, 15) * 1000;			// ADC full-scale voltage / ADC full scale reading * divider ratio
const float adc_to_uA = 2.048 / pow(2, 15) / 8200.0 * 1.E6;	// ADC full-scale voltage / ADC full scale reading / shunt resistance * uA per amp

// Trip constants and variables
const uint8_t liveChn = 0b00111111;		// Zeros for any channel you do NOT want trip logic applied to
//const uint8_t liveChn = 0b01;		// Zeros for any channel you do NOT want trip logic applied to
int32_t tripLimit = 20.;// / (adc_to_uA); //trip at 200uA
const uint16_t tripCount = 50;
uint8_t count_over_current[mChn];

uint8_t state = 0;

// Time ADC readout
int32_t adcTime;

// Shared storage for ADC readout
static uint16_t byChn[mAdc]; //not much point defining these static, but maybe useful in teh future
static uint16_t byBit[nClk];


//getchar does not realy work , have ot use the SDK version
unsigned char mygetchar() {
  int c;
  while ( (c = getchar_timeout_us(0)) < 0);
  return (unsigned char)c;
};

unsigned char buffer[85];

unsigned char * readLine() {
  unsigned char u , *p ;
  for (p=buffer, u = mygetchar() ; u != '\r' && p - buffer <80 ; u = mygetchar()) putchar(*p++=u);
  *p = 0 ;
  printf("\n") ;
  return buffer;
}

// Pin definitions for pico 1



//******************************************************************************
// Initialization functions
// Ports

void port_init() {

  uint8_t port;
  // Reset all trips
  for (uint8_t i = 0; i < sizeof(all_pins.crowbarPins); i++) {
    gpio_init(all_pins.crowbarPins[i]);
    gpio_set_dir(all_pins.crowbarPins[i], GPIO_OUT);
  }
  // Pedestal/data line
  gpio_init(all_pins.P1_0);
  gpio_set_dir(all_pins.P1_0, GPIO_OUT);

  // MUX enable pin
  gpio_init(all_pins.enablePin);
  gpio_set_dir(all_pins.enablePin, GPIO_OUT);

  /*
  // CS line
  gpio_init(all_pins.csPin);
  gpio_set_dir(all_pins.csPin, GPIO_OUT);
  gpio_put(all_pins.csPin, 1);

  // Clock line direct port access
  gpio_init(all_pins.sclk);
  gpio_set_dir(all_pins.sclk, GPIO_OUT);
  gpio_set_drive_strength(all_pins.sclk, GPIO_DRIVE_STRENGTH_2MA);
  gpio_put(all_pins.sclk, 0);
  */


  // Data lines direct port access. Using all bits so no mask needed
  // Current and Voltage
  /*
  uint dataPins_mask = 0;
  for (int i =0 ;i < nAdc; i++)
    dataPins_mask |= (1<<all_pins.dataPinsI[i]);
  gpio_init_mask(dataPins_mask);
  gpio_set_dir_in_masked	(	dataPins_mask);

  dataPins_mask = 0;
  for (int i =0 ;i < nAdc; i++)
    dataPins_mask |= (1<<all_pins.dataPinsV[i]);
  gpio_init_mask(dataPins_mask);
  gpio_set_dir_in_masked	(	dataPins_mask);
  */



  //  *(portOutputRegister(port)) = 0xFF;   // DBG Apply input pullup to voltage data port
}

// Variables
void variable_init() {

  if (pico == 1) {
    //all_pins.crowbarPins = (uint8_t []){ 2, 5, 8, 11, 14, 21 };			// crowbar pins
      //  { 21, 26, 22, 16, 4, 5 };     //Channels in data are upside down, FIXME!!!
    uint8_t crowbarPins[6] = { 2, 5, 8, 11, 14, 21};
    //uint8_t dataPinsV[6] = { 0, 3, 6, 9, 12, 26};
    //uint8_t dataPinsI[6] = { 1, 4, 7, 10, 13, 22};
    uint8_t headerPins[6] = { 1, 3, 6, 10, 12, 9};

    for (int i = 0; i < 6; i++) {
      all_pins.crowbarPins[i] = crowbarPins[i];
      //all_pins.dataPinsV[i] = dataPinsV[i];
      //all_pins.dataPinsI[i] = dataPinsI[i];
      all_pins.headerPins[i] = headerPins[i];
    }

    all_pins.P1_0 = 20;					// Offset
    all_pins.sclk = 26;						// SPI clock
    all_pins.csPin = 15;					// SPI Chip select for I
    all_pins.enablePin = 7;     // enable pin for MUX
  }
  else {
    uint8_t crowbarPins[6] = { 2, 5, 8, 26, 21, 14};
    //uint8_t dataPinsV[6] = { 0, 3, 6, 9, 27, 20};
    //uint8_t dataPinsI[6] = { 1, 4, 7, 10, 22, 13};

    for (int i = 0; i < 6; i++) {
      all_pins.crowbarPins[i] = crowbarPins[i];
      //all_pins.dataPinsV[i] = dataPinsV[i];
      //all_pins.dataPinsI[i] = dataPinsI[i];
    }
    all_pins.P1_0 = 15;					// Offset
    all_pins.sclk = 11;						// SPI clock
    all_pins.csPin = 12;					// SPI Chip select for I
  }

  tripLimit = tripLimit / (adc_to_uA); //convert trip limit to ADC counts from uA
  memset(count_over_current, 0, sizeof(count_over_current));
}

//******************************************************************************
// Trip logic
// Reset all trips
void tripReset() {
  for (int i = 0; i < sizeof(all_pins.crowbarPins); i++) {
    gpio_put(all_pins.crowbarPins[i], 0);
  }
}
//==============================================================================
// Set trips for current above limit
// Avoid tripping from short glitch by doing a ~running average of times over limit

void trips(int32_t currents[], int32_t limit) {
  uint8_t process = liveChn;


  for (uint8_t chn = 0; chn < mChn; chn++, process >>= 1) {

    if ( (process & 1) == 0)	// Option to skip channels (useful for debugging)
      continue;
    // Count up if above limit, down if below limit
    if (abs(currents[chn]) > limit) {
      count_over_current[chn]++;
      // Trip if reach limit
      if (count_over_current[chn] > tripCount) {
	gpio_put(all_pins.crowbarPins[mChn -1 - chn], 1) ; //FIXME
	printf("Trip on channel %d\n",mChn-1 - chn);
      }
    }
    else if (count_over_current[chn] > 0) {
      count_over_current[chn]--;
    }
    else
      continue;

    //Channels in data are upside down, FIXME!!!

    printf("Trip count on channel %d changed to %d\n",mChn-1-chn,count_over_current[chn]);

  }
}

//******************************************************************************
// Hardware interface functions
// Read from from all ADCs in parallel
#pragma GCC push_options
#pragma GCC optimize ("Ofast")

float get_single_voltage(PIO pio, uint sm) {
  uint16_t temp = pio_sm_get_blocking(pio, sm);
  float voltage = temp * adc_to_V;
  return voltage;
}


float get_averaged_current(PIO pio, uint sm) {


  float averaged_current = 0;

  uint16_t temp_current = 0;

  
  //absolute_time_t start = get_absolute_time();
  for (uint32_t i = 0; i < 200; i++) {
    temp_current = pio_sm_get_blocking(pio, sm);
    averaged_current += temp_current;
  }
  averaged_current *= adc_to_uA/200;

  //adcTime = absolute_time_diff_us(start, get_absolute_time());
  //printf("%f\n", averaged_current);

  return averaged_current;
  
}



//******************************************************************************
// Standard loop function, called repeatedly
int main(){
  float clkdiv = 21;
  static const float sumSclI = adc_to_uA / (nSampleFast*nSampleSlow);
  static const float sumSclV = adc_to_V / nSampleSlow;

  stdio_init_all();

  // initialize adc for adc 2 (gpio pin 28)
  adc_init();
  adc_gpio_init(28);
  adc_select_input(2);


  //  set_sys_clock_khz(150000, true);

  variable_init();
  port_init();

  static const uint sclk_pin = 1;
  static const uint cs_pin = 0;
  static const float pio_freq = 2000;

  // initialize channel currents
  float channel_current_averaged[6];
  float channel_voltage[6];

  // set current trip limit
  float trip_current = 1000000;







  uint32_t start_mask = -1;

    PIO pio_0 = pio0;
    PIO pio_1 = pio1;

    // Start clock state machine
      uint sm_clock = pio_claim_unused_sm(pio_0, true);
    uint offset_clock = pio_add_program(pio_0, &clock_program);
    clock_program_init(pio_0,sm_clock,offset_clock,cs_pin,clkdiv);


    // start channel 0 state machine
    uint sm_channel_0 = pio_claim_unused_sm(pio_0, true);
    uint offset_channel_0 = pio_add_program(pio_0, &channel_program);
    channel_program_init(pio_0,sm_channel_0,offset_channel_0,1,clkdiv);

    /*

    // start channel 1 state machine
    uint sm_channel_1 = pio_claim_unused_sm(pio_0, true);
    uint offset_channel_1 = pio_add_program(pio_0, &channel_program);
    channel_program_init(pio_0,sm_channel_1,offset_channel_1,all_pins.headerPins[1],clkdiv);

    // start channel 2 state machine
    uint sm_channel_2 = pio_claim_unused_sm(pio_0, true);
    uint offset_channel_2 = pio_add_program(pio_0, &channel_program);
    channel_program_init(pio_0,sm_channel_0,offset_channel_2,all_pins.headerPins[2],clkdiv);



    // start channel 3 state machine
    uint sm_channel_3 = pio_claim_unused_sm(pio_1, true);
    uint offset_channel_3 = pio_add_program(pio_1, &channel_program);
    channel_program_init(pio_1,sm_channel_3,offset_channel_3,all_pins.headerPins[3],clkdiv);

    // start channel 4 state machine
    uint sm_channel_4 = pio_claim_unused_sm(pio_1, true);
    uint offset_channel_4 = pio_add_program(pio_1, &channel_program);
    channel_program_init(pio_1,sm_channel_4,offset_channel_4,all_pins.headerPins[4],clkdiv);

    // start channel 5 state machine
    uint sm_channel_5 = pio_claim_unused_sm(pio_1, true);
    uint offset_channel_5 = pio_add_program(pio_1, &channel_program);
    channel_program_init(pio_1,sm_channel_5,offset_channel_5,all_pins.headerPins[5],clkdiv);
    

   

    // create array of state machines
    uint sm_array[6] = {sm_channel_0, sm_channel_1, sm_channel_2, sm_channel_3, sm_channel_4, sm_channel_5};
    */
    uint sm_array[6];
    sm_array[0] = sm_channel_0;

    // start all state machines in both pio blocks
    pio_enable_sm_mask_in_sync(pio_0, start_mask);
    pio_enable_sm_mask_in_sync(pio_1, start_mask);



  // disable trip for all channels initially
  gpio_put(all_pins.P1_0, 1);
  for (uint32_t i=0; i<6; i++){
    gpio_put(all_pins.crowbarPins[i],0);
  }
  sleep_ms(1);


  while (true){

    // ----- Collect 200 measurement current average, timing it ----- //

    // obtain start time for data acquisition
    absolute_time_t start = get_absolute_time();

    // set mux to current
    gpio_put(all_pins.enablePin, 1);
    sleep_ms(100);
    for (uint32_t i=0; i<1000; i++) {

      channel_current_averaged[0] = get_averaged_current(pio_0, sm_array[0]);
    

      if (channel_current_averaged[0] > trip_current) {
        gpio_put(all_pins.crowbarPins[0],1);
        printf("Channel 1 tripped");
      }
    }
    printf("Current measurement: %f\n", channel_current_averaged[0]);


  

    // ----- Collect single voltage measurement ----- //

    // set mux to voltage
    gpio_put(all_pins.enablePin, 0);
    sleep_ms(100);

    channel_voltage[0] = get_single_voltage(pio_0, sm_array[0]);
    printf("Voltage measurement: %f\n", channel_voltage[0]);


    // calculate frequency of data acquisition
    float adcTime = absolute_time_diff_us(start, get_absolute_time());
    printf("%f\n", 1/adcTime*1000*10.E5*200);
    
  }
  return 0;

}
