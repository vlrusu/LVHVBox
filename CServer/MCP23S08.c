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
#include "utils.h"



#define MCPDELAY 1

// Control byte and configuration register information - Control Byte: "0100 A2 A1 A0 R/W" -- W=0

#define OPCODEW (0b01000000) // Opcode for MCP23S17 with LSB (bit0) set to write (0), address OR'd in later, bits 1-3
#define OPCODER (0b01000001) // Opcode for MCP23S17 with LSB (bit0) set to read (1), address OR'd in later, bits 1-3


int MCP_setup(MCP* mcp, uint8_t address)
{
  mcp->_address = address;

  if (MCP_byteWrite(mcp, IOCON, IOCON_INIT) == -1) {
    return  -1;
  }

  mcp->_modeCache = 0xFF;   // Default I/O mode is all input, 0xFFFF
  mcp->_outputCache = 0x00; // Default output state is all off, 0x0000
  mcp->_pullupCache = 0x00; // Default pull-up state is all off, 0x0000
  mcp->_invertCache = 0x00; // Default input inversion state is not inverted, 0x0000

  if (MCP_byteWrite(mcp, IODIR, mcp->_modeCache) == -1) {
    return -1;
  } else if (MCP_byteWrite(mcp, IOCON, IOCON_INIT) == -1) {
    return -1;
  }

  return 0;
};

int MCP_byteWrite(MCP *mcp, uint8_t reg, uint8_t value)
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
  if ((ioctl(spiFds, SPI_IOC_MESSAGE(1), &spi) < 0)) {


    // create and store error message
    char error_msg[50];
    sprintf(error_msg, "mcp23s08_write_reg: Error during SPI transaction.");
    error_log(error_msg);

    // display error message
    perror(error_msg);


    return -1;
  }

  return 0; // return value for succesful execution

}



// MODE SETTING FUNCTIONS - BY PIN

int MCP_pinMode(MCP *mcp, uint8_t pin, uint8_t mode)
{ // Accept the pin # and I/O mode

  if (pin > 16) {
    // create and store error message
    char error_msg[50];
    sprintf(error_msg, "MCP_pinMode, pin out of bounds: %u", pin);
    error_log(error_msg);

    // display error message
    perror(error_msg);

    return -1;
  }
  if (mode == MCP_INPUT)
  {                                // Determine the mode before changing the bit state in the mode cache
    mcp->_modeCache |= 1 << (pin); // Since input = "HIGH", OR in a 1 in the appropriate place
  }
  else
  {
    mcp->_modeCache &= ~(1 << (pin)); // If not, the mode must be output, so and in a 0 in the appropriate place
  }

  if (MCP_byteWrite(mcp, IODIR, mcp->_modeCache) == -1) {
    return -1; // return -1 upon bytewrite failure
  }

  return 0;
}

// WRITE FUNCTIONS

int MCP_pinWrite(MCP *mcp, uint8_t pin, uint8_t value)
{

  if (pin > 16)
  {
    // create and store error message
    char error_msg[50];
    sprintf(error_msg, "MCP_pinWrite, pin out of bounds: %u", pin);
    error_log(error_msg);

    // display error message
    perror(error_msg);

    return -1;
  }

  if (value) {
    mcp->_outputCache |= 1 << (pin);
  } else {
    mcp->_outputCache &= ~(1 << (pin));
  }
  
  if (MCP_byteWrite(mcp, GPIO, mcp->_outputCache) == -1) {
    return -1;
  }

  return 0;
}
