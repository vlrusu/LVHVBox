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


// Channel count
#define mAdc  12		// Maximum number of ADCs to read
#define nAdc  6		// Number of SmartSwitches
#define mChn  6		// Number of channels for trip processing

#define pico 2



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
int32_t tripLimit = 300.;// / (adc_to_uA); //trip at 200uA
const uint16_t tripCount = 5;
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
    if (currents[chn] > limit) {
      count_over_current[chn]++;
      // Trip if reach limit
      if (count_over_current[chn] > tripCount) {
	gpio_put(all_pins.crowbarPins[chn], 1);
	printf("Trip on channel %d\n",mChn-1 - chn);
      }
    }
    else if (count_over_current[chn] > 0) {
      count_over_current[chn]--;
    }
    else
      continue;

    //Channels in data are upside down, FIXME!!!

//    printf("Trip count on channel %d changed to %d\n",mChn-1-chn,count_over_current[chn]);

  }
}

//******************************************************************************
// Hardware interface functions
// Read from from all ADCs in parallel
#pragma GCC push_options
#pragma GCC optimize ("Ofast")


void SM73201_ADC_Raw(PIO pio, uint sm) {
  const int nBitPerByte = 8;
  const int nBytesPerAdc = 2;

  // Drop CS, ALL chips
  gpio_put(all_pins.sclk, 1);
  //	*sclkAddr |= sclkMask;		// clock hi
  gpio_put(all_pins.csPin, 0);
  // Read 18x8 bits (1st two will be ignored)
  uint16_t* _pByBit = byBit - 1;
  //	uint8_t sclkHi = *sclkAddr;
  //	uint8_t sclkLo = sclkHi & ~sclkMask;
  uint32_t flags = save_and_disable_interrupts();

  absolute_time_t start = get_absolute_time();

  for (uint8_t i = nClk; i--; ) {
    gpio_put(all_pins.sclk, 0);
    *(++_pByBit) = 0;	// Just need increment. Set value to ensure compiler does this step here
    gpio_put(all_pins.sclk, 1);
    //    *_pByBit = (gpio_get_all()  & 0xFF ) ;
    uint32_t allPins = pio_sm_get_blocking(pio, sm);
    *_pByBit = (  ((allPins >> all_pins.dataPinsV[0]) & 0x1) << 0 | ((allPins >> all_pins.dataPinsV[1]) & 0x1) << 1 |
		  ((allPins >> all_pins.dataPinsV[2]) & 0x1) << 2 | ((allPins >> all_pins.dataPinsV[3]) & 0x1) << 3 |
		  ((allPins >> all_pins.dataPinsV[4]) & 0x1) << 4 | ((allPins >> all_pins.dataPinsV[5]) & 0x1) << 5 |
		  ((allPins >> all_pins.dataPinsI[0]) & 0x1) << 6 | ((allPins >> all_pins.dataPinsI[1]) & 0x1) << 7 |
		  ((allPins >> all_pins.dataPinsI[2]) & 0x1) << 8 | ((allPins >> all_pins.dataPinsI[3]) & 0x1) << 9 |
		  ((allPins >> all_pins.dataPinsI[4]) & 0x1) << 10 | ((allPins >> all_pins.dataPinsI[5]) & 0x1) << 11) ;




		 /*  *_pByBit = ( gpio_get(dataPins[0]) | gpio_get(dataPins[1]) << 1 | */
		 /* gpio_get(dataPins[2]) << 2 | gpio_get(dataPins[3]) << 3 */
		 /* | gpio_get(dataPins[4]) << 4 | gpio_get(dataPins[5]) << 5 */
		 /* | gpio_get(dataPins[6]) << 6 | gpio_get(dataPins[7]) << 7) ; */
  }
  adcTime += absolute_time_diff_us (start, get_absolute_time() );
  restore_interrupts(flags);

  // Raise CS
  gpio_put(all_pins.csPin, 1);

}

//==============================================================================
// Remap bits from all ADCS
void SM73201_ADC_Remap() {
  const int nBitPerByte = 8;
  memset(byChn, 0, sizeof(byChn));
  //  for (uint8_t i = nClk; i--; )
  //    printf("Bybit %08x\n",byBit[i]);
  uint16_t* pByBit = byBit + 2;  // Skip 1st two bits
  for (uint8_t i = 16; i--; ) {
    uint16_t portH = pByBit[0];            // MSB
    //    uint16_t portL = pByBit[nBitPerByte];  // LSB
    //    printf("test:%08x %08x\n",portL,portH);
    pByBit++;
    uint16_t* pByChn = (uint16_t*)(byChn + mAdc);
    for (uint8_t chn = mAdc; chn--; ) {
      pByChn --;
      // Relies on endian-ness of chip
      // Least significant byte
      pByChn[0] <<= 1;
      pByChn[0] |= portH & 1;
      portH >>= 1;
      // Most significant byte
      //      pByChn[1] <<= 1;
      //      pByChn[1] |= portH & 1;
      //      portH >>= 1;
    }
  };
}
#pragma GCC pop_options

//******************************************************************************
// Read out
// All currents or voltages once
void readCurent(int32_t* result, PIO pio, uint sm) {
  // Read Shunt
  //P1_0 = 0 reads the offset

  SM73201_ADC_Raw(pio, sm);
  // Switch to offset, let it stabilize
  // Remap bits while shunt/offset stabilizes
  gpio_put(all_pins.P1_0, 0);
  sleep_us(100);
  SM73201_ADC_Remap();
  //  printf("--------\n");
  //  for (uint8_t chn = mAdc; chn > 0; chn--) {
  //    printf("test:%08x\n",byChn[chn]);
  //  }

  for (uint8_t chn = nAdc; chn--;) {
    result[chn] = (int16_t)byChn[chn];
  }
  // Read offset
  SM73201_ADC_Raw(pio, sm);
  // Switch back to shunt
  gpio_put(all_pins.P1_0, 1);
  sleep_us(100);
  // Remap offset bits and merge with shunt
  SM73201_ADC_Remap();
  for (uint8_t chn = nAdc;  chn--;) {
        result[chn] -= (int16_t)byChn[chn];
    }
}

//==============================================================================
// All channels (voltage and current) multiple times
void readMultiple(int32_t* sumI, int32_t *sumV, PIO pio, uint sm) {
  for (uint16_t i = nSampleSlow; i--; ) {
    int32_t fastSum[nAdc];
    memset(fastSum, 0, sizeof(fastSum));
    // Read specified number of fast samples plus two
    for (uint16_t j = nSampleFast; j--; ) {
      int32_t single[nAdc];
      readCurent(single, pio, sm);
      for (uint8_t chn = nAdc; chn--; ) {
	fastSum[chn] += single[chn];
      }
    }
    // Sum fast samples for slow sample
    for (uint8_t chn = nAdc; chn--; ) {
      sumI[chn] += fastSum[chn];
    }
    // Also do trips
    trips(fastSum, tripLimit * nSampleFast);
    // Read voltage, still have the last read
    //    SM73201_ADC_Raw();
    //    SM73201_ADC_Remap();

    for (uint8_t chn = mAdc; chn>=nAdc; chn--) {
      sumV[chn-nAdc] += (int16_t)byChn[chn];
    }
  }
}


//******************************************************************************
// Standard loop function, called repeatedly
int main(){
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


  // Choose PIO instance (0 or 1)
  PIO pio = pio0;

  // Get first free state machine in PIO 0
  uint sm = pio_claim_unused_sm(pio, true);

  // Add PIO program to PIO instruction memory. SDK will find location and
  // return with the memory offset of the program.
  uint offset = pio_add_program(pio, &combined_program);

  // Calculate the PIO clock divider

  // Initialize the program using the helper function in our .pio file
  if (pico == 1) {
    combined_program_init_1(pio, sm, offset, cs_pin, 1);
  }
  else {
    combined_program_init_2(pio, sm, offset, cs_pin, 1);
  }

  // Start running our PIO program in the state machine
  pio_sm_set_enabled(pio, sm, true);







  while (true){

    absolute_time_t start = get_absolute_time();

    // Process keyboard entry, if any

    int input = getchar_timeout_us(10);
    if (input == 'R') {
      printf("Resetting trip\n");
      tripReset();
    }
    else if (input == 'T') {
      uint32_t limit  = atoi(readLine());
      printf("Trip limit changed from %d to ",tripLimit);
      if (limit > 0)
	tripLimit = MIN(0x7FFFFFFF, limit / (1000 * adc_to_uA));
      printf("%d\n",tripLimit);
      sleep_ms(10000);
    }
    else if (input == 'F'){
      uint32_t channel  = atoi(readLine());
      printf("Forcing trip on cha %d\n",channel);
      gpio_put(all_pins.crowbarPins[channel], 1);
    }

    int32_t sumI[mAdc], sumV[mAdc];
    adcTime = 0;
    memset(sumI, 0, sizeof(sumI));
    memset(sumV, 0, sizeof(sumV));
    readMultiple(sumI,sumV,pio,sm);
    // Print currents
    for (uint8_t i = 0; i < nAdc; i++) {
      // Convert sum to uA
      float current = sumSclI * sumI[i];
      // then to fixed-length string
      printf(" %6.3f",current);
    }
    printf( " | ");
    // Repeat for voltage
    for (uint8_t i = 0; i < nAdc; i++) {
      // Convert sum to uA
      float voltage = sumSclV * sumV[i];
      // then to fixed-length string
      printf(" %6.3f",voltage);
    }
    printf( " | ");
    uint32_t totalTime = absolute_time_diff_us (start, get_absolute_time() );

    if (pico == 1) {
      float result = adc_read()*3.3/8192*1.5;
      printf("%1.2f | ",result);
    }
    else {
      float result = (1.8455-adc_read()*3.3/4096)/0.01123;
      printf("%1.2f | ",result);
    }

    // identifier for the pico
    if (pico == 1) {
      printf("1 | ");
    }
    else {
      printf("2 | ");
    }

    printf( "ADCTime=%d TotalTime=%d\n",adcTime,totalTime);

    sleep_ms(1000);
  }
  return 0;

}
