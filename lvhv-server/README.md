# LVHV server built from one source tree

The server builds directly from LVHVBox. It includes the messaging C protocol
implementation in `messaging/`, links it statically into the server, and does
not require the site `libmu2e-tracker-messaging` Debian package or shared library.
See `messaging/README.md` for upstream attribution and source revision.
The fleet deployment installs the built binary, matching Python clients and
units directly, without building or installing Mu2e Debian packages.

Standard OS dependencies remain: CMake/C build tools, USB/udev/I2C development
libraries and the Python dependencies for the other services. The Ansible
requirements step provisions those from the OS package sources. PSU13's BME680
driver is also bundled under `i2c-sensor-server/bme680`; database and notification
credentials remain site configuration and are never bundled.

HV ramping runs in the Python `SetWireVoltage` client used by the control-center
GUI and `Client/ramp-hv.py`. The server accepts individual `set_hv_by_dac` writes
and `query_hv_dac_cache` reads. The legacy server-side ramp and CLI commands
`ramp_hv` / `down_hv` have been removed; use the Python ramp workflow for raising
or lowering HV. Retired command IDs `344631822` and `1236373670` remain reserved
and must not be reused. Old requests receive the server's unknown-command
error reply and perform no hardware operation. Other command IDs are unchanged.

LV control attempts every requested shutdown write and returns failure if any
GPIO/SPI write fails. Raw HV DAC writes return failure on a transfer error and
update the DAC cache only after a successful transfer; Python ramping stops on a
failed acknowledgement without retrying. The cache is the last acknowledged
setting, not measured voltage. A failed transfer can leave the physical setting
unknown; software must not report that the outputs were verified off.

[READ-ONLY] Build on the supported ARM64 Linux target without executing it:

```sh
cmake -S lvhv-server -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 2
readelf -d build/lvhv-server
```

The dynamic dependency list must not contain `libmu2e-tracker-messaging.so`.
The deployment role checks this before stopping any service. Existing system
messaging packages are left untouched and are not used by the new server build.

Offline C/Python compatibility tests compile only the messaging implementation
and exercise typed requests and error replies through local socket pairs:

```sh
python3 -m unittest discover -s lvhv-server/tests -v
```

[AFFECTS LV/HV OR DETECTOR HARDWARE] Starting the actual server initializes
hardware and disables global LV. Building it and running the protocol-only tests
do not start the server or access detector hardware.
