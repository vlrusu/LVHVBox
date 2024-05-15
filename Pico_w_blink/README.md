# LED Blink Our RP2040 pico w -- minimal working examples

Sanity check that we can compile and flash our pico code.

`example_1/`: bare minimal example only testing led flashing for the pico *w*s.
Different from a led blink program for *non-wifi* picos. LED pin is access
differently. tinyusb not tested here.

`example_2/`: combine `example_1` with tinyusb. In addition to flashing, we now
can echo whatever gets passed in.
In one terminal do:
`cat /dev/ttyACM0`
While in a second terminal window do:
`echo "test" > /dev/ttyACM0`.

## Compile and flash instructions:

```
export PICO_SDK_PATH=/home/mu2e/pico/pico-sdk
cd example_1
mkdir build; cd build
cmake ..
make
# <start pico in bootsel mode>
sudo picotool load -F picow_blink.elf
sudo picotool reboot # reboots the pico into application mode 
```
