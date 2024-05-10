/*
 * DAC8164.c
 *
 *  Created on: June 21, 2022
 *      Author: vrusu
 */

#include "dac8164.h"
#include "stdint.h"
#include <stdio.h>
#include "gpio.h"
#include "MCP23S08.h"
#include "utils.h"
#include <unistd.h>

#define DAC8164DELAY 2 // in uS


int DAC8164_setup(DAC8164 *self, MCP *MCP, uint8_t sync, int sclk, uint8_t sdi, int enable_pin, uint8_t ldac_pin)
{
  self->_MCP = MCP;
  self->_sync_pin = sync;
  self->_sclk_pin = sclk;
  self->_sdi_pin = sdi;
  self->_enable_pin = enable_pin;
  self->_ldac_pin = ldac_pin;

  char error_msg[100];


  if (MCP_pinMode(self->_MCP, self->_sync_pin, OUTPUT) == -1) {
    sprintf(error_msg, "dac8164_setup _sync_pin MCP_pinMode fail: %u", self->_sync_pin);
    error_log(error_msg);

    return -1;
  }
  if (MCP_pinWrite(self->_MCP, self->_sync_pin, HIGH) == -1) {
    sprintf(error_msg, "dac8164_setup _sync_pin MCP_pinWrite fail: %u", self->_sync_pin);
    error_log(error_msg);

    return -1;
  }


  if (MCP_pinMode(self->_MCP, self->_sclk_pin, OUTPUT) == -1) {
    sprintf(error_msg, "dac8164_setup _sclk_pin MCP_pinMode fail: %u", self->_sclk_pin);
    error_log(error_msg);

    return -1;
  }
  if (MCP_pinWrite(self->_MCP, self->_sclk_pin, LOW) == -1) {
    sprintf(error_msg, "dac8164_setup _sync_pin MCP_pinWrite fail: %u", self->_sclk_pin);
    error_log(error_msg);

    return -1;
  }

  if (MCP_pinMode(self->_MCP, self->_sdi_pin, OUTPUT) == -1) {
    sprintf(error_msg, "dac8164_setup _sync_pin MCP_pinMode fail: %u", self->_sdi_pin);
    error_log(error_msg);

    return -1;
  }
  if (MCP_pinWrite(self->_MCP, self->_sdi_pin, LOW) == -1) {
    sprintf(error_msg, "dac8164_setup _sync_pin MCP_pinWrite fail: %u", self->_sdi_pin);
    error_log(error_msg);

    return -1;
  }

  


  return 0;
}


void DAC8164_write(DAC8164 *self, uint32_t data)
{
  char error_msg[50];


  if (MCP_pinWrite(self->_MCP, self->_sclk_pin, 0) == -1) {
    sprintf(error_msg, "dac8164_write _sclk_pin fail: %u", self->_sclk_pin);
    error_log(error_msg);
  }
  
  if (MCP_pinWrite(self->_MCP, self->_sync_pin, 0) == -1) {
    sprintf(error_msg, "dac8164_write _sync_pin fail: %u", self->_sync_pin);
    error_log(error_msg);
  }
  usleep(DAC8164DELAY);

  for (int i=23;i>=0;i--){
    uint8_t thisbit;
    if ((0x1<<i) & data)
      thisbit = 1;
    else
      thisbit = 0;


    if (MCP_pinWrite(self->_MCP, self->_sdi_pin, thisbit) == -1) {
      sprintf(error_msg, "dac8164_write _sdi_pin fail: %u", self->_sdi_pin);
      error_log(error_msg);
    }
    usleep(DAC8164DELAY);

    if (MCP_pinWrite(self->_MCP, self->_sclk_pin, 1) == -1) {
      sprintf(error_msg, "dac8164_write _sclk_pin on fail: %u", self->_sclk_pin);
      error_log(error_msg);
    }
    usleep(DAC8164DELAY);

    if (MCP_pinWrite(self->_MCP, self->_sclk_pin, 0) == -1) {
      sprintf(error_msg, "dac8164_write _sclk_pin off fail: %u", self->_sclk_pin);
      error_log(error_msg);
    }
    usleep(DAC8164DELAY);
    
  }

  if (MCP_pinWrite(self->_MCP, self->_sync_pin, 1) == -1) {
    sprintf(error_msg, "dac8164_write _sync_pin on fail: %u", self->_sync_pin);
    error_log(error_msg);
  }
  
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
  uint32_t dac_mask;

  uint8_t mod_channel = channel % 4;

  if ((channel - mod_channel) == 8) {
    dac_mask = DAC_MASK_2;
  }
  else if ((channel - mod_channel) == 4) {
    dac_mask = DAC_MASK_1;
  }
  else {
    dac_mask = DAC_MASK_0;
  }
  mod_channel = mod_channel + 1;


  if (mod_channel == DAC_CHANNEL_A)
    data = DAC_SINGLE_CHANNEL_UPDATE  | dac_mask ;

  else if (mod_channel == DAC_CHANNEL_B)
    data = DAC_SINGLE_CHANNEL_UPDATE | DAC_MASK_DACSEL0 | dac_mask ;

  else if (mod_channel == DAC_CHANNEL_C)
    data = DAC_SINGLE_CHANNEL_UPDATE| DAC_MASK_DACSEL1 | dac_mask ;

  else if (mod_channel == DAC_CHANNEL_D)
    data = DAC_SINGLE_CHANNEL_UPDATE | DAC_MASK_DACSEL1 | DAC_MASK_DACSEL0 | dac_mask ;

  else if (mod_channel == DAC_CHANNEL_ALL)
    data = DAC_BROADCAST_UPDATE | DAC_MASK_DACSEL1 ;
  else
    // avoid writing bad data
    return;

  // value is 12 MSB bits (last LSB nibble to 0)

  data |= value << 2;
  // Send to chip
  DAC8164_write (self, data);
}

/*
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
*/
