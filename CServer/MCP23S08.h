/**
 * @file MCP23S08.h
 * @author Vadim Rusu (vadim.l.rusu@gmail.com)
 * @brief
 * @version 0.1
 * @date 2023-10-07
 *
 * @copyright Copyright (c) 2023
 *
 */

#ifndef MCP23S08_h
#define MCP23S08_h

/**
 * @brief registers defintion
 *
 */

/**
 * @brief I/O Direction registeer (1 = Input (default), 0 = Output)
 *
 */
#define IODIR (0x00)

/**
 * @brief IPOL Input Polarity Register (0 = Normal (default)(low reads as 0), 1 = Inverted (low reads as 1))
 *
 */
#define IPOLA (0x01)

/**
 * @brief Interrupt on Change Pin Assignements
 *
 */
#define GPINTEN (0x02)

/**
 * @brief Default Compare Register for Interrupt on Change. Opposite of what is here will trigger an interrupt (default = 0)
 *
 */
#define DEFVAL (0x03)

/**
 * @brief Interrupt on Change Control Register
 * 1 = pin is compared to DEFVAL, 0 = pin is compared to previous state (default)
 */
#define INTCON (0x04)

/**
 * @brief Configuration Register
 *
 */
#define IOCON (0x05)

/**
 * @brief Weak Pull-Up Resistor Register, this only affects inputs
 * 0 = No Internal 100k Pull-Up (default) 1 = Internal 100k Pull-Up
 */
#define GPPU (0x06)

/**
 * @brief Interrupt Flag Register. 1 = This Pin Triggered the Interrupt
 *
 */
#define INTF (0x07)

/**
 * @brief Interrupt Captured Value for Port Register
 * State of the Pin at the Time the Interrupt Occurred
 */
#define INTCAP (0x8)

/**
 * @brief GPIO Port Register
 * Value on the Port - Writing Sets Bits in the Output Latch
 */
#define GPIO (0x9)

/**
 * @brief Output Latch Register
 * 1 = Latch High, 0 = Latch Low (default) Reading Returns Latch State, Not Port Value!
 */
#define OLAT (0xA)

#define MCP_SPI_MODE 0

#define MCP_INPUT 1
#define MCP_OUTPUT 0

#define PUD_OFF 0
#define PUD_DOWN 1
#define PUD_UP 2

/**
 * @brief Bits in the IOCON register
 */

#define IOCON_UNUSED 0x01
#define IOCON_INTPOL 0x02
#define IOCON_ODR 0x04
#define IOCON_HAEN 0x08
#define IOCON_DISSLW 0x10
#define IOCON_SEQOP 0x20
#define IOCON_MIRROR 0x40
#define IOCON_BANK_MODE 0x80

#define IOCON_INIT (IOCON_HAEN)

#include <stdio.h>
#include <string.h>
#include <stdint.h>


extern uint8_t spi_bpw = 8; // bits per word
extern uint32_t spi_speed = 40000000; // 40MHz
extern uint16_t spi_delay = 0;

extern int         spiFds; //SPI file descriptor 


/**
 * @brief address = address of the MCP in use
 *
 */
typedef struct
{
    uint8_t _address;
    uint8_t _outputCache;
    uint8_t _pullupCache;
    uint8_t _invertCache;
    uint8_t _modeCache;
} MCP;

void MCP_setup(MCP *mcp, uint8_t address);

/**
 * @brief byteWrite, mostly internal use
 * 
 * @param mcp 
 */
void MCP_byteWrite(MCP *mcp, uint8_t, uint8_t); 
void MCP_pinMode(MCP *mcp, uint8_t, uint8_t);   

void MCP_pullupMode(MCP *mcp, uint8_t, uint8_t); 

void MCP_pinWrite(MCP *mcp, uint8_t, uint8_t); 

uint8_t MCP_pinRead(MCP *mcp, uint8_t);  
uint8_t MCP_byteRead(MCP *mcp, uint8_t); 

uint16_t MCP_pinReadAll(MCP *mcp);

void MCP_maskWrite(MCP *mcp, uint8_t mask, uint8_t value);
void MCP_maskpullupMode(MCP *mcp, uint8_t mask, uint8_t value);
void MCP_maskpinMode(MCP *mcp, uint8_t mask, uint8_t mode);

#endif // MCP23S08
