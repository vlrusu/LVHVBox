# Bundled BME680 driver

From [Pimoroni bme680-python](https://github.com/pimoroni/bme680-python), commit
`30fcb34efc2d19f60a63ece656b9059adb373150`, retrieved October 27, 2026.
`__init__.py` and `constants.py` are unchanged upstream files. The upstream MIT
license is retained as `LICENSE`. The driver still requires the standard smbus2
Python module and access to the configured I²C bus/device.

Running the collector from source finds this sibling package by default.
Fleet deployment copies it with the collector release. Explicit
`I2C_SENSOR_SERVER_SENSOR_REPO` site settings can select another driver path.
