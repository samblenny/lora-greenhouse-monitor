# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny

.PHONY: help bundle sync tty tty-rp2 tty-esp clean mount umount

# Name of top level folder in project bundle zip file should match repo name
PROJECT_DIR = $(shell basename `git rev-parse --show-toplevel`)

# This is for use by .github/workflows/buildbundle.yml GitHub Actions workflow
# To use this on Debian, you might need to apt install curl and zip.
bundle:
	@mkdir -p build
	python3 bundle_builder.py

# Sync current code and libraries to one or two CIRCUITPY drives on macOS.
# This handles up to two boards plugged in at once. The first one should mount
# as '/Volumes/CIRCUITPY' and the second as '/Volumes/CIRCUTPY 1'.
sync: bundle
	@if [ -d /Volumes/CIRCUITPY ]; then \
		xattr -cr build; \
		rsync -rcvO 'build/${PROJECT_DIR}/CircuitPython 10.x/' /Volumes/CIRCUITPY; \
		sync; fi
	@if [ -d '/Volumes/CIRCUITPY 1' ]; then \
		xattr -cr build; \
		rsync -rcvO 'build/${PROJECT_DIR}/CircuitPython 10.x/' '/Volumes/CIRCUITPY 1'; \
		sync; fi

# Serial terminal: 115200 baud, no flow control (-fn)
# This should work on macOS or Debian, assuming that there is only one serial
# device plugged in that will match the device file glob. On Debian, your login
# account must be in the dialout group or screen won't open the serial port.
tty:
	@if [ -e /dev/ttyACM0 ]; then \
		screen -h 9999 -fn /dev/ttyACM0 115200; fi
	@if [ -e /dev/tty.usbmodem* ]; then \
		screen -h 9999 -fn /dev/tty.usbmodem* 115200; fi

# Open serial monitor on macOS with a device file glob designed to match the
# serial port for an RP2350 Feather. This assumes there may be multiple
# serial devices but that they will have different device name lengths.
tty-rp2:
	@if [ -e /dev/tty.usbmodem???? ]; then \
		screen -h 9999 -fn /dev/tty.usbmodem???? 115200; fi

# Open serial monitor on macOS with a device file glob designed to match the
# serial port for an ESP32-S3 Feather. This assumes there may be multiple
# serial devices but that they will have different device name lengths.
tty-esp:
	@if [ -e /dev/tty.usbmodem????????????? ]; then \
		screen -h 9999 -fn /dev/tty.usbmodem????????????? 115200; fi

clean:
	rm -rf build

# Mount CIRCUITPY from Debian command line
# You might need to apt install pmount before using this.
mount:
	@if [ ! -d /media/CIRCUITPY ] ; then \
		pmount `readlink -f /dev/disk/by-label/CIRCUITPY` CIRCUITPY; else \
		echo "/media/CIRCUITPY was already mounted"; fi

# Unmount CIRCUITPY from Debian command line.
# You might need to apt install pmount before using this.
umount:
	@if [ -d /media/CIRCUITPY ] ; then pumount CIRCUITPY; else \
		echo "/media/CIRCUITPY wasn't mounted"; fi
