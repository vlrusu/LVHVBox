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
  uint8_t P1_0;
  uint8_t sclk;
  uint8_t csPin;
} all_pins;



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

  // CS line
  gpio_init(all_pins.csPin);
  gpio_set_dir(all_pins.csPin, GPIO_OUT);
  gpio_put(all_pins.csPin, 1);

  // Clock line direct port access
  gpio_init(all_pins.sclk);
  gpio_set_dir(all_pins.sclk, GPIO_OUT);
  gpio_set_drive_strength(all_pins.sclk, GPIO_DRIVE_STRENGTH_2MA);
  gpio_put(all_pins.sclk, 0);


  // Data lines direct port access. Using all bits so no mask needed
  // Current and Voltage
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



  //  *(portOutputRegister(port)) = 0xFF;   // DBG Apply input pullup to voltage data port
}

// Variables
void variable_init() {

  if (pico == 1) {
    //all_pins.crowbarPins = (uint8_t []){ 2, 5, 8, 11, 14, 21 };			// crowbar pins
      //  { 21, 26, 22, 16, 4, 5 };     //Channels in data are upside down, FIXME!!!
    uint8_t crowbarPins[6] = { 2, 5, 8, 11, 14, 21};
    uint8_t dataPinsV[6] = { 0, 3, 6, 9, 12, 26};
    uint8_t dataPinsI[6] = { 1, 4, 7, 10, 13, 22};

    for (int i = 0; i < 6; i++) {
      all_pins.crowbarPins[i] = crowbarPins[i];
      all_pins.dataPinsV[i] = dataPinsV[i];
      all_pins.dataPinsI[i] = dataPinsI[i];
    }

    all_pins.P1_0 = 20;					// Offset
    all_pins.sclk = 27;						// SPI clock
    all_pins.csPin = 15;					// SPI Chip select for I
  }
  else {
    uint8_t crowbarPins[6] = { 2, 5, 8, 26, 21, 14};
    uint8_t dataPinsV[6] = { 0, 3, 6, 9, 27, 20};
    uint8_t dataPinsI[6] = { 1, 4, 7, 10, 22, 13};

    for (int i = 0; i < 6; i++) {
      all_pins.crowbarPins[i] = crowbarPins[i];
      all_pins.dataPinsV[i] = dataPinsV[i];
      all_pins.dataPinsI[i] = dataPinsI[i];
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


int SM73201_ADC_Raw(PIO pio, uint sm[2]) {


  float channel_1_currents[8000];

  

  uint16_t temp_current_channel_1;

  
  absolute_time_t start = get_absolute_time();
  for (uint32_t i = 0; i < 8000; i++) {
    temp_current_channel_1 = pio_sm_get_blocking(pio, sm[1]);

    channel_1_currents[i] = temp_current_channel_1 * adc_to_uA;
  }

  adcTime = absolute_time_diff_us(start, get_absolute_time());
  

  
  for (uint32_t i=0;i<8000;i++){
    printf("%f\n", channel_1_currents[i]);
  }
  
  
  
  
  /*
  printf("#\n");
  
  printf("end\n");
  printf("%" PRIu32 "\n",adcTime);
  */
  
  
  



  

  /*
  uint16_t channel_1_voltage_raw;
  channel_1_voltage_raw = pio_sm_get_blocking(pio, sm[0]);
  float voltage_result;
  voltage_result = channel_1_voltage_raw * adc_to_V;
  printf("float %f \n \n",voltage_result);
  */
  
  


 

  /*
  uint32_t all_pins_array[18];
  for (uint8_t i = nClk; i--; ) {
    all_pins_array[i] = pio_sm_get_blocking(pio, sm);

    

  }
  printf("%" PRIu32 "\n",all_pins_array);
  printf("hello");
  */




  // Raise CS
  //gpio_put(all_pins.csPin, 1);

}



//******************************************************************************
// Standard loop function, called repeatedly
int main(){
  float clkdiv = 7;
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






  uint32_t start_mask = -1;

    PIO pio_0 = pio0;
    PIO pio_1 = pio1;


    // Start clock state machine
      uint sm_clock = pio_claim_unused_sm(pio_0, true);
    uint offset_clock = pio_add_program(pio_0, &clock_program);
    clock_program_init(pio_0,sm_clock,offset_clock,cs_pin,clkdiv);


    // start channel 1 voltage state machine
    uint sm_channel_1_voltage = pio_claim_unused_sm(pio_0, true);
    uint offset_channel_1_voltage = pio_add_program(pio_0, &channel_1_program);
    channel_1_program_init(pio_0,sm_channel_1_voltage,offset_channel_1_voltage,cs_pin,clkdiv);
    

    // start channel 1 current state machine
    uint sm_channel_1_current = pio_claim_unused_sm(pio_0, true);
    uint offset_channel_1_current = pio_add_program(pio_0, &channel_1_program);
    channel_1_program_init(pio_0,sm_channel_1_current,offset_channel_1_current,cs_pin+1,clkdiv);


    // create array of state machines
    uint sm_array[2];
    sm_array[0] = sm_channel_1_voltage;
    sm_array[1] = sm_channel_1_current;

    // start all state machines in pio block
    pio_enable_sm_mask_in_sync(pio_0, start_mask);




  gpio_put(all_pins.P1_0, 1);
  sleep_ms(1);


  while (true){
    SM73201_ADC_Raw(pio_0, sm_array);
    sleep_ms(5000);

    

    
  }
  return 0;

}
