cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

set(PICO_BOARD pico_w)

include(pico_sdk_import.cmake)

project(picow_blink C CXX ASM)

pico_sdk_init()

add_executable(picow_blink picow_blink.c usb_descriptors.c) #msc_disk.c)

target_include_directories(picow_blink PUBLIC ${CMAKE_CURRENT_LIST_DIR} )

target_link_libraries(picow_blink
        pico_stdlib              # for core functionality
        pico_cyw43_arch_none     # we need Wifi to access the GPIO, but we don't need anything else
        hardware_adc hardware_pio tinyusb_device tinyusb_board
        )

# These are alternatives to communicating via tinyusb
#pico_enable_stdio_usb(picow_blink 0)
#pico_enable_stdio_uart(picow_blink 0)

# create map/bin/hex file etc.
pico_add_extra_outputs(picow_blink)
