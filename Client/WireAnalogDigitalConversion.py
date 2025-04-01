# Ed Callaghan
# Conversion between analog high voltage readbacks and programmed dac values
# March 2025

import json
from scipy.interpolate import interp1d

class WireAnalogDigitalConversion:
    def __init__(self, path, key):
        with open(path, 'r') as f:
            j = json.load(f)
        j = j[key]

        xx = []
        yy = []
        for _,_j in sorted(j.items(), key=lambda p: int(p[0])):
            xx.append(_j['voltage']['value'])
            yy.append(_j['dac'])

        self.interp = interp1d(xx, yy)

    def AnalogToDigital(self, value):
        try:
            rv = self.interp(value)
            rv = int(rv)
        except ValueError as e:
            if value < self.interp.x[0]:
                rv = 0
            elif self.interp.x[-1] < value:
                rv = self.interp(self.interp.x[-1])
            else:
                raise e
        return rv

    '''
    def __init__(self):
        self.dac_per_volt = 16383.0 / 1900.0

    def AnalogToDigital(self, value):
        rv = self.dac_per_volt * value
        return rv
    '''
