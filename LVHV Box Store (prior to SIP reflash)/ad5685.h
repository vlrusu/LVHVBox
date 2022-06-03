/*
 * AD5685.h
 *
 *  Created on: Feb 15 2022
 *      Author: vrusu
 */

#ifndef AD5685_H_
#define AD5685_H_

#include <stdint.h>

#define AD5685DELAY 2

#define AD5685_ADDR_NOOP             0x0
#define AD5685_ADDR_DAC_WRITE        0x3
#define AD5685_ADDR_RESET            0x6
#define AD5685_ADDR_READBACK         0x9


typedef struct {
  int _csnMCP; //pin bases
  int _sclkMCP;
  int _sdiMCP;
  uint8_t _csnPin;
  uint8_t _sclkPin;
  uint8_t _sdiPin;
  uint8_t _nbits;
} AD5685;

void AD5685_setup(AD5685 *self, int csnMCP, uint8_t csnPin, int sclkMCP, uint8_t sclkPin, int sdiMCP, uint8_t sdiPin);
void AD5685_write(AD5685 *self, uint8_t channel, uint16_t value);
void AD5685_setdac(AD5685 *self, uint8_t dacchannel, float value);

#endif /* AD5685_H_ */
