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

The server accepts `-p PORT`, `-b BACKLOG` and `-l LOG_PATH`. The unused legacy
configuration store, root `config.txt` and server `-c` option have been removed:
loaded values were never applied to hardware settings. Supplying `-c` now fails
during argument parsing before hardware initialization. Existing pin/channel
assignments and control behavior remain in their source implementations.
Python client configuration and the other services' INI/environment settings
are separate and remain supported.

HV ramping runs in the Python `SetWireVoltage` client used by the control-center
GUI and `Client/ramp-hv.py`. The server accepts individual `set_hv_by_dac` writes
and `query_hv_dac_cache` reads. The legacy server-side ramp and CLI commands
`ramp_hv` / `down_hv` have been removed; use the Python ramp workflow for raising
or lowering HV. Retired command IDs `344631822` and `1236373670` remain reserved
and must not be reused. Old requests receive the server's unknown-command
error reply and perform no hardware operation. Other command IDs are unchanged.

## LV power-on modes

[AFFECTS LV/HV OR DETECTOR HARDWARE] `powerOn 6` resets the station once,
enables the shared LV supply, then enables outputs0–5 with 50ms between
successful output writes (five waits, 250ms total). A successful sequence sends
one RS485 discovery event; the existing RS485 worker waits its default5s boot
delay before scanning. `powerOn 7` retains the previous all-channel behavior:
the same reset and shared enable, followed by all six writes without deliberate
spacing, then one discovery event on success. Writes are sequential bus
operations; "simultaneous" does not mean an electrically atomic transition.
Individual outputs0–5 retain their existing behavior without discovery.

`Client.py` now sends channel6 for bare `powerOn`, `powerOn all` and
`powerOn -1`, instead of issuing six individual commands. Explicit `powerOn 7`
selects startup without spacing. Channel7 is valid only for `powerOn`;
`powerOff 7` and LV measurement selectors7 are rejected. Old server binaries
reject the new selector, so the server must be rebuilt/deployed to support it.
No wire opcode or shared protocol layout changes are required.

The default50ms spacing preserves the previous CLI pacing; it is not a measured
inrush limit. `lv_power_policy.h` permits a build-time override using
`-DLV_POWER_ON_STAGGER_MS=<nonnegative milliseconds>`. Larger delays extend the
blocking I2C command and must be assessed against client timeouts and protection
response requirements.

Staggered startup stops on reset, shared-enable, output-write or wait failure,
returns failure and skips the success/discovery event. The output index is logged
for a failed output write. Already-enabled outputs stay enabled; the command
does not automatically roll them back or claim verified output voltage.
Channel7 preserves the previous best-effort write behavior on errors, returning
failure after attempting all six output writes, without a success event.
Shutdown remains immediate, without startup waits or reset pulses.

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

Python syntax validation runs offline instead of on each PSU during deployment.
Before pushing, run this dependency-free check from the repository root:

```sh
python3 -m unittest discover -s Client/tests -p test_python_syntax.py -v
```

The `Python syntax` GitHub Actions workflow runs the same test using Python3.11
on pushes and pull requests. It parses Git-tracked Python files, including client
utilities and tests, without importing or executing application code or creating
bytecode files. Local untracked logs/data are excluded. Deployment retains its
build, import-path and service-state checks.

Offline C/Python compatibility tests compile only the messaging implementation
and exercise typed requests and error replies through local socket pairs:

```sh
python3 -m unittest discover -s lvhv-server/tests -v
```

[AFFECTS LV/HV OR DETECTOR HARDWARE] Starting the actual server initializes
hardware and disables global LV. Building it and running the protocol-only tests
do not start the server or access detector hardware.

The four Python protection monitors share [`../config/alarm-policy.json`](../config/alarm-policy.json).
See [`../config/README.md`](../config/README.md) for editing and validation.
The LVHV C server's power-on spacing is a separate build-time hardware-control
setting; this policy does not change LV enable modes, HV DAC limits or firmware trip settings.
