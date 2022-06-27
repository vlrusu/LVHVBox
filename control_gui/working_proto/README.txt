// Isaiah Wardlaw || University of Minnesota Twin Cities //
// Summer 2022 //
// Fermilab || Mu2e //


// Purpose of this repository //

Working together, the difference scripts in this repository permit the Mu2e LVHV
boxes to be controlled through a convenient and simple touchscreen GUI. Additionally,
this code logs data and keeps track of errors.

// Included Files (not including .o and .so compiled scripts) //

gui_main.py:
  This is the main file in the repository, controlling a pyqt4 gui. This python script
  allows users to control all hv channels and lv channels through a simple touchscreen
  interface.

ad5685.c:
  Driver for hv.

ad5685.h:
  Header file for hv.

python_connect.c:
  Has function(s) in C that need to be called in python by gui_main.py.





// File Breakdowns by pertinent Functions //

|| gui_main.py ||

  ||||| ** class Session() ** |||||

    The Session class focuses on interactions with the hardware, providing
    them to the Window (main gui) class.

  ** power_on(self, channel) **

    Sets one lv channel on.

  ** power_off(self, channel) **

    Sets one lv channel off.

  ** initialize_lv(self, test) **

    Initializes the lv connection. Currently, has to be run more than
    once to reliably set up the connection. Not sure why, that will
    have to be rectified at some point... TODO.

  ** initialize_hv(self, test) **

    Calls the initialization function from python_connect.c through
    the .so file.

  ** hv_rampup_on_off(self) **

    Sets self.is_ramping to True. This ensures that the script doesn't
    try to interact with more than one hv channel at a time. Then it
    ramps up/ramps down the latest item in self.rampup_list. When done,
    it sets self.is_ramping to false so that the next selected hv
    channel may be actuated.

  ** call_hv_data(self) **

    If the variable self.acquiring_hv is false, it sets it to true and
    then calls the function self.get_hv_data in a thread.

  ** get_hv_data(self, test) **

    Opens a pyserial connection in order to acquire hv data from
    SmartSwitch on the pico. Then it parses the output, ensures that
    the data is proper, and then sets the voltages and currents to
    self.hv_voltage and self.hv_current, respectively.

  ** get_blade_data(self, test) **

    Utilizes an I2C bus connection to acquire assorted data from the
    excelsys blades. The acquired values are voltages, currents, and
    temperatures. It then sets the voltage, current, and temperature
    values to self.voltage, self.current, and self.temperature,
    respectively. It utilizes packet error checking to lessen the
    likelihood of collisions and resulting corruption on the
    I2C bus.

  ** get_lv_data(self, test) **

    Sets self.accessing_lv to true in order to ensure that two threads
    don't attempt to access lv data simultaneously. It then calls
    get_blade_data. Then it utilizes the I2C bus connection to acquire
    the readMon data for the board. It then saves the five volt voltage,
    five volt current, 48 volt conditioned voltage, and 48 volt conditioned
    current to self.five_voltage, self.five_current, self.cond_voltage,
    and self.cond_current, respectively. When done, it sets
    self.accessing_lv to false once again.

  ** save_txt(self) **

    Saves the channel number, self.voltage, self.current, self.temperature,
    self.five_voltage, self.five_current, self.cond_voltage,
    self.cond_current, and the unix timestamp to a line in logfile.txt.

  ** save_error(self, text) **

    Called in try_except blocks throughout the GUI script to
    save error information for the purpose of debugging.

  ||||| ** class Window() ** |||||

    The Window class deals with the pyqt4 gui, utilizing the Session class
    for interactions with the hardware.

  ** tabs(self) **

    Sets up the pyqt4 tabs on the touchscreen. Called tab initialization
    functions are the following:

      -self.controls_setup()
      -self.lv_controls_setup()
      -self.hv_controls_setup()
      -self.blade_plotting_setup()
      -self.board_plotting_setup()
      -self.hv_plotting_setup()
      -self.stability_blade_plotting_setup()
      -self.stability_board_plotting_setup()
      -self.stability_hv_plotting_setup()

    After initializing these tabs, it then adds then to the main
    GUI window utilizing the .addTab() function. The GUI is then
    shown using the .show() function.

  ** stability_blade_plotting_setup(self) **













|| ad5685.c ||

  ** AD5685_setup(AD5685 *self, int csnMCP, uint8_t csnPin, int sclkMCP, uint8_t sclkPin, int sdiMCP, uint8_t sdiPin) **

    Initializes the DAC utilizing digitalWrite and pinMode.
    Additionally, it initializes the self struct.

  ** AD5685_write(AD5685 *self, uint8_t address, uint16_t value) **

    Used to write a value to the pertinent DAC address.

  ** AD5685_setdac(AD5685 *self, uint8_t dacchannel, float value) **

    Utilizes AD5685_write to set the dac for one hv channel to the
    pertinent voltage.

|| ad5685.h ||

  ** typedef struct **

    Defines self struct variables.

  Also sets AD5685_setup, AD5685_write, and AD5685_setdac.

|| python_connect.c ||

** initialization() **

  Sets up wiringpi connections, as well as connections
  with HV.

** rampup_hv(int channel, int value) **

  Sets a single hv channel to a voltage value, doing it
  incrementally to ensure that no damage is inflicted
  upon the circuit.
