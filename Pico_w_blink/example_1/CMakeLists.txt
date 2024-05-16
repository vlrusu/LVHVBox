cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

set(PICO_BOARD pico_w)

include(pico_sdk_import.cmake)

project(picow_blink C CXX ASM)

pico_sdk_init()

add_executable(picow_blink picow_blink.c)

pico_enable_stdio_usb(picow_blink 1) # need this for pi to recognize pico as a
                                     # valid usb device. And I assume it's
                                     # needed for printf to work. From the
                                     # docs: Note this library is a developer
                                     # convenience. It is not applicable in all
                                     # cases; for one it takes full control of
                                     # the USB device precluding your use of
                                     # the USB in device or host mode. For this
                                     # reason, this library will automatically
                                     # disengage if you try to using it
                                     # alongside tinyusb_device or
                                     # tinyusb_host. It also takes control of a
                                     # lower level IRQ and sets up a periodic
                                     # background task.

target_link_libraries(picow_blink
        pico_stdlib              # for core functionality
        pico_cyw43_arch_none     # we need Wifi to access the GPIO, but we don't need anything else
        )

# create map/bin/hex file etc.
pico_add_extra_outputs(picow_blink)
