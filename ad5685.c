/*
 * AD5685.c
 *
 *  Created on: Feb 15, 2022
 *      Author: vrusu
 */

#include "ad5685.h"
#include "stdint.h"
#include "wiringPi.h"
#include "wiringPiSPI.h"
#include "mcp23s17.h"



void AD5685_setup(AD5685 *self, int csnMCP, uint8_t csnPin, int sclkMCP, uint8_t sclkPin, int sdiMCP, uint8_t sdiPin)
{
	self->_csnPin = csnPin;
	self->_sclkPin = sclkPin;
	self->_sdiPin = sdiPin;
	self->_csnMCP = csnMCP;
	self->_sclkMCP = sclkMCP;
	self->_sdiMCP = sdiMCP;



	
    digitalWrite(self->_csnMCP + self->_csnPin, 1);
    pinMode(self->_csnMCP + self->_csnPin, OUTPUT);
    digitalWrite(self->_sclkMCP + self->_sclkPin, 0);
    pinMode(self->_sclkMCP + self->_sclkPin, OUTPUT);
    digitalWrite(self->_sdiMCP + self->_sdiPin, 0);
    pinMode(self->_sdiMCP + self->_sdiPin, OUTPUT);


}


void AD5685_write(AD5685 *self, uint8_t address, uint16_t value)
{
  uint32_t dataWord = ((address & 0xFF) << 16) | value;


  digitalWrite(self->_sclkMCP + self->_sclkPin, 0);
  digitalWrite(self->_csnMCP + self->_csnPin, 0);
  delayMicroseconds(AD5685DELAY);
  for (int i=23;i>=0;i--){
    uint8_t thisbit;
    if ((0x1<<i) & dataWord)
      thisbit = 1;
    else
      thisbit = 0;
    
    digitalWrite(self->_sdiMCP + self->_sdiPin, thisbit);
    delayMicroseconds(AD5685DELAY);
    digitalWrite(self->_sclkMCP + self->_sclkPin, 1);
    delayMicroseconds(AD5685DELAY);
    digitalWrite(self->_sclkMCP + self->_sclkPin, 0);
    delayMicroseconds(AD5685DELAY);
  }
  digitalWrite(self->_csnMCP + self->_csnPin, 1);
  delayMicroseconds(AD5685DELAY);
}


void AD5685_setdac(AD5685 *self, uint8_t dacchannel, float value)
{
  uint32_t address = (AD5685_ADDR_DAC_WRITE << 4 ) | (1 << dacchannel);
  uint32_t digvalue = ( (int) (16383.*(value/2.5))) & 0x3FFF;
  //  printf(" Test %i\n",  (int) (16383.*(value/2.5)));
  
  AD5685_write(self,address, digvalue<<2);
    
  
}
