cmake_minimum_required(VERSION 3.15...3.25)

project(ramphv
  VERSION
    1.0
  LANGUAGES
    C
)

add_executable(ramphv ramphv.c dac8164.c dac8164.h)
target_link_libraries(ramphv /usr/lib/gcc/aarch64-linux-gnu/10/../../../aarch64-linux-gnu/libusb-1.0.a pthread udev wiringPi)
target_include_directories(ramphv PRIVATE /home/mu2e/final_lvhv/Control)

add_executable(sethv sethv.c dac8164.c dac8164.h)
target_link_libraries(sethv /usr/lib/gcc/aarch64-linux-gnu/10/../../../aarch64-linux-gnu/libusb-1.0.a pthread udev wiringPi)
target_include_directories(sethv PRIVATE /home/mu2e/final_lvhv/Control)

