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

# Compilation and follow-on flash command
function(compile_and_flash target pico USB_VID)
  add_executable(${target} SmartSwitch.c usb_descriptors.c msc_disk.c)
  target_compile_definitions(${target} PRIVATE pico=${pico})
  target_compile_definitions(${target} PRIVATE USB_VID=${USB_VID})
  target_include_directories(${target} PUBLIC ${CMAKE_CURRENT_LIST_DIR})
  target_link_libraries(${target}
                        pico_stdlib
                        hardware_adc
                        hardware_pio
                        pico_multicore
                        tinyusb_device
                        tinyusb_board)
  pico_add_extra_outputs(${target})
  pico_set_program_name(${target} "SmartSwitch")
  pico_set_program_version(${target} "0.1")
  #pico_enable_stdio_uart(${target} 0)
  #pico_enable_stdio_usb(${target} 0)
  add_custom_target(flash-pico-${pico}
                    DEPENDS ${target}
                    COMMAND echo picotool load ${target}.elf -f \${REST})
endfunction()

# Add executables, and generate commands to load onto picos
compile_and_flash(SmartSwitch_1 1 0xcaf0)
compile_and_flash(SmartSwitch_2 2 0xcaf1)
