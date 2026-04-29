#!/bin/bash

sudo echo 'deb [trusted=yes] http://trackerpi10.dhcp.fnal.gov/dev trixie mu2e' >/etc/apt/sources.list.d/mu2e.list

# vadim
sudo apt-get install -y ntpsec
sudo apt-get install -y krb5-user
sudo apt-get install -y krb5-admin-server
sudo apt update

# ejc
sudo apt-get install -y vim screen
sudo apt-get install libmu2e-tracker-messaging mu2e-tracker-lvhv-tools mu2e-tracker-monitoring-tools
sudo apt-get install mu2e-tracker-picotool mu2e-tracker-pico-smartswitch-applications
sudo apt-get install -y ejc-configs

# make life easier
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_serial_cons 0
sudo raspi-config nonint do_serial_hw 0

sudo echo 'dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=17,i2c_gpio_scl=22,i2c_gpio_delay_us=8' >>/boot/firmware/config.txt
sudo echo 'dtoverlay=i2c-gpio,bus=4,i2c_gpio_sda=13,i2c_gpio_scl=19,i2c_gpio_delay_us=8' >>/boot/firmware/config.txt
