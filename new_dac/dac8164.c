/*
 * DAC8164.c
 *
 *  Created on: June 21, 2022
 *      Author: vrusu
 */

#include "dac8164.h"
#include "stdint.h"
#include "wiringPi.h"
#include "wiringPiSPI.h"
#include "mcp23s17.h"

#define DAC8164DELAY 2


void DAC8164_setup(DAC8164 *self, int MCP, uint8_t sync, int sclk, uint8_t sdi, int enable_pin, uint8_t ldac_pin)
{
  self->_MCP = MCP;
  self->_sync_pin = sync;
  self->_sclk_pin = sclk;
  self->_sdi_pin = sdi;
  self->_enable_pin = enable_pin;
  self->_ldac_pin = ldac_pin;


  if (enable_pin != -1) {
    digitalWrite(self->_MCP + self->_enable_pin, HIGH);
    pinMode(self->_MCP + self->_enable_pin, OUTPUT);
  }


   // LDAC to low
  if (ldac_pin != -1)
  {
    digitalWrite(self->_MCP + self->_ldac_pin, HIGH);
    pinMode(self->_MCP + self->_ldac_pin, OUTPUT);

  }

  digitalWrite(self->_MCP + self->_sync_pin, 1);
  pinMode(self->_MCP + self->_sync_pin, OUTPUT);

  digitalWrite(self->_MCP + self->_sclk_pin, 0);
  pinMode(self->_MCP + self->_sclk_pin, OUTPUT);

  digitalWrite(self->_MCP + self->_sdi_pin, 0);
  pinMode(self->_MCP + self->_sdi_pin, OUTPUT);


}

void DAC8164_write(DAC8164 *self, uint32_t data)
{

  if (self->_enable_pin != -1)
    digitalWrite(self->_MCP + self->_enable_pin, LOW);


  digitalWrite(self->_MCP + self->_sclk_pin, 0);
  digitalWrite(self->_MCP + self->_sync_pin, 0);
  delayMicroseconds(DAC8164DELAY);

  for (int i=23;i>=0;i--){
    uint8_t thisbit;
    if ((0x1<<i) & data)
      thisbit = 1;
    else
      thisbit = 0;

    digitalWrite(self->_MCP + self->_sdi_pin, thisbit);
    delayMicroseconds(DAC8164DELAY);
    digitalWrite(self->_MCP + self->_sclk_pin, 1);
    delayMicroseconds(DAC8164DELAY);
    digitalWrite(self->_MCP + self->_sclk_pin, 0);
    delayMicroseconds(DAC8164DELAY);
  }
  digitalWrite(self->_MCP + self->_sync_Pin, 1);


  if (self->_enable_pin != -1)
    digitalWrite(self->_enable_pin, HIGH);
}


void DAC8164_setReference(DAC8164 *self, uint16_t reference)
{
  uint32_t data = DAC_MASK_PD0;

  // set reference mde
  data |= reference;

  DAC8164_write(self, data);

}


void DAC8164_writeChannel(DAC8164 *self, uint8_t channel, uint16_t value)
{
  uint32_t data ;

  if (channel == DAC_CHANNEL_A)
    data = DAC_SINGLE_CHANNEL_UPDATE;

  else if (channel == DAC_CHANNEL_B)
    data = DAC_SINGLE_CHANNEL_UPDATE | DAC_MASK_DACSEL0 ;

  else if (channel == DAC_CHANNEL_C)
    data = DAC_SINGLE_CHANNEL_UPDATE| DAC_MASK_DACSEL1 ;

  else if (channel == DAC_CHANNEL_D)
    data = DAC_SINGLE_CHANNEL_UPDATE | DAC_MASK_DACSEL1 | DAC_MASK_DACSEL0 ;

  else if (channel == DAC_CHANNEL_ALL)
    data = DAC_BROADCAST_UPDATE | DAC_MASK_DACSEL1 ;

  else
    // avoid writing bad data
    return;

  // value is 12 MSB bits (last LSB nibble to 0)
  data |= value << 4;

  // Send to chip
  DAC8164_write (self, data);
}

void DAC8164_setChannelPower(DAC8164 *self, uint8_t channel, uint16_t power)
{
  // Default we'll set power
  uint32_t data = power | DAC_MASK_PD0 ;

  if (channel == DAC_CHANNEL_A)
    data |= DAC_SINGLE_CHANNEL_UPDATE;

  else if (channel == DAC_CHANNEL_B)
    data |= DAC_SINGLE_CHANNEL_UPDATE | DAC_MASK_DACSEL0 ;

  else if (channel == DAC_CHANNEL_C)
    data |= DAC_SINGLE_CHANNEL_UPDATE| DAC_MASK_DACSEL1 ;

  else if (channel == DAC_CHANNEL_D)
    data |= DAC_SINGLE_CHANNEL_UPDATE | DAC_MASK_DACSEL1 | DAC_MASK_DACSEL0 ;

  else if (channel == DAC_CHANNEL_ALL)
    data |= DAC_BROADCAST_UPDATE | DAC_MASK_DACSEL1 ;

  // Send to chip
  DAC8164_write (self, data);
}
