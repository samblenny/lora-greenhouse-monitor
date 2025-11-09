# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Base Station
#
# See NOTES.md for related documentation
#
from board import D9, D10, SCL, SDA, SPI
import busio
from collections import namedtuple
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

Report = namedtuple("Report", ["timestamp", "volts", "degree_f"])

Node = namedtuple("Node", ["reports", "min_f", "max_f"])

class SensorReports:
    # This tracks reports from multiple sensors to format them for a 2x16 LCD
    def __init__(self):
        self.ready_timestamp = time.monotonic()
        self.lora_nodes = {}

    def new_report(self, lora_node, volts, degree_f):
        now = time.monotonic()
        new_report = Report(now, volts, degree_f)
        nodes = self.lora_nodes
        if lora_node not in nodes:
            # First report for this node, so initialize a new reports list
            nodes[lora_node] = Node([new_report], degree_f, degree_f)
        else:
            # Not first report, so add new report at end of existing list
            reports = nodes[lora_node].reports
            reports.append(new_report)
            # Prune reports older than 1 day from front of list
            s_per_day = 86400
            for _ in range(len(reports)-1):
                (t, v, f) = reports[0]
                if t + s_per_day < now:
                    reports.pop(0)
                else:
                    break
            # Re-calculate 24 hour min/max temperature stats
            min_f = max_f = degree_f
            for (t, v, f) in reports:
                if f < min_f:
                    min_f = f
                if f > max_f:
                    max_f = f
            # Save the updated reports list with stats
            nodes[lora_node] = Node(reports, min_f, max_f)

    def freshness_tag(self, seconds):
        minutes = round(max(0, seconds)) // 60
        hours = minutes // 3600   # 60*60=3600 seconds/hour
        days = minutes // 86400   # 60*60*24=86400 seconds/day
        if days > 0:
            return '%dd' % days
        elif hours > 0:
            return '%dh' % hours
        else:
            return '%dm' % minutes

    def __str__(self):
        # Format a two line status string for display on the 2x16 LCD
        now = time.monotonic()
        if len(self.lora_nodes) == 0:
            tag = self.freshness_tag(now - self.ready_timestamp)
            return 'Ready %s' % tag
        # Display current report and min/max temperature stats for the lowest
        # numbered lora node (because more won't fit on the 2x16 LCD)
        node_key = sorted(self.lora_nodes)[0]
        n = self.lora_nodes[node_key]
        r = n.reports[-1]  # newest report is at end of list
        tag = self.freshness_tag(now - r.timestamp)
        # Format 2-line message for LCD
        return '%d %.1fV %s %.0fF\n %.0fF %.0fF' % (
            node_key, r.volts, tag, r.degree_f, n.min_f, n.max_f)


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
        lcd.message = 'Ready 0m'
        reports = SensorReports()
    except ValueError:
        # Character_LCD_I2C() raises ValueError if it doesn't find an LCD.
        # If that happens, just ignore it and carry on. You can rely on this
        # to omit the LCD from a base station hardware build if you want.
        lcd = None

    EXPECTED_SIZE = 4 + 6 + HMAC_TRUNC    # size of header + message + MAC
    seq_list = {}
    while True:
        # receive() returns None for timeout or a bytearry of header+packet
        if data := rfm95.receive(with_header=True, timeout=60):
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
                if check == "OK":      # Don't update LCD for replay packets
                    reports.new_report(node, v, f)
                lcd.clear()
                lcd.message = str(reports)
        else:
            # In case of receive timeout, just update report age tags on LCD
            if lcd:
                lcd.message = str(reports)
