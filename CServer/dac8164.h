/*
 * DAC8164.h
 *
 *  Created on: June 22 2022
 *      Author: vrusu
 */

#ifndef DAC8164_H_
#define DAC8164_H_

#include <stdint.h>
#include "MCP23S08.h"


// 24 bits code definition
#define DAC_REFERENCE_ALWAYS_POWERED_DOWN  0x2000
#define DAC_REFERENCE_POWERED_TO_DEFAULT   0x0000
#define DAC_REFERENCE_ALWAYS_POWERED_UP    0x1000

#define DAC_DATA_INPUT_REGISTER    0x011000

#define DAC_MASK_LD1        0x200000
#define DAC_MASK_LD0        0x100000
#define DAC_MASK_DACSEL1    0x040000
#define DAC_MASK_DACSEL0    0x020000
#define DAC_MASK_PD0        0x010000
#define DAC_MASK_PD1        0x008000
#define DAC_MASK_PD2        0x004000
#define DAC_MASK_DATA       0x00FFF0

#define DAC_MASK_0          0x0
#define DAC_MASK_1          0x400000
#define DAC_MASK_2          0x800000

#define DAC_SINGLE_CHANNEL_STORE    0 /* LD1=0,LD0=0 */
#define DAC_SINGLE_CHANNEL_UPDATE   DAC_MASK_LD0 /* LD1=0,LD0=1 */
#define DAC_SIMULTANEOUS_UPDATE     DAC_MASK_LD1 /* LD1=1,LD0=0 */
#define DAC_BROADCAST_UPDATE        DAC_MASK_LD1 | DAC_MASK_LD0 /* LD1=1,LD0=1 */

#define DAC_POWER_DOWN_1K   DAC_MASK_PD2
#define DAC_POWER_DOWN_100K DAC_MASK_PD1
#define DAC_POWER_DOWN_HIZ  DAC_MASK_PD2 | DAC_MASK_PD1

// 8 bit constant to pass only 8 bits paramaeters
#define DAC_CHANNEL_A   1
#define DAC_CHANNEL_B   2
#define DAC_CHANNEL_C   3
#define DAC_CHANNEL_D   4
#define DAC_CHANNEL_ALL 5

#define DAC_MAX_SCALE 4096 // Max Scale points (DAC 14 bits)


typedef struct {
  MCP *_MCP;
  uint8_t _sync_pin; //pin bases
  uint8_t _sclk_pin;
  uint8_t _sdi_pin;
  uint8_t _enable_pin;
  uint8_t _ldac_pin;
} DAC8164;

void DAC8164_write(DAC8164 *self, uint32_t data);
void DAC8164_setup(DAC8164 *self, MCP *MCP, uint8_t sync, int sclk, uint8_t sdi, int enable_pin, uint8_t ldac_pin);
void DAC8164_setReference(DAC8164 *self, uint16_t reference);
void DAC8164_writeChannel(DAC8164 *self, uint8_t channel, uint16_t value);
void DAC8164_setChannelPower(DAC8164 *self, uint8_t channel, uint16_t power);



#endif /* DAC8164_H_ */
