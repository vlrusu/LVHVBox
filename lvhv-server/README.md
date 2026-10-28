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
