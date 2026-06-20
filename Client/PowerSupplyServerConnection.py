# Ed Callaghan
# Abstract out details of communicating with lvhv server
# October 2024

import ctypes
import os.path
import threading
import time
from MessagingConnection import MessagingConnection
from WireAnalogDigitalConversion import WireAnalogDigitalConversion

class SharedValue:
    def __init__(self, value):
        self.value = value
        self.lock = threading.Lock()

    def Get(self):
        self.lock.acquire()
        rv = self.value
        self.lock.release()
        return rv

    def Set(self, value):
        self.lock.acquire()
        self.value = value
        self.lock.release()

class PowerSupplyServerConnection():
    def __init__(self, host, port, header='/etc/mu2e-tracker-lvhv-tools/commands.h', cpath=None):
        self.host = host
        self.port = port
        self.header = header
        self.reestablish()

        self.specials = {}
        with open(header, 'r') as f:
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
                      'current_burst': 'pico',
                     }

        self.specials['COMMAND_set_hv_by_dac'] = 344631823
        self.types['set_hv_by_dac'] = 'hv'
        self.MS_PER_NS = 1e-6

        keys = [str(i) for i in range(12)]
        path = cpath
        if path is None:
            cdir = os.path.dirname(header)
            path = os.path.join(cdir, 'measured-hv-dac-calibration.json')
            if not os.path.exists(path):
                print('warning: cannot find dedicated dac calibration. using a nominal calibration. monitor HV transitions, and be careful.')
                path = os.path.join(cdir, 'nominal-hv-dac-calibration.json')
                keys = ['nominal' for i in range(12)]
        self.wire_analog_digital_conversions = {
            i: WireAnalogDigitalConversion(path, key) \
                    for i,key in enumerate(keys)
        }
        self.minimum_hv_step = 0.01

        self.hv_lock = [SharedValue(False) for i in range(12)]

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

    def GetHVLock(self, channel):
        rv = self.hv_lock[channel].Get()
        return rv

    def SetHVLock(self, channel, value):
        self.hv_lock[channel].Set(value)

    def _set_hv_by_dac(self, channel, dac):
        rvs = self.WriteRead('set_hv_by_dac', channel, dac)
        return rvs

    def _voltage_to_dac(self, channel, voltage):
        conversion = self.wire_analog_digital_conversions[channel]
        rv = conversion.AnalogToDigital(voltage)
        return rv

    def _timed_dac_set(self, channel, dac, pause):
        if self.GetHVLock(channel):
            return None
        self._set_hv_by_dac(channel, dac)
        time.sleep(pause)

    def _take_dac_steps(self, channel, step, steps, pause):
        current = self.QueryLastHVSetting(channel)
        for i in range(steps):
            if self.GetHVLock(channel):
                rv = self.QueryWireVoltage(channel)
                return rv
            target = current + step
            if target < 0:
                break
            self._timed_dac_set(channel, target, pause)
            current = target
        rv = self.QueryWireVoltage(channel)
        return rv

    def _walk_dac_steps(self, channel, target, step, pause, readback):
        sign = +1
        current = self.QueryWireVoltage(channel)
        if target < current:
            step = -step
            sign = -1

        stop = False
        while not stop:
            if self.GetHVLock(channel):
                current = self.QueryWireVoltage(channel)
                return current
            current = self._take_dac_steps(channel, step, readback, pause)
            remaining = target - current
            if sign * remaining < 0:
                stop = True

        return current


    def _take_macro_step(self, channel, target, step, pause, readback):
        if self.GetHVLock(channel):
            rv = self.QueryWireVoltage(channel)
            return rv
        rv = self._walk_dac_steps(channel, target, step, pause, readback)
        return rv

    def _set_wire_voltage(self, channel, voltage):
        volts_per_dac = 0.1
        max_step = 50
        max_readback = 10
        max_pause = 0.01
        med_step = 10
        med_readback = 10
        med_pause = 0.01
        min_step = 2
        min_readback = 1
        min_pause = 0.1

        max_tolerance = max_step * max_readback * volts_per_dac
        med_tolerance = med_step * med_readback * volts_per_dac
        min_tolerance = 1.0

        last_action = None
        target = voltage

        stop = False
        while not stop:
            sign = +1
            current = self.QueryWireVoltage(channel)
            if voltage < current:
                sign = -1

            remaining = abs(voltage - current)
            if self.GetHVLock(channel):
                last_action = 'HV lock set'
                stop = True
            elif remaining < min_tolerance:
                tup = (target, current, remaining, min_tolerance)
                last_action = 'stop @ %.1f (%.1f): %.1f vs %.1f' % tup
                stop = True
            elif remaining < 2*med_tolerance:
                target = voltage
                last_action = 'min_step'
                self._take_macro_step(channel, target,
                                      min_step, min_pause, min_readback)
            elif remaining < 2*max_tolerance:
                last_action = 'med_step'
                target = voltage - sign*med_tolerance
                self._take_macro_step(channel, target,
                                      med_step, med_pause, med_readback)
            else:
                last_action = 'max_step'
                target = voltage - sign*max_tolerance
                self._take_macro_step(channel, target,
                                      max_step, max_pause, max_readback)
        rv = last_action
        return rv

    def SetWireVoltage(self, channel, value):
        tolerance = 1.0
        start = self.QueryWireVoltage(channel)
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
