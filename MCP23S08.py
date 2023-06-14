import spidev
import RPi.GPIO as GPIO



class MCP23S08(object):
    """This class provides an abstraction of the GPIO expander MCP23S17
    for the Raspberry Pi.
    It is depndent on the Python packages spidev and RPi.GPIO, which can
    be get from https://pypi.python.org/pypi/RPi.GPIO/0.5.11 and
    https://pypi.python.org/pypi/spidev.
    """
    PULLUP_ENABLED = 0
    PULLUP_DISABLED = 1

    DIR_INPUT = 0
    DIR_OUTPUT = 1

    LEVEL_LOW = 0
    LEVEL_HIGH = 1

    """Register addresses as documentined in the technical data sheet at
    http://ww1.microchip.com/downloads/en/DeviceDoc/21952b.pdf
    """
    MCP23S08_IODIR = 0x00
    MCP23S08_IPOL  = 0x01
    MCP23S08_GPINTEN  = 0x02
    MCP23S08_DEFVAL  = 0x03
    MCP23S08_INTCON  = 0x04
    MCP23S08_IOCON  = 0x05
    MCP23S08_GPPU  = 0x06
    MCP23S08_INTF  = 0x07
    MCP23S08_INTCAP  = 0x08
    MCP23S08_GPIO  = 0x09
    MCP23S08_OLAT  = 0x0A    
    """Bit field flags as documentined in the technical data sheet at
    http://ww1.microchip.com/downloads/en/DeviceDoc/21952b.pdf
    """
    IOCON_UNUSED = 0x01
    IOCON_INTPOL = 0x02
    IOCON_ODR = 0x04
    IOCON_HAEN = 0x08
    IOCON_DISSLW = 0x10
    IOCON_SPREAD = 0x20

    IOCON_INIT = 0x28  # IOCON_SEQOP and IOCON_HAEN from above

    MCP23S08_CMD_WRITE = 0x40
    MCP23S08_CMD_READ = 0x41

    def __init__(self, bus=0, pin_cs=0, pin_reset=-1, device_id=0x00):
        """
        Constructor
        Initializes all attributes with 0.

        Keyword arguments:
        device_id -- The device ID of the component, i.e., the hardware address (default 0)
        pin_cs -- The Chip Select pin of the MCP, default 0
        pin_reset -- The Reset pin of the MCP
        """
        self.device_id = device_id
        self._GPIO = 0
        self._IODIR = 0
        self._GPPU = 0
        self._pin_reset = pin_reset
        self._bus = bus
        self._pin_cs = pin_cs
        self._spimode = 0b00
        self._spi = spidev.SpiDev()
        self.isInitialized = False

    def open(self):
        """Initializes the MCP23S08 with hardware-address access
        and sequential operations mode.
        """
        self._setupGPIO()
        self._spi.open(self._bus, self._pin_cs)
        self.isInitialized = True
        self._writeRegister(MCP23S08.MCP23S08_IOCON, MCP23S08.IOCON_INIT)

        # set defaults
        for index in range(0, 7):
            self.setDirection(index, MCP23S08.DIR_INPUT)
            self.setPullupMode(index, MCP23S08.PULLUP_ENABLED)

    def close(self):
        """Closes the SPI connection that the MCP23S08 component is using.
        """
        self._spi.close()
        self.isInitialized = False

    def setPullupMode(self, pin, mode):
        """Enables or disables the pull-up mode for input pins.

        Parameters:
        pin -- The pin index (0 - 7)
        mode -- The pull-up mode (MCP23S08.PULLUP_ENABLED, MCP23S08.PULLUP_DISABLED)
        """

        assert pin < 8
        assert (mode == MCP23S08.PULLUP_ENABLED) or (mode == MCP23S08.PULLUP_DISABLED)
        assert self.isInitialized


        register = MCP23S08.MCP23S08_GPPU
        data = self._GPPU
        noshifts = pin

        if mode == MCP23S08.PULLUP_ENABLED:
            data |= (1 << noshifts)
        else:
            data &= (~(1 << noshifts))

        self._writeRegister(register, data)


        self._GPPU = data

    def setDirection(self, pin, direction):
        """Sets the direction for a given pin.

        Parameters:
        pin -- The pin index (0 - 7)
        direction -- The direction of the pin (MCP23S08.DIR_INPUT, MCP23S08.DIR_OUTPUT)
        """

        assert (pin < 8)
        assert ((direction == MCP23S08.DIR_INPUT) or (direction == MCP23S08.DIR_OUTPUT))
        assert self.isInitialized

        register = MCP23S08.MCP23S08_IODIR
        data = self._IODIR
        noshifts = pin

        if direction == MCP23S08.DIR_INPUT:
            data |= (1 << noshifts)
        else:
            data &= (~(1 << noshifts))

        self._writeRegister(register, data)


        self._IODIR = data

    def digitalRead(self, pin):
        """Reads the logical level of a given pin.

        Parameters:
        pin -- The pin index (0 - 7)
        Returns:
         - MCP23S08.LEVEL_LOW, if the logical level of the pin is low,
         - MCP23S08.LEVEL_HIGH, otherwise.
        """

        assert self.isInitialized
        assert (pin < 8)

        self._GPIO = self._readRegister(MCP23S08.MCP23S08_GPIO)
        if (self._GPIO & (1 << pin)) != 0:
          return MCP23S08.LEVEL_HIGH
        else:
          return MCP23S08.LEVEL_LOW

    def digitalWrite(self, pin, level):
        """Sets the level of a given pin.
        Parameters:
        pin -- The pin index (0 - 7)
        level -- The logical level to be set (LEVEL_LOW, LEVEL_HIGH)
        """

        assert self.isInitialized
        assert (pin < 8)
        assert (level == MCP23S08.LEVEL_HIGH) or (level == MCP23S08.LEVEL_LOW)

        register = MCP23S08.MCP23S08_GPIO
        data = self._GPIO
        noshifts = pin

        if level == MCP23S08.LEVEL_HIGH:
            data |= (1 << noshifts)
        else:
            data &= (~(1 << noshifts))

        self._writeRegister(register, data)


        self._GPIO = data

    def writeGPIO(self, data):
        """Sets the data port value for all pins.
        Parameters:
        data - The 8-bit value to be set.
        """

        assert self.isInitialized

        self._GPIO = (data & 0xFF)
        self._writeRegisterWord(MCP23S08.MCP23S08_GPIO, data)

    def readGPIO(self):
        """Reads the data port value of all pins.
        Returns:
         - The 8-bit data port value
        """

        assert self.isInitialized
        data = self._readRegisterWord(MCP23S08.MCP23S08_GPIO)
        self._GPIO = (data & 0xFF)
        return data

    def _writeRegister(self, register, value):
        assert self.isInitialized
        command = MCP23S08.MCP23S08_CMD_WRITE | (self.device_id << 1)
        self._setSpiMode(self._spimode)
        self._spi.xfer2([command, register, value])

    def _readRegister(self, register):
        assert self.isInitialized
        command = MCP23S08.MCP23S08_CMD_READ | (self.device_id << 1)
        self._setSpiMode(self._spimode)
        data = self._spi.xfer2([command, register, 0])
        return data[2]

    def _readRegisterWord(self, register):
        assert self.isInitialized
        buffer = [0, 0]
        buffer[0] = self._readRegister(register)
        buffer[1] = self._readRegister(register + 1)
        return (buffer[1] << 8) | buffer[0]

    def _writeRegisterWord(self, register, data):
        assert self.isInitialized
        self._writeRegister(register, data & 0xFF)
        self._writeRegister(register + 1, data >> 8)

    def _setupGPIO(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)

        if self._pin_reset != -1:
            GPIO.setup(self._pin_reset, GPIO.OUT)
            GPIO.output(self._pin_reset, True)

    def _setSpiMode(self, mode):
        if self._spi.mode != mode:
            self._spi.mode = mode
            self._spi.xfer2([0])  # dummy write, to force CLK to correct level
