cmake_minimum_required(VERSION 3.13)
include(pico_sdk_import.cmake)

project(SmartSwitch C CXX ASM)

pico_sdk_init()

add_executable(SmartSwitch
    SmartSwitch.c
)

target_include_directories(SmartSwitch PRIVATE ${CMAKE_CURRENT_LIST_DIR})

pico_enable_stdio_usb(SmartSwitch 1)
pico_enable_stdio_uart(SmartSwitch 0)

pico_add_extra_outputs(SmartSwitch)

# Link TinyUSB library
target_link_libraries(SmartSwitch pico_stdlib tinyusb_device)
