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
#include "clock.pio.h"
#include "channel.pio.h"
#include "combined.pio.h"
#include <pico/platform.h>
#include <inttypes.h>

#include "bsp/board.h"
#include "tusb.h"



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


void SM73201_ADC_Raw(PIO pio, uint sm[]) {

  

  float channel_1_currents[8000];

  

  uint16_t temp_current_channel_1;

  
  absolute_time_t start = get_absolute_time();
  for (uint32_t i = 0; i < 8000; i++) {
    temp_current_channel_1 = pio_sm_get_blocking(pio, sm[1]);

    channel_1_currents[i] = temp_current_channel_1 * adc_to_uA;
  }

  
  
  for (uint32_t i = 0; i<8000; i++) {
    printf("%f\n", channel_1_currents[i]);
  }
  
  
  


 

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























//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

// Invoked when device is mounted
void tud_mount_cb(void)
{
  ;
}

// Invoked when device is unmounted
void tud_umount_cb(void)
{
  ;
}

// Invoked when usb bus is suspended
// remote_wakeup_en : if host allow us  to perform remote wakeup
// Within 7ms, device must draw an average of current less than 2.5 mA from bus
void tud_suspend_cb(bool remote_wakeup_en)
{
  (void) remote_wakeup_en;
  ;
}

// Invoked when usb bus is resumed
void tud_resume_cb(void)
{
  ;
}










//--------------------------------------------------------------------+
// USB CDC
//--------------------------------------------------------------------+
/*
void cdc_task(void)
{
  if ( tud_cdc_connected() )
  {
    // connected and there are data available
    if ( tud_cdc_available() )
    {
      uint8_t buf[64];

      // read and echo back
      uint32_t count = tud_cdc_read(buf, sizeof(buf));

      for(uint32_t i=0; i<count; i++)
      {
        tud_cdc_write_char(buf[i]);

        if ( buf[i] == '\r' ) tud_cdc_write_char('\n');
      }

      tud_cdc_write_flush();
    }
  }
}

*/

void cdc_task(PIO pio, uint sm[])
{
  uint16_t channel_1_current_list[30];
  uint16_t channel_1_voltage_list[30];
  uint32_t temp_voltage;
  uint32_t temp_current;

  
  if ( tud_cdc_available() )
    {
      tud_cdc_read_flush();

      
      for(uint32_t i=0; i<30; i++)
      {
        //tud_cdc_write(&channel_1_currents[i],sizeof(channel_1_currents[i]));


        channel_1_voltage_list[i] = (uint16_t) pio_sm_get_blocking(pio, sm[0]);
        channel_1_current_list[i] = (uint16_t) pio_sm_get_blocking(pio, sm[1]);

        
        tud_cdc_write(&channel_1_current_list[i],sizeof(channel_1_current_list)[i]);
        

        
        
      }
      
      tud_cdc_write_flush();
  

    }
    

}


// Invoked when cdc when line state changed e.g connected/disconnected
void tud_cdc_line_state_cb(uint8_t itf, bool dtr, bool rts)
{
  (void) itf;

  // connected
  if ( dtr && rts )
  {
    // print initial message when connected
    tud_cdc_write_str("\r\nTinyUSB CDC MSC device example\r\n");
  }
}

// Invoked when CDC interface received data from host
void tud_cdc_rx_cb(uint8_t itf)
{
  (void) itf;
}
























//******************************************************************************
// Standard loop function, called repeatedly
int main(){

  stdio_init_all();


  //board_init();






  float clkdiv = 7;
  uint32_t start_mask = -1;
  static const float sumSclI = adc_to_uA / (nSampleFast*nSampleSlow);
  static const float sumSclV = adc_to_V / nSampleSlow;

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

  uint32_t current_reading;


 

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

 //pio_sm_set_enabled(pio_0, sm_clock, true);
 //pio_sm_set_enabled(pio_0, sm_clock, true);

 
  gpio_put(all_pins.P1_0, 1);


  
  sleep_ms(100);
  //tud_init(BOARD_TUD_RHPORT);

//SM73201_ADC_Raw(pio_0, sm_array);
  while (true){


    /*
    cdc_task(pio_0, sm_array);

    tud_task();
    */

   SM73201_ADC_Raw(pio_0, sm_array);

   

    
  }
  

  return 0;
  

}