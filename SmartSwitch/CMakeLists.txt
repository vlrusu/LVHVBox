# Generated Cmake Pico project file

cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialise pico_sdk from installed location
# (note this can come from environment, CMake cache etc)

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)

project(SmartSwitch C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()


# Add executable. Default name is the project name, version 0.1

add_executable(SmartSwitch SmartSwitch.c usb_descriptors.c msc_disk.c)




pico_set_program_name(SmartSwitch "SmartSwitch")
pico_set_program_version(SmartSwitch "0.1")

#pico_enable_stdio_uart(SmartSwitch 0)
#pico_enable_stdio_usb(SmartSwitch 0)

target_include_directories(SmartSwitch PUBLIC
    ${CMAKE_CURRENT_LIST_DIR}
)


# Add the standard library to the build
target_link_libraries(SmartSwitch pico_stdlib hardware_adc hardware_pio hardware_irq pico_multicore tinyusb_device tinyusb_board)

pico_add_extra_outputs(SmartSwitch)
