/**
 * @file MCP23S08.c
 * @author Vadim Rusu (vadim.l.rusu@gmail.com)
 * @brief
 * @version 0.1
 * @date 2023-10-07
 *
 * @copyright Copyright (c) 2023
 *
 */

#include "MCP23S08.h" // Header files for this class

#include <sys/ioctl.h>
#include <linux/spi/spidev.h>
#include "gpio.h"



#define MCPDELAY 1

// Control byte and configuration register information - Control Byte: "0100 A2 A1 A0 R/W" -- W=0

#define OPCODEW (0b01000000) // Opcode for MCP23S17 with LSB (bit0) set to write (0), address OR'd in later, bits 1-3
#define OPCODER (0b01000001) // Opcode for MCP23S17 with LSB (bit0) set to read (1), address OR'd in later, bits 1-3


void MCP_setup(MCP* mcp, uint8_t address)
{
  mcp->_address = address;

  MCP_byteWrite(mcp, IOCON, IOCON_INIT);

  mcp->_modeCache = 0xFF;   // Default I/O mode is all input, 0xFFFF
  mcp->_outputCache = 0x00; // Default output state is all off, 0x0000
  mcp->_pullupCache = 0x00; // Default pull-up state is all off, 0x0000
  mcp->_invertCache = 0x00; // Default input inversion state is not inverted, 0x0000

  MCP_byteWrite(mcp, IODIR, mcp->_modeCache);
  MCP_byteWrite(mcp, IOCON, IOCON_INIT);
};

void MCP_byteWrite(MCP *mcp, uint8_t reg, uint8_t value)
{ // Accept the register and byte

  uint8_t tx_buf[3];
  tx_buf[0] = OPCODEW | (mcp->_address << 1);
  tx_buf[1] = reg;
  tx_buf[2] = value;
  uint8_t rx_buf[sizeof tx_buf];

  struct spi_ioc_transfer spi;
  memset(&spi, 0, sizeof(spi));
  spi.tx_buf = (unsigned long)tx_buf;
  spi.rx_buf = (unsigned long)rx_buf;
  spi.len = sizeof tx_buf;
  spi.delay_usecs = spi_delay;
  spi.speed_hz = spi_speed;
  spi.bits_per_word = spi_bpw;


  // do the SPI transaction
  if ((ioctl(spiFds, SPI_IOC_MESSAGE(1), &spi) < 0))
  {
    printf(
        "mcp23s08_write_reg: There was a error during the SPI "
        "transaction.\n");
  }

}

uint8_t MCP_byteRead(MCP *mcp, uint8_t reg)
{
  uint8_t tx_buf[3];
  tx_buf[0] = OPCODER | (mcp->_address << 1);
  tx_buf[1] = reg;
  tx_buf[2] = 0;

  uint8_t rx_buf[3];

  struct spi_ioc_transfer spi;
  memset(&spi, 0, sizeof(spi));
  spi.tx_buf = (unsigned long)tx_buf;
  spi.rx_buf = (unsigned long)rx_buf;
  spi.len = sizeof tx_buf;
  spi.delay_usecs = spi_delay;
  spi.speed_hz = spi_speed;
  spi.bits_per_word = spi_bpw;

  // do the SPI transaction
  if ((ioctl(spiFds, SPI_IOC_MESSAGE(1), &spi) < 0))
  {
    printf(
        "mcp23s08_read_reg: There was a error during the SPI "
        "transaction.\n");
    return -1;
  }

  uint8_t recv = rx_buf[2];

  return recv;
}

// MODE SETTING FUNCTIONS - BY PIN

void MCP_pinMode(MCP *mcp, uint8_t pin, uint8_t mode)
{ // Accept the pin # and I/O mode

  if (pin > 16)
  {
    printf("pin outta bounds\n");
    return;
  }
  if (mode == MCP_INPUT)
  {                                // Determine the mode before changing the bit state in the mode cache
    mcp->_modeCache |= 1 << (pin); // Since input = "HIGH", OR in a 1 in the appropriate place
  }
  else
  {
    mcp->_modeCache &= ~(1 << (pin)); // If not, the mode must be output, so and in a 0 in the appropriate place
  }
  MCP_byteWrite(mcp, IODIR, mcp->_modeCache);
}

void MCP_maskpinMode(MCP *mcp, uint16_t mask, uint8_t mode)
{
  // idea here is that all devices off the MCP do the same thing

  if (mode == MCP_INPUT)
    mcp->_modeCache = (mcp->_modeCache & ~mask) | (0xffff & mask);
  else
    mcp->_modeCache = (mcp->_modeCache & ~mask) | (0 & mask);

  MCP_maskWrite(mcp, IODIR, mcp->_modeCache);
}

// THE FOLLOWING WRITE FUNCTIONS ARE NEARLY IDENTICAL TO THE FIRST AND ARE NOT INDIVIDUALLY COMMENTED

// WEAK PULL-UP SETTING FUNCTIONS - BY WORD AND BY PIN

void MCP_pullupMode(MCP *mcp, uint8_t pin, uint8_t mode)
{

  if (pin > 16)
  {
    printf("pin outta bounds\n");
    return;
  }
  if (mode == ON)
  {
    mcp->_pullupCache |= 1 << (pin);
  }
  else
  {
    mcp->_pullupCache &= ~(1 << (pin));
  }
  MCP_maskWrite(mcp, GPPU, mcp->_pullupCache);
}

void MCP_maskpullupMode(MCP *mcp, uint16_t mask, uint8_t mode)
{
  // idea here is that all devices off the MCP do the same thing

  if (mode == ON)
    mcp->_pullupCache = (mcp->_pullupCache & ~mask) | (0xffff & mask);
  else
    mcp->_pullupCache = (mcp->_pullupCache & ~mask) | (0 & mask);

  MCP_maskWrite(mcp, GPPU, mcp->_pullupCache);
}

// WRITE FUNCTIONS

void MCP_pinWrite(MCP *mcp, uint8_t pin, uint8_t value)
{
  if (pin > 16)
  {
    
    printf("pin outta bounds: %d\n",pin);
    return;
  }

  if (value)
  {
    mcp->_outputCache |= 1 << (pin);
  }
  else
  {
    mcp->_outputCache &= ~(1 << (pin));
  }
  MCP_byteWrite(mcp, GPIO, mcp->_outputCache);
}

void MCP_maskWrite(MCP *mcp, uint16_t mask, uint8_t value)
{
  // idea here is that all devices off the MCP do the same thing

  if (value)
    mcp->_outputCache = (mcp->_outputCache & ~mask) | (0xffff & mask);
  else
    mcp->_outputCache = (mcp->_outputCache & ~mask) | (0 & mask);

  MCP_maskWrite(mcp, GPIO, mcp->_outputCache);
}
