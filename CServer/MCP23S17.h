/* mbed MCP23S17 Library, for driving the MCP23S17 16-Bit I/O Expander with Serial Interface (SPI)
 * Copyright (c) 2015, Created by Steen Joergensen (stjo2809) inspired by Romilly Cocking MCP23S17 library
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
 
#include "mbed.h"

#ifndef MBED_MCP23S17_H
#define MBED_MCP23S17_H

//=============================================================================
// All Registers and there Address if BANK = 0
//=============================================================================

#define IODIRA_ADDR   0x00       // Controls the direction of the data I/O on Port A       
#define IODIRB_ADDR   0x01       // Controls the direction of the data I/O on Port B
#define IPOLA_ADDR    0x02       // Configure the polarity on the corresponding GPIO (Port A)
#define IPOLB_ADDR    0x03       // Configure the polarity on the corresponding GPIO (Port B)
#define GPINTENA_ADDR 0x04       // Controls the interrupt-on change feature for each pin for Port A
#define GPINTENB_ADDR 0x05       // Controls the interrupt-on change feature for each pin for Port B
#define DEFVALA_ADDR  0x06       // The default comparison value if the INTCONA is set to "1" for Port A
#define DEFVALB_ADDR  0x07       // The default comparison value if the INTCONA is set to "1" for Port B
#define INTCONA_ADDR  0x08       // Controls how the associated pin value is compared for the interrupt-on-change feature for Port A
#define INTCONB_ADDR  0x09       // Controls how the associated pin value is compared for the interrupt-on-change feature for Port B
#define IOCON_ADDR    0x0A       // Contains several bits for configuring the device
#define GPPUA_ADDR    0x0C       // Controls the pull-up resistors for the port pins for port A
#define GPPUB_ADDR    0x0D       // Controls the pull-up resistors for the port pins for port B
#define INTFA_ADDR    0x0E       // READ ONLY // reflects the interrupt condition on port A pins of any pin that is enabled for interrupts via the GPINTEN register.
#define INTFB_ADDR    0x0F       // READ ONLY // reflects the interrupt condition on port B pins of any pin that is enabled for interrupts via the GPINTEN register.
#define INTCAPA_ADDR  0x10       // READ ONLY // captures the GPIO port A value at the time the interrupt occurred
#define INTCAPB_ADDR  0x11       // READ ONLY // captures the GPIO port B value at the time the interrupt occurred
#define GPIOA_ADDR    0x12       // Reflects the value on the port A (doing write function it only read input)
#define GPIOB_ADDR    0x13       // Reflects the value on the port B (doing write function it only read input)
#define OLATA_ADDR    0x14       // A write to this register modifies the output latches that modifies the pins configured as outputs for Port A
#define OLATB_ADDR    0x15       // A write to this register modifies the output latches that modifies the pins configured as outputs for Port B

//=============================================================================
// Declaration of variables & custom #defines
//=============================================================================

#define INTERRUPT_MIRROR_BIT   0x40
#define INTERRUPT_POLARITY_BIT 0x02


//=============================================================================
// Functions Declaration
//=============================================================================

/** Interface to the MCP23S17 16-Bit I/O Expander with Serial Interface (SPI) 
 *
 *  Using the driver:
 *   - remenber to setup SPI in main routine.
 *   - remenber to setup interrupt pin or pins in main routine (if you are using interrupts).
 *
 *  Defaults in this driver:
 *   - as default is hardware adressing "On" and if disable use "0" in hardwareaddress when creating the instance.
 *   - as default is interrupt pins "Active High".
 *   - as default is INTA is associated with PortA and INTB is associated with PortB. 
 *
 *  Limitations of using this driver:
 *   - can't use Open-Drain output.
 *   - can't use Sequential Operation mode bit.
 *   - can't use BANK 1 addressing.
 *
 */
class MCP23S17 {
public:
    /** Create an instance of the MCP23S17 connected via specfied SPI instance, with the specified address.
     *
     * @param hardwareaddress The SPI hardware address 0-7 for this MCP23S17.
     * @param spi The mbed SPI instance (make in main routine)
     * @param nCs The SPI chip select pin.
     * @param nReset The Hardware reset pin.
     */
    MCP23S17(int hardwareaddress, SPI& spi, PinName nCs, PinName nReset);
    
    /** Create an instance of the MCP23S17 connected via specfied SPI instance, with the specified address, and Global reset only.
     *
     * @param hardwareaddress The SPI hardware address 0-7 for this MCP23S17.
     * @param spi The mbed SPI instance (make in main routine)
     * @param nCs The SPI chip select pin.
     */
    MCP23S17(int hardwareaddress, SPI& spi, PinName nCs);
    

    /** Read an Register address.
     *
     * @param reg_address The selected register to read from.
     * @return The 8 bits read, but if GPIO register only the value of the inputs (outputs is read as "0").
     */
    char read(char reg_address);

    /** Write to Register address.
     *
     * @param reg_adress The selected register to write to.
     * @param data The 8 bits to write to the register, but if GPIO only the output will change.
     */
    void write(char reg_address, char data);
    
    /** Write to Bit in a register.
     *
     * @param reg_adress The selected register to write to.
     * @param bit The bit with to write in, values from 1 to 8 
     * @param high_low The value to write the bit True = '1' and False = '0'.
     */
    void bit(char reg_address, int bitnumber, bool high_low);

    /** Resetting the MCP23S17.
     *
     * Reset has to be pull down for min. 1uS to insure correct reset.
     * This function pull down the reset pin for 5uS.
     */
    void reset();
    
    /** Read IODIRA.
     *
     * I/O DIRECTION REGISTER 
     * Controls the direction of the data I/O.
     *
     * @return The 8 bits read.
     */
    char iodira();

     /** Write to IODIRA.
     *
     * I/O DIRECTION REGISTER 
     * Controls the direction of the data I/O.
     *
     * @param data The 8 bits to write to IODIRA register.
     */
    void iodira(char data);
   
    /** Read IODIRB.
     *
     * I/O DIRECTION REGISTER 
     * Controls the direction of the data I/O.
     *
     * @return The 8 bits read.
     */
    char iodirb();

     /** Write to IODIRB.
     *
     * I/O DIRECTION REGISTER 
     * Controls the direction of the data I/O.
     *
     * @param data The 8 bits to write to IODIRB register.
     */
    void iodirb(char data);
    
    /** Read IPOLA.
     *
     * INPUT POLARITY REGISTER
     * This register allows the user to configure the polarity on the corresponding GPIO port bits.
     *
     * @return The 8 bits read.
     */
    char ipola();

     /** Write to IPOLA.
     *
     * INPUT POLARITY REGISTER
     * This register allows the user to configure the polarity on the corresponding GPIO port bits.
     *
     * @param data The 8 bits to write to IPOLA register.
     */
    void ipola(char data);    
    
    /** Read IPOLB.
     *
     * INPUT POLARITY REGISTER
     * This register allows the user to configure the polarity on the corresponding GPIO port bits.
     *
     * @return The 8 bits read.
     */
    char ipolb();

     /** Write to IPOLB.
     *
     * INPUT POLARITY REGISTER
     * This register allows the user to configure the polarity on the corresponding GPIO port bits.
     *
     * @param data The 8 bits to write to IPOLB register.
     */
    void ipolb(char data);
    
    /** Read GPINTENA.
     *
     * INTERRUPT-ON-CHANGE CONTROL REGISTER
     * The GPINTEN register controls the interrupt-onchange feature for each pin.
     *
     * @return The 8 bits read.
     */
    char gpintena();

     /** Write to GPINTENA.
     *
     * INTERRUPT-ON-CHANGE CONTROL REGISTER
     * The GPINTEN register controls the interrupt-onchange feature for each pin.
     *
     * @param data The 8 bits to write to GPINTENA register.
     */
    void gpintena(char data);

     /** Read GPINTENB.
     *
     * INTERRUPT-ON-CHANGE CONTROL REGISTER
     * The GPINTEN register controls the interrupt-onchange feature for each pin.
     *
     * @return The 8 bits read.
     */
    char gpintenb();

     /** Write to GPINTENB.
     *
     * INTERRUPT-ON-CHANGE CONTROL REGISTER
     * The GPINTEN register controls the interrupt-onchange feature for each pin.
     *
     * @param data The 8 bits to write to GPINTENB register.
     */
    void gpintenb(char data);
    
    /** Read DEFVALA.
     *
     * DEFAULT COMPARE REGISTER FOR INTERRUPT-ON-CHANGE
     * The default comparison value is configured in the DEFVAL register, If enabled (via GPINTEN and INTCON).
     *
     * @return The 8 bits read.
     */
    char defvala();

     /** Write to DEFVALA.
     *
     * DEFAULT COMPARE REGISTER FOR INTERRUPT-ON-CHANGE
     * The default comparison value is configured in the DEFVAL register, If enabled (via GPINTEN and INTCON).
     *
     * @param data The 8 bits to write to DEVALA register.
     */
    void defvala(char data);
    
    /** Read DEFVALB.
     *
     * DEFAULT COMPARE REGISTER FOR INTERRUPT-ON-CHANGE
     * The default comparison value is configured in the DEFVAL register, If enabled (via GPINTEN and INTCON).
     *
     * @return The 8 bits read.
     */
    char defvalb();

     /** Write to DEFVALB.
     *
     * DEFAULT COMPARE REGISTER FOR INTERRUPT-ON-CHANGE
     * The default comparison value is configured in the DEFVAL register, If enabled (via GPINTEN and INTCON).
     *
     * @param data The 8 bits to write to DEVALB register.
     */
    void defvalb(char data); 
    
    /** Read INTCONA.
     *
     * INTERRUPT CONTROL REGISTER
     * The INTCON register controls how the associated pin value is compared for the interrupt-on-change feature.
     *
     * @return The 8 bits read.
     */
    char intcona();

     /** Write to INTCONA.
     *
     * INTERRUPT CONTROL REGISTER
     * The INTCON register controls how the associated pin value is compared for the interrupt-on-change feature.
     *
     * @param data The 8 bits to write to INTCONA register.
     */
    void intcona(char data);
    
    /** Read INTCONB.
     *
     * INTERRUPT CONTROL REGISTER
     * The INTCON register controls how the associated pin value is compared for the interrupt-on-change feature.
     *
     * @return The 8 bits read.
     */
    char intconb();

     /** Write to INTCONB.
     *
     * INTERRUPT CONTROL REGISTER
     * The INTCON register controls how the associated pin value is compared for the interrupt-on-change feature.
     *
     * @param data The 8 bits to write to INTCONB register.
     */
    void intconb(char data);
    
    /** Read IOCON.
     *
     * CONFIGURATION REGISTER 
     * The IOCON register contains several bits for configuring the device.
     *
     * @return The 8 bits read.
     */
    char iocon();

    /** Write to IOCON.
     *
     * CONFIGURATION REGISTER 
     * The IOCON register contains several bits for configuring the device.
     *
     * @param data The 8 bits to write to IOCON register.
     */
    void iocon(char data);
    
     /** Read GPPUA.
     *
     * PULL-UP RESISTOR CONFIGURATION REGISTER 
     * The GPPU register controls the pull-up resistors for the port pins.
     *
     * @return The 8 bits read.
     */
    char gppua();

     /** Write to GPPUA.
     *
     * PULL-UP RESISTOR CONFIGURATION REGISTER 
     * The GPPU register controls the pull-up resistors for the port pins.
     *
     * @param data The 8 bits to write to GPPUA register.
     */
    void gppua(char data);

     /** Read GPPUB.
     *
     * PULL-UP RESISTOR CONFIGURATION REGISTER 
     * The GPPU register controls the pull-up resistors for the port pins.
     *
     * @return The 8 bits read.
     */
    char gppub();

     /** Write to GPPUB.
     *
     * PULL-UP RESISTOR CONFIGURATION REGISTER 
     * The GPPU register controls the pull-up resistors for the port pins.
     *
     * @param data The 8 bits to write to GPPUB register.
     */
    void gppub(char data);

     /** Read INTFA.
     *
     * INTERRUPT FLAG REGISTER - READ ONLY
     * The INTF register reflects the interrupt condition on the port pins of any pin that is enabled for interrupts via the GPINTEN register.
     *
     * @return The 8 bits read.
     */
    char intfa();
    
    /** Read INTFB.
     *
     * INTERRUPT FLAG REGISTER - READ ONLY
     * The INTF register reflects the interrupt condition on the port pins of any pin that is enabled for interrupts via the GPINTEN register.
     *
     * @return The 8 bits read.
     */
    char intfb();
    
    /** Read INTCAPA.
     *
     * INTERRUPT CAPTURE REGISTER - READ ONLY
     * The INTCAP register captures the GPIO port value at the time the interrupt occurred. The register is ‘read only’ and is updated only when an interrupt occurs.
     *
     * @return The 8 bits read.
     */
    char intcapa();
    
    /** Read INTCAPB.
     *
     * INTERRUPT CAPTURE REGISTER - READ ONLY
     * The INTCAP register captures the GPIO port value at the time the interrupt occurred. The register is ‘read only’ and is updated only when an interrupt occurs.
     *
     * @return The 8 bits read.
     */
    char intcapb();      
         
     /** Read GPIOA.
     *
     * PORT REGISTER
     * The GPIO register reflects the value on the port. Reading from this register reads the port. Writing to this register modifies the Output Latch (OLAT) register.
     *
     * @return The 8 bits read.
     */
    char gpioa();

     /** Write to GPIOA.
     *
     * PORT REGISTER
     * The GPIO register reflects the value on the port. Reading from this register reads the port. Writing to this register modifies the Output Latch (OLAT) register.
     *
     * @param data The 8 bits to write to GPIOA register.
     */
    void gpioa(char data);
    
    /** Read GPIOB.
     *
     * PORT REGISTER
     * The GPIO register reflects the value on the port. Reading from this register reads the port. Writing to this register modifies the Output Latch (OLAT) register.
     *
     * @return The 8 bits read.
     */
    char gpiob();

     /** Write to GPIOB.
     *
     * PORT REGISTER
     * The GPIO register reflects the value on the port. Reading from this register reads the port. Writing to this register modifies the Output Latch (OLAT) register.
     *
     * @param data The 8 bits to write to GPIOB register.
     */
    void gpiob(char data);
    
     /** Read OLATA.
     *
     * OUTPUT LATCH REGISTER
     * The OLAT register provides access to the output latches. A read from this register results in a read of the OLAT and not the port itself. A write to this register
     * modifies the output latches that modifies the pins configured as outputs.
     *
     * @return The 8 bits read.
     */
    char olata();

     /** Write to OLATA.
     *
     * OUTPUT LATCH REGISTER
     * The OLAT register provides access to the output latches. A read from this register results in a read of the OLAT and not the port itself. A write to this register
     * modifies the output latches that modifies the pins configured as outputs.
     *
     * @param data The 8 bits to write to OLATA register.
     */
    void olata(char data);
    
    /** Read OLATB.
     *
     * OUTPUT LATCH REGISTER
     * The OLAT register provides access to the output latches. A read from this register results in a read of the OLAT and not the port itself. A write to this register
     * modifies the output latches that modifies the pins configured as outputs.
     *
     * @return The 8 bits read.
     */
    char olatb();

     /** Write to OLATB.
     *
     * OUTPUT LATCH REGISTER
     * The OLAT register provides access to the output latches. A read from this register results in a read of the OLAT and not the port itself. A write to this register
     * modifies the output latches that modifies the pins configured as outputs.
     *
     * @param data The 8 bits to write to OLATB register.
     */
    void olatb(char data);
    
     /** Write to IOCON.MIRROR
     *
     * IOCON REGISTER - INTERRUPT MIRROR BIT
     * 1 = The INT pins are internally connected
     * 0 = The INT pins are not connected. INTA is associated with PortA and INTB is associated with PortB
     *
     * @param mirror write true ('1') or false ('0').
     */
    void intmirror(bool mirror);
    
     /** Write to IOCON.INTPOL
     *
     * IOCON REGISTER - INTERRUPT POLARITY BIT
     * This bit sets the polarity of the INT output pin.
     * 1 = Active-high.
     * 0 = Active-low.
     *
     * @param polarity write true ('1') or false ('0').
     */
    void intpol(bool polarity);

private:
    int _hardwareaddress;
    SPI& _spi;
    DigitalOut _nCs;
    DigitalOut _nReset;
    char _writeopcode;
    char _readopcode;
    void _initialization();
    void _make_opcode(int _hardwareaddress);
    char _read(char address);                          
    void _write(char address, char data);             

};

#endif
