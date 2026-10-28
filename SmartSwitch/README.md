# SmartSwitch

Firmware for the two SmartSwitch Pico identities. The current CMake project
selects `PICO_BOARD=pico2` and builds both identities from the same sources;
there is no need to edit the Pico number or USB VID in source files.

## Direct build

Prerequisites: CMake, a build tool supported by CMake, an ARM embedded C/C++
toolchain, Python 3, and a Raspberry Pi Pico SDK checkout supporting `pico2`.
The SDK's TinyUSB dependency must be available for `tinyusb_device` and
`tinyusb_board`. Set `PICO_SDK_PATH` to your existing SDK checkout; the old
machine-specific SDK path is not required.

From the LVHVBox checkout root:

[LOCAL BUILD — no device access]

```sh
export PICO_SDK_PATH="/absolute/path/to/pico-sdk"
cmake -S SmartSwitch -B build/SmartSwitch \
  -DPICO_SDK_PATH="$PICO_SDK_PATH" -DPICO_SDK_FETCH_FROM_GIT=OFF
cmake --build build/SmartSwitch --target SmartSwitch_1 SmartSwitch_2 --parallel
```

Replace the SDK placeholder before running. Keep the SDK revision and toolchain
version with your build record. The commands configure and compile locally;
they do not install a service or upload firmware to a connected device.

| Target | Build definition | USB vendor ID | ELF output |
| --- | --- | --- | --- |
| `SmartSwitch_1` | `pico=1` | `0xcaf0` | `build/SmartSwitch/SmartSwitch_1.elf` |
| `SmartSwitch_2` | `pico=2` | `0xcaf1` | `build/SmartSwitch/SmartSwitch_2.elf` |

The Pico SDK also generates additional image formats through
`pico_add_extra_outputs`. Use a new build directory when changing SDK/toolchain
settings. No custom Debian package is needed.

Firmware loading is a separate operation that changes detector hardware state.
Confirm the intended physical Pico and its matching image before any separately
authorized flashing operation. These build instructions do not flash either Pico.
