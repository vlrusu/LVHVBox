#
# Makefile:
#	wiringPi - A "wiring" library for the Raspberry Pi
#	https://projects.drogon.net/wiring-pi
#
#	Copyright (c) 2012-2015 Gordon Henderson
#################################################################################
# This file is part of wiringPi:
#	Wiring Compatable library for the Raspberry Pi
#
#    wiringPi is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    wiringPi is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with wiringPi.  If not, see <http://www.gnu.org/licenses/>.
#################################################################################

ifneq ($V,1)
Q ?= @
endif

#DEBUG	= -g -O0
DEBUG	= -O3
INCLUDE	= -I/usr/local/include -I ./
CFLAGS	= $(DEBUG) -Wall $(INCLUDE) -Winline -pipe

LDFLAGS	= -L/usr/local/lib
LDLIBS    = dac8164.c -lwiringPi -lwiringPiDev -lpthread -lm -lcrypt -lrt

# Should not alter anything below this line
###############################################################################

SRC	=	dac8164.c test.c rampup.c sethv.c python_connect.c

OBJ	=	$(SRC:.c=.o) $(SRC:.c=.so)

BINS	=	rampup sethv python_connect.so

.DEFAULT_GOAL := all

all:	$(BINS)
	$Q echo "    $(BINS)" | fmt
	$Q echo ""

really-all:	$(BINS)

test:	test.o dac8164.o
	$Q echo [link]
	$Q $(CC) -o $@ test.o dac8164.o  $(LDFLAGS) $(LDLIBS)
rampup:	rampup.o dac8164.o
	$Q echo [link]
	$Q $(CC) -o $@ rampup.o dac8164.o  $(LDFLAGS) $(LDLIBS)

sethv:	sethv.o dac8164.o
	$Q echo [link]
	$Q $(CC) -o $@ sethv.o dac8164.o  $(LDFLAGS) $(LDLIBS)

python_connect.so:	python_connect.o dac8164.o
	$Q echo [link]
	$Q $(CC) -shared -o $@ python_connect.o dac8164.o  $(LDFLAGS) $(LDLIBS)



.c.oa:
	$Q echo [CC] $<
	$Q $(CC) -c $(CFLAGS) $< -o $@

clean:
	$Q echo "[Clean]"
	$Q rm -f $(OBJ) *~ core tags $(BINS) adrac

tags:	$(SRC)
	$Q echo [ctags]
	$Q ctags $(SRC)

depend:
	makedepend -Y $(SRC)

# DO NOT DELETE
