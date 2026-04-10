# Ed Callaghan
# Abstract out details of communicating with lvhv server
# October 2024

import ctypes
import os.path
import time
from MessagingConnection import MessagingConnection
from WireAnalogDigitalConversion import WireAnalogDigitalConversion

class PowerSupplyServerConnection():
    def __init__(self, host, port, cpath='/etc/mu2e-tracker-lvhv-tools/commands.h'):
        self.host = host
        self.port = port
        self.reestablish()

        self.specials = {}
        with open(cpath, 'r') as f:
            for line in f:
                line = line.strip()
                tokens = line.split()
                key = tokens[1]
                value = int(tokens[2])
                self.specials[key] = value
        self.types = {
                      'powerOn'      : 'lv',
                      'powerOff'     : 'lv',
                      'readMonV48'   : 'lv',
                      'readMonI48'   : 'lv',
                      'readMonV6'    : 'lv',
                      'readMonI6'    : 'lv',
                      'get_vhv'      : 'pico',
                      'get_ihv'      : 'pico',
                      'get_vhvs'     : 'pico',
                      'get_ihvs'     : 'pico',
                      'trip_status'  : 'pico',
                      'trip_currents': 'pico',
                      'reset_trip'   : 'pico',
                      'set_trip'     : 'pico',
                      'pcb_temp'     : 'pico',
                      'pico_current' : 'pico',
                      'query_hv_dac_cache': 'hv',
                     }

        self.specials['COMMAND_set_hv_by_dac'] = 344631823
        self.types['set_hv_by_dac'] = 'hv'
        self.MS_PER_NS = 1e-6

        cdir = os.path.dirname(cpath)
        path = os.path.join(cdir, 'measured-hv-dac-calibration.json')
        keys = [str(i) for i in range(12)]
        if not os.path.exists(path):
            print('warning: cannot find dedicated dac calibration. using a nominal calibration. monitor HV transitions, and be careful.')
            path = os.path.join(cdir, 'nominal-hv-dac-calibration.json')
            keys = ['nominal' for i in range(12)]
        self.wire_analog_digital_conversions = {
            i: WireAnalogDigitalConversion(path, key) \
                    for i,key in enumerate(keys)
        }
        self.minimum_hv_step = 0.01

    def reestablish(self):
        self.connection = MessagingConnection(self.host, self.port)

    def close(self):
        self.connection.close()

    def WriteRead(self, command, channel=None, numeric=None):
        ckey = 'COMMAND_%s' % command
        tkey = 'TYPE_%s' % self.types[command]
        if channel is None:
            channel = 0
        if numeric is None:
            numeric = 0.0

        cmd = ctypes.c_uint(self.specials[ckey])
        typ = ctypes.c_uint(self.specials[tkey])

        chn = ctypes.c_char(channel)
        num = ctypes.c_float(numeric)
        self.connection.send_message(cmd, typ, chn, num)
        rvs = self.connection.recv_message()
        return rvs

    def DisableLowVoltage(self, channel=6):
        # channel 6 is a flag to disable all channels and disable 6V driver
        rvs = self.WriteRead('powerOff', channel)
        return rvs

    def EnableLowVoltage(self, channel):
        rvs = self.WriteRead('powerOn', channel)
        return rvs

    def QueryPowerVoltage(self, channel):
        rvs = self.WriteRead('readMonV48', channel)
        rv = rvs[0][0]
        return rv

    def QueryPowerVoltages(self):
        rvs = self.WriteRead('readMonV48', 6)
        rv = rvs[0]
        return rv

    def QueryPowerCurrent(self, channel):
        rvs = self.WriteRead('readMonI48', channel)
        rv = rvs[0][0]
        return rv

    def QueryPowerCurrents(self):
        rvs = self.WriteRead('readMonI48', 6)
        rv = rvs[0]
        return rv

    def QuerySwitchingVoltage(self, channel):
        rvs = self.WriteRead('readMonV6', channel)
        rv = rvs[0][0]
        return rv

    def QuerySwitchingVoltages(self):
        rvs = self.WriteRead('readMonV6', 6)
        rv = rvs[0]
        return rv

    def QuerySwitchingCurrent(self, channel):
        rvs = self.WriteRead('readMonI6', channel)
        rv = rvs[0][0]
        return rv

    def QuerySwitchingCurrents(self):
        rvs = self.WriteRead('readMonI6', 6)
        rv = rvs[0]
        return rv

    def QueryWireVoltage(self, channel):
        rvs = self.WriteRead('get_vhv', channel)
        rv = rvs[0][0]
        return rv

    def QueryWireCurrent(self, channel):
        rvs = self.WriteRead('get_ihv', channel)
        rv = rvs[0][0]
        return rv

    def BlockQueryWireVoltages(self, channel):
        rvs = self.WriteRead('get_vhvs', channel)
        rv = rvs[0]
        return rv

    def BlockQueryWireCurrents(self, channel):
        rvs = self.WriteRead('get_ihvs', channel)
        rv = rvs[0]
        return rv

    def QueryWireVoltages(self):
        rv = []
        rv += self.BlockQueryWireVoltages(0)
        rv += self.BlockQueryWireVoltages(6)
        return rv

    def QueryWireCurrents(self):
        rv = []
        rv += self.BlockQueryWireCurrents(0)
        rv += self.BlockQueryWireCurrents(6)
        return rv

    def QueryPcbTemp(self):
        rvs = self.WriteRead('pcb_temp')
        rv = rvs[0][0]
        return rv

    def QueryPicoCurrent(self):
        rvs = self.WriteRead('pico_current')
        rv = rvs[0][0]
        return rv

    def _set_hv_by_dac(self, channel, dac):
        rvs = self.WriteRead('set_hv_by_dac', channel, dac)
        return rvs

    def _voltage_to_dac(self, channel, voltage):
        conversion = self.wire_analog_digital_conversions[channel]
        rv = conversion.AnalogToDigital(voltage)
        return rv

    def _timed_hv_set(self, channel, value, pause):
        dac = self._voltage_to_dac(channel, value)
        self._set_hv_by_dac(channel, dac)

        time.sleep(pause)
        rv = self.QueryWireVoltage(channel)
        return rv

    def _transition_wire_voltage_linear(self, channel, target,
                                        tolerance, speed, timestep):
        # speed in V / ms, step size, timestep in ms
        current = self.QueryWireVoltage(channel)
        sign = 1 if (current < target) else -1
        step = speed * sign * timestep
        remaining = target - current

        finetunethreshold = 50
        finetunespeed = 2

        tried = 0
        stop = False
        while tolerance < abs(remaining) and 0 < sign*remaining and not stop:

            if (abs(remaining) < finetunethreshold):
                # as I decrease the speed, the HV values are closer and closer, settling time can influence the reading. So I need to increase the timestep
                timestep = 3
                step = finetunespeed * sign * timestep

            stage = current + step
            updated = self._timed_hv_set(channel, stage, timestep)
            print(current,updated, timestep, step,timestep)
            change = updated - current
            current = updated

            tried += 1
            if sign*change < 0 and tolerance < abs(change):
                print("Stopped on tolerance or overshoot",sign*change,change, tolerance, channel)
                stop = True
            elif 9 < tried and abs(change) < self.minimum_hv_step:
                stop = True
            else:
                remaining = target - current
                if (tolerance < abs(change)):
                    tried = 0

        return current

    def _ramp_wire_voltage_bilinear(self, channel, target,
                                    tolerance, transition,
                                    speed_lo, timestep_lo,
                                    speed_hi, timestep_hi):
        if transition < target:
            rv = self._transition_wire_voltage_linear(channel, transition,
                                                      tolerance,
                                                      speed_lo, timestep_lo)
        rv = self._transition_wire_voltage_linear(channel, target,
                                                  tolerance,
                                                  speed_hi, timestep_hi)
        return rv

    def _ramp_wire_voltage_trilinear(self, channel, target, tolerance,
                                     transition_md, transition_hi,
                                     speed_lo, timestep_lo,
                                     speed_md, timestep_md,
                                     speed_hi, timestep_hi):
        rv = self.QueryWireVoltage(channel)
        if rv < transition_md and transition_md < target:
            rv = self._transition_wire_voltage_linear(channel, transition_md,
                                                      tolerance,
                                                      speed_lo, timestep_lo)
            '''
            if tolerance < abs(rv - transition_md):
                return rv
            '''
        if rv < transition_hi and transition_hi < target:
            rv = self._transition_wire_voltage_linear(channel, transition_hi,
                                                      tolerance,
                                                      speed_md, timestep_md)
            '''
            if tolerance < abs(rv - transition_hi):
                return rv
            '''
        rv = self._transition_wire_voltage_linear(channel, target,
                                                  tolerance,
                                                  speed_hi, timestep_hi)
        return rv

    def _set_wire_voltage(self, channel, value):
        tolerance = 1.0
        transition_onset = 20.0
        transition_bulk = 40.0
        speed_early = 10.0
        timestep_early = 0.5
        speed_bulk = 50.0
        timestep_bulk = 0.5
        transition_fine = value - 1.0*speed_bulk*timestep_bulk
        speed_fine = 5.0
        timestep_fine = 0.5

        current = self.QueryWireVoltage(channel)
        # if ramping up, first get out of baseline-region
        if current < value and current < transition_onset:
                rv = self._timed_hv_set(channel, transition_onset,
                                        timestep_early)
        # if ramping down, first drop to below the setpoint
        else:
            rv = self._transition_wire_voltage_linear(channel, value,
                                                      tolerance,
                                                      speed_bulk, timestep_bulk)
        # ramp up to setpoint
        rv = self._ramp_wire_voltage_trilinear(channel, value, tolerance,
                                              transition_bulk, transition_fine,
                                              speed_early, timestep_early,
                                              speed_bulk, timestep_bulk,
                                              speed_fine, timestep_fine)

        return rv

    def SetWireVoltage(self, channel, value):
        tolerance = 1.0
        start = self.QueryWireVoltage(channel)
        rv = self._set_wire_voltage(channel, value)
        # if the transition overshot the target, then retune
        if tolerance < abs(rv - value):
            rv = self._set_wire_voltage(channel, value)
        return rv

    def _step_hv_dac(self, channel, target, step, interval):
        target = int(target)
        current = self.QueryLastHVSetting(channel)
        if current < target:
            sign = +1
        elif target < current:
            sign = -1
        else:
            return current

        remaining = target - current
        while 0 < sign*remaining:
            dac = current + sign*step
            self._set_hv_by_dac(channel, dac)
            time.sleep(interval)
            current = self.QueryLastHVSetting(channel)
            remaining = target - current

        return current

    def QueryTripStatus(self, channel):
        rvs = self.WriteRead('trip_status', channel)
        rv = rvs[0][0]
        return rv

    def QueryTripCurrents(self, channel):
        rvs = self.WriteRead('trip_currents', channel)
        rv = rvs[0][0]
        return rv

    def ResetTripStatus(self, channel):
        rvs = self.WriteRead('reset_trip', channel)
        rv = rvs[0][0]
        return rv

    def SetTripThreshold(self, channel, value):
        rvs = self.WriteRead('set_trip', channel, value)
        rv = rvs[0][0]
        return rv

    def QueryLastHVSetting(self, channel):
        rvs = self.WriteRead('query_hv_dac_cache', channel)
        rv = rvs[0][0]
        return rv
