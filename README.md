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

dac8164.c:
  ** DAC8164_setup(self, MCP, sync, sclk, sdi, enable_pin, ldac_pin) **

    Initialize connection with DAC8164.

  ** DAC8164_write(self, data) **

    Sends data via previously initialized connection to DAC8164.

  ** DAC8164_setReference(self, reference) **

  ** DAC8164_writeChannel(self, channel, value) **

    Writes a power value to a DAC8164 channel.

dac8164.h:
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

    Defines tab 7 in the GUI.

  ** stability_board_plotting_setup(self) **

    Defines tab 8 in the GUI.

  ** stability_hv_plotting_setup(self) **

    Defines tab 9 in the GUI.

  ** blade_plotting_setup(self) **

    Defines tab 4 in the GUI.

  ** board_plotting_setup(self) **

    Defines tab 5 in the GUI.

  ** hv_plotting_setup(self) **

    Defines tab 6 in the GUI.

  ** lv_controls setup(self) **

    Defines tab 2 in the GUI.

  ** hv_controls_setup(self) **

    Defines tab 3 in the GUI.

  ** controls_setup(self) **

    Defines tab 1 in the GUI.

  ** actuate_lv_power(self, number) **

    Called when any of the LV power actuation buttons are toggled.
    Changes the color of the button and calls either self.power_on
    or self.power_off, depending on the button status.

  ** actuate_hv_power(self, number) **

    Called when one of the hv power buttons is pressed.
    Appends the button to self.rampup_list, in order to utilize
    threading. This ensures that the GUI doesn't lock up.

  ** update_blade_table(self) **

    Called to update the blade table - rather self explanatory.

  ** update_board_table(self) **

    Called to update the board table.

  ** update_hv_bars(self) **

    Called to update the hv bars above the buttons. This alerts
    users to hv rampup progress - where hv channels are in the
    queue.

  ** update_hv_table(self) **

    Called to update the hv table.

  ** get_blade_channel(self) **

    When given the text value of a blade channel, this function
    returns the integer value of that channel.

  ** get_board_channel(self) **

    When given the text value of a board channel, this function
    returns the integer value of that channel.

  ** get_hv_channel(self) **

    When given the text value of an hv channel, this function
    returns the integer value of that channel.

  ** get_stability_blade_channel(self) **

    When given the text value of a blade stability channel, this
    function returns the integer value of that channel.

  ** get_stability_board_channel(self) **

    When given the text value of a stability board channel, this
    function returns the integer value of that channel.

  ** get_stability_hv_channel(self) **

    When given the text value of a stability hv channel, this
    function returns the integer value of that channel.

  ** change_stability_blade_plot(self) **

    When called, this function changes the type of data displayed
    on the stability blade plot. The labels and ydata lists are
    updated. The plot is then redrawn.

  ** change_stability_hv_plot(self) **

    When called, this function changes the type of data displayed
    on the stability hv plot. The labels and ydata lists are
    updated. The plot is then redrawn.

  ** change_stability_board_plot(self) **

    When called, this function changes the type of data displayed
    on the stability hv plot. The labels and ydata lists are
    updated. The plot is then redrawn.

  ** change_blade_plot(self) **

    When called, this function changes the type of data displayed
    on the blade plot. The labels and ydata lists are updated.
    The plot is then redrawn.

  ** change_hv_plot(self) **

    When called, this function changes the type of data displayed
    on the hv plot. The labels and ydata lists are updated.
    The plot is then redrawn.

  ** change_board_plot(self) **

    When called, this function changes the type of data displayed
    on the board plot. The labels and ydata lists are updated.
    The plot is then redrawn.

  ** update_stability_blade_plot(self) **

    When called, this function updates the pertinent ydata and then
    redraws the stability blade plot.

  ** update_stability_board_plot(self) **

    When called, this function updates the pertinent ydata and then
    redraws the stability board plot.

  ** update_stability_hv_plot(self) **

    When called, this function updates the pertinent ydata and then
    redraws the stability hv plot.

  ** update_blade_plot(self) **

    When called, this function updates the pertinent ydata and then
    redraws the blade plot.

  ** update_board_plot(self) **

    When called, this function updates the pertinent ydata and then
    redraws the board plot.

  ** update_hv_plot(self) **

    When called, this function updates the pertinent ydata and then
    redraws the hv plot.

  ** call_lv_data(self) **

    Checks to see if the lv data is currently in the process of being
    acquired by another thread. If not, it then starts a thread to
    call self.get_lv_data. This prevents collisions on the I2C bus.

  ** primary_update(self) **

    Calls self.update_board_table(), self.update_blade_table(),
    self.update_blade_plot(), and self.update_board_plot().

  ** stability_save(self) **

    Calls self.update_stability_blade_plot(), self.update_stability_board_plot(),
    self.update_stability_hv_plot(), and self.save_txt().

  ** hv_update(self) **

    Calls self.update_hv_table() and self.update_hv_bars(). If
    self.is_ramping is false and the self.rampup_list isn't empty,
    it then starts a thread to call self.hv_rampup_on_off.

  ** initialize_data(self) **

    Initializes assorted variables, lists, et cetera... used in the window
    class.

  ** run(self) **

    Called to start up the GUI. Initializes timers and their periodically
    called functions, et cetera...




|| dac8164.c ||

  ** DAC8164_setup(DAC8164 *self, int MCP, uint8_t sync, int sclk, uint8_t sdi, int enable_pin, uint8_t ladac_pin) **

    Initializes the DAC utilizing digitalWrite and pinMode.
    Additionally, it initializes the self struct.

  ** DAC8164_write(DAC8164 *self, uint32_t data) **

    Used to write a value to the pertinent DAC address.

  ** DAC8164_setReference(DAC8164 *self, uint16_t reference) **

  ** DAC8164_writeChannel(DAC8164 *self, uint8_t channel, uint16_t value) **

|| DAC8164.h ||

  ** typedef struct **

    Defines self struct variables.

  Also sets DAC8164_write, DAC8164_setup, DAC8164_setReference,
  DAC8164_writeChannel, and DAC8164_setChannelPower.

|| python_connect.c ||

** initialization() **

  Sets up wiringpi connections, as well as connections
  with HV.

** rampup_hv(int channel, int value) **

  Sets a single hv channel to a voltage value, doing it
  incrementally to ensure that no damage is inflicted
  upon the circuit.
