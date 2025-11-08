# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Base Station
#
# See NOTES.md for related documentation
#
from board import D9, D10, SCL, SDA, SPI
import busio
from digitalio import DigitalInOut
from microcontroller import cpu
import os
import time

from adafruit_character_lcd.character_lcd_i2c import Character_LCD_I2C

from common import HMAC_TRUNC, HMAC_KEY, decode_, rfm9x_factory
from sb_hmac import hmac_sha1

# ---------------------------------------------------------------------------
# I2C Character LCD Backlight Option for settings.toml
#
# To disable the LCD backlight, put `LCD_BACKLIGHT = 0` in settings.toml.
#
# The backlight setting combined with the try/except block below make it easy
# to build three base station configurations:
# 1. Full base station setup with backlit LCD
# 2. Darkmode setup with LCD but no backlight (e.g. to use in a bedroom)
# 3. Minimal setup with USB serial output only (e.g. to log with Raspberry Pi)
#
LCD_BACKLIGHT = True
if (backlight := os.getenv("LCD_BACKLIGHT")) is not None:
    LCD_BACKLIGHT = bool(backlight)
# ---------------------------------------------------------------------------

def run():
    # Initialize and run in base station hardware configuration (LoRa RX)
    print("=========================")
    print("=== Base Station Mode ===")
    print("=========================")

    # Reduce CPU frequency so the board runs cooler. The default ESP32-S3
    # default frequency is 240 MHz. To avoid messing up time.monotonic(), don't
    # attempt to set this below 80 MHz.
    if cpu.frequency == 240_000_000:
        cpu.frequency = 80_000_000

    # LoRa radio module
    cs, rst = DigitalInOut(D10), DigitalInOut(D9)
    rfm95 = rfm9x_factory(SPI(), cs, rst)
    rfm95.node = 255                      # receive from all stations (nodes)

    # Character LCD
    i2c = busio.I2C(SCL, SDA, frequency=250_000)  # default bus clock is slow
    cols, rows = 16, 2
    try:
        lcd = Character_LCD_I2C(i2c, cols, rows)
        lcd.clear()
        if LCD_BACKLIGHT:
            lcd.backlight = True
        lcd.message = 'Ready'
    except ValueError:
        # Character_LCD_I2C() raises ValueError if it doesn't find an LCD.
        # If that happens, just ignore it and carry on. You can rely on this
        # to omit the LCD from a base station hardware build if you want.
        lcd = None

    EXPECTED_SIZE = 4 + 6 + HMAC_TRUNC    # size of header + message + MAC
    seq_list = {}
    while True:
        if data := rfm95.receive(with_header=True):  # bytearry: header+packet
            rssi = rfm95.last_rssi                   # signal strength
            snr = rfm95.last_snr                     # signal to noise ratio
            if EXPECTED_SIZE != len(data):           # skip wrong-size packets
                continue
            # Re-assemble message including the node address byte from header.
            # Message format: node address, sequence number, volts, °F.
            msg = data[1:2] + data[4:-HMAC_TRUNC]
            msg_hash = data[-HMAC_TRUNC:]
            node, seq, v, f = decode_(msg)
            # Verify HMAC of message (configure nodes to share the same key)
            if msg_hash != hmac_sha1(HMAC_KEY, msg)[:HMAC_TRUNC]:
                continue
            # Check for monotonic sequence number (per node)
            # CAUTION: After boot, this accepts the first sequence number it
            # sees for each node address (values don't persist across reset)
            check = "DUP"
            prev_seq = seq_list.get(node)
            if (prev_seq is None) or (prev_seq < seq):
                check = "OK"
                seq_list[node] = seq
            # Making it here means packet is in sequence and authenticated.
            # Print decoded packet then update sequence number.
            print('RX: %d, %.1f, %d, %08x, %.2f, %.0f, %s' %
                (rssi, snr, node, seq, v, f, check))
            if lcd:
                lcd.clear()
                lcd.message = '%ddB\n%d: %.2fV %.0fF' % (rssi, node, v, f)
