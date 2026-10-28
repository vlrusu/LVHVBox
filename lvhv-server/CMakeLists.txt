cmake_minimum_required(VERSION 3.15...3.25)

project(lvhv-server
  VERSION
    0.0
  LANGUAGES
    C
)

find_package(Python3 COMPONENTS Interpreter REQUIRED)
set(PROTOCOL_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../protocol")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${PROTOCOL_ROOT}/lvhv.json" "${PROTOCOL_ROOT}/generate.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${PROTOCOL_ROOT}/generate.py" --check
  RESULT_VARIABLE PROTOCOL_CHECK_RESULT)
if(NOT PROTOCOL_CHECK_RESULT EQUAL 0)
  message(FATAL_ERROR "Generated protocol definitions are stale; run protocol/generate.py")
endif()
add_custom_target(lvhv_protocol_check
  COMMAND "${Python3_EXECUTABLE}" "${PROTOCOL_ROOT}/generate.py" --check
  COMMENT "Checking shared C/Python protocol definitions"
  VERBATIM)

# Compile the protocol into this release; no site messaging package is needed.
add_library(lvhv_messaging STATIC messaging/Messages.c)
add_dependencies(lvhv_messaging lvhv_protocol_check)
target_include_directories(lvhv_messaging PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/messaging")

add_executable(lvhv-server lvhv-server.c Command.c BinaryHeap.c ConfigurationStore.c HashTable.c Logging.c Pico.c PriorityQueue.c Task.c connections.c handler.c pico_routines.c i2c_routines.c spi_routines.c i2cbusses.c dac8164.c MCP23S08.c gpio.c utils.c pico_registry.c rs485_notify.c)

target_link_libraries(lvhv-server PRIVATE lvhv_messaging /usr/lib/aarch64-linux-gnu/libusb-1.0.a pthread udev i2c m)
