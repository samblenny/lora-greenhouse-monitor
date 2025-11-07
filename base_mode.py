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
import time

from adafruit_character_lcd.character_lcd_i2c import Character_LCD_I2C

from common import HMAC_TRUNC, HMAC_KEY, decode_, rfm9x_factory
from sb_hmac import hmac_sha1


def run():
    # Initialize and run in base station hardware configuration (LoRa RX)

    # LoRa radio module
    cs, rst = DigitalInOut(D10), DigitalInOut(D9)
    rfm95 = rfm9x_factory(SPI(), cs, rst)
    rfm95.node = 255                      # receive from all stations (nodes)

    # Character LCD
    i2c = busio.I2C(SCL, SDA, frequency=250_000)  # default bus clock is slow
    cols, rows = 16, 2
    lcd = Character_LCD_I2C(i2c, cols, rows)
    lcd.clear()
    lcd.backlight = True
    lcd.message = 'Ready'

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
            check = "SEQ_ERR"
            prev_seq = seq_list.get(node)
            if (prev_seq is None) or (prev_seq < seq):
                check = "SEQ_OK"
                seq_list[node] = seq
            # Making it here means packet is in sequence and authenticated.
            # Print decoded packet then update sequence number.
            print('RX: rssi=%d, snr=%.1f, %d, %08x, %.2f, %.0f, %s' %
                (rssi, snr, node, seq, v, f, check))
            lcd.clear()
            lcd.message = 'rssi %d snr %.1f\n%d: %.2fV %.0fF' % (
                rssi, snr, node, v, f)
