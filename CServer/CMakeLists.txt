cmake_minimum_required(VERSION 3.15...3.25)

    project(Server VERSION 1.0 LANGUAGES C)

        add_executable(
            Server Server.c i2cbusses.c dac8164.c MCP23S08.c gpio.c utils.c)

            target_link_libraries(Server / usr / lib / gcc / aarch64 - linux -
                                  gnu / 12 /../../../ aarch64 - linux -
                                  gnu / libusb - 1.0.a pthread udev i2c)
                target_include_directories(Server PRIVATE / home / mu2e /
                                           final_lvhv / Server)
