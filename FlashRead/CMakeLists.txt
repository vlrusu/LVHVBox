cmake_minimum_required(VERSION 3.15...3.25)

project(AcquireSwitch
  VERSION
    1.0
  LANGUAGES
    C
)


add_executable(AcquireSwitch AcquireSwitch.c)


target_link_libraries(AcquireSwitch /usr/lib/gcc/aarch64-linux-gnu/10/../../../aarch64-linux-gnu/libusb-1.0.a pthread udev)