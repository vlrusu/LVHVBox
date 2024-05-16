# LED Blink Our RP2040 pico w -- minimal working example

Sanity check that we can compile and flash our pico code.

tinyusb not tested here.

Different from a led blink program for non-wifi picos. Access the LED pin
differently.

```
export PICO_SDK_PATH=/home/mu2e/pico/pico-sdk
mkdir build; cd build
cmake ..
make
<start pico in bootsel mode>
sudo picotool load -F picow_blink.elf
sudo picotool reboot # reboots the pico into application mode 
```
