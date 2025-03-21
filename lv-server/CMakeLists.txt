cmake_minimum_required(VERSION 3.15...3.25)

project(lv-server
  VERSION
    0.0
  LANGUAGES
    C
)

add_executable(lv-server lv-server.c BinaryHeap.c ConfigurationStore.c HashTable.c Logging.c Messages.c Pico.c PriorityQueue.c Task.c connections.c handler.c pico_routines.c i2c_routines.c spi_routines.c i2cbusses.c dac8164.c MCP23S08.c gpio.c utils.c pico_registry.c)

target_link_libraries(lv-server /usr/lib/gcc/aarch64-linux-gnu/12/../../../aarch64-linux-gnu/libusb-1.0.a pthread udev i2c m)
#target_include_directories(Server PRIVATE /home/mu2e/final_lvhv/Server)
