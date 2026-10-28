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

#define DAC8164DELAY 20 // in uS

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


int DAC8164_write(DAC8164 *self, uint32_t data)
{
  if (!self || !self->_MCP || data > 0xFFFFFFu) return -1;
  if (MCP_pinWrite(self->_MCP, self->_sclk_pin, LOW) < 0) goto failed;
  if (MCP_pinWrite(self->_MCP, self->_sync_pin, LOW) < 0) goto failed;
  usleep(DAC8164DELAY);
  for (int i = 23; i >= 0; --i){
    uint8_t bit = (data >> i) & 1u;
    if (MCP_pinWrite(self->_MCP, self->_sdi_pin, bit) < 0) goto failed;
    usleep(DAC8164DELAY);
    if (MCP_pinWrite(self->_MCP, self->_sclk_pin, HIGH) < 0) goto failed;
    usleep(DAC8164DELAY);
    if (MCP_pinWrite(self->_MCP, self->_sclk_pin, LOW) < 0) goto failed;
    usleep(DAC8164DELAY);
  }
  if (MCP_pinWrite(self->_MCP, self->_sync_pin, HIGH) < 0) goto failed;
  return 0;
failed:
  error_log("DAC8164 transfer failed; physical setting is unknown");
  // Stop transmitting; best-effort idle restoration is not a command retry.
  MCP_pinWrite(self->_MCP, self->_sclk_pin, LOW);
  MCP_pinWrite(self->_MCP, self->_sync_pin, HIGH);
  return -1;
}


int DAC8164_setReference(DAC8164 *self, uint16_t reference)
{
  uint32_t data = DAC_MASK_PD0;

  // set reference mde
  data |= reference;

  return DAC8164_write(self, data);

}


int DAC8164_writeChannel(DAC8164 *self, uint8_t channel, uint16_t value)
{
  if (!self || !self->_MCP || channel >= LVHV_HV_CHANNELS || value > LVHV_HV_DAC_MAX) return -1;
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
    return -1;

  // value is 12 MSB bits (last LSB nibble to 0)

  data |= value << 2;
  // Send to chip
  return DAC8164_write(self, data);
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
