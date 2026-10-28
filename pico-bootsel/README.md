# Pico BOOTSEL helper

`reboot-pico-bootsel` is a native host utility built from `reboot.c`. It addresses
a USB device by bus and address and sends a request to enter BOOTSEL. It is
separate from the SmartSwitch firmware and from the Pico SDK's `picotool`.

## Direct build

Build on the Linux host architecture where the helper will run. Prerequisites:
a native C compiler, Make, `pkg-config`, libusb-1.0 development headers/library,
and an existing Pico SDK checkout. The Makefile uses SDK headers from
`src/rp2_common/pico_stdio_usb/include` and
`src/common/pico_usb_reset_interface_headers/include`, plus `lvhv-server/Pico.h`.
The SDK is used for headers; this helper does not use an ARM firmware compiler.

From the LVHVBox checkout root:

[LOCAL BUILD — no device access]

```sh
export PICO_SDK_PATH="/absolute/path/to/pico-sdk"
pkg-config --cflags --libs libusb-1.0
make -C pico-bootsel PICO_SDK_PATH="$PICO_SDK_PATH" reboot-pico-bootsel
```

Replace the SDK placeholder before running. `pkg-config` should report the
libusb include/link flags; resolve missing dependencies before building.
The output is `pico-bootsel/reboot-pico-bootsel`. Building it neither executes
the helper nor accesses a USB device. No root privileges or custom Debian
package are needed for the build. After changing compiler/SDK options, remove
the old output with `make -C pico-bootsel clean` before rebuilding.

Executing the helper is a separate hardware action: its `--bus` and `--address`
arguments select the target USB device and its request can interrupt firmware
operation and DAQ. Confirm device identity and a suitable maintenance state
before any separately authorized execution. These instructions only build it.
