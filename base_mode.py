# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Base Station
#
# See NOTES.md for related documentation
#
import board
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
# RSSI and SNR Display
#
# To enable RSSI display mode, put `RSSI_SNR_DISPLAY = 1` in settings.toml.
#
# This will show LoRa RSSI and SNR on the second line of the sensor report
# display (instead of min/max temperature). You can use it for checking
# signal strength at different receiver locations.
#
RSSI_SNR_DISPLAY = False
if (rssisnr := os.getenv("RSSI_SNR_DISPLAY")) is not None:
    RSSI_SNR_DISPLAY = bool(rssisnr)
# ---------------------------------------------------------------------------
# Repeater Mode
#
# To enable repeater mode, put `LORA_REPEATER = 1` in settings.toml.
#
# This helps with placing an LCD base station in a place with good visibility
# for watching the display but with a poor line of sight to the sensor(s). By
# putting the repeater node in location with better line of sight, you can
# extend the range of the sensor.
#
LORA_REPEATER = False
if (repeater := os.getenv("LORA_REPEATER")) is not None:
    LORA_REPEATER = bool(repeater)
# ---------------------------------------------------------------------------
# ESP-NOW Gateway & Display Mode
#
# - To enable LoRa to ESP-NOW Gateway mode, put `ESPNOW_GATEWAY = 1` in
#   settings.toml
# - To enable ESP-NOW Display mode, put `ESPNOW_DISPLAY = 1` in settings.toml
#
# This is for using a Gateway with both LoRa and ESP-NOW (ESP32 wifi) radios
# to extend the range of sensors. The gateway can go somewhere with a good
# line of sight to the sensor, and the remote display unit can go somewhere
# within ESP-NOW range of the gateway.
#
ESPNOW_GATEWAY = False
if (gateway := os.getenv("ESPNOW_GATEWAY")) is not None:
    ESPNOW_GATEWAY = bool(gateway)
ESPNOW_DISPLAY = False
if (display_ := os.getenv("ESPNOW_DISPLAY")) is not None:
    ESPNOW_DISPLAY = bool(display_)
# ---------------------------------------------------------------------------


Report = namedtuple("Report", ["timestamp", "volts", "degree_f"])

Node = namedtuple("Node", ["reports", "min_f", "max_f"])

class SensorReports:
    # This tracks reports from multiple sensors to format them for a 2x16 LCD
    def __init__(self):
        self.ready_timestamp = time.monotonic()
        self.lora_nodes = {}
        self.rssi = 0
        self.snr = 0

    def new_report(self, lora_node, volts, degree_f, rssi, snr):
        self.rssi = rssi
        self.snr = snr
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
        hours = seconds // 3600   # 60*60=3600 seconds/hour
        days = seconds // 86400   # 60*60*24=86400 seconds/day
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
        if RSSI_SNR_DISPLAY:
            # second line has RSSI and SNR
            return '%d %.1fV %s %.0fF\n r%d s%.1f' % (
                node_key, r.volts, tag, r.degree_f, self.rssi, self.snr)
        else:
            # second line has min/max temperature
            return '%d %.1fV %s %.0fF\n %.0fF %.0fF' % (
                node_key, r.volts, tag, r.degree_f, n.min_f, n.max_f)


def run():
    # Initialize and run in base station hardware configuration (LoRa RX)

    # Print a banner showing which modes are active from settings.toml
    modes = ['=== Base Station']
    if LORA_REPEATER:
        modes.append(' + LoRa Repeater')
    if ESPNOW_GATEWAY:
        modes.append(' + ESP-NOW Gateway')
    if ESPNOW_DISPLAY:
        modes.append(' + ESP-NOW Display')
    if RSSI_SNR_DISPLAY:
        modes.append(' + RSSI SNR Display')
    modes.append(' ===')
    banner = ''.join(modes)
    hr = '=' * len(banner)
    print()
    print(hr)
    print(banner)
    print(hr)

    # Reduce CPU frequency so the board runs cooler. The default ESP32-S3
    # default frequency is 240 MHz. To avoid messing up time.monotonic(), don't
    # attempt to set this below 80 MHz.
    if cpu.frequency == 240_000_000:
        cpu.frequency = 80_000_000

    # Conditionally try to initialize SPI peripherals:
    # - In ESPNOW_DISPLAY mode on a Metro ESP32-S3, there may be an ILI9341 TFT
    #   display shield (otherwise there might be an I2C 2x16 character LCD)
    # - In other modes, there should be a LoRa module
    display = None
    rfm95 = None
    textbox = None
    if ESPNOW_DISPLAY:
        if board.board_id == 'adafruit_metro_esp32s3':
            # Try to initialize 2.8" TFT display shield
            try:
                import displayio
                from fourwire import FourWire
                import terminalio
                from adafruit_ili9341 import ILI9341
                from adafruit_display_text import label
                displayio.release_displays()
                spi = board.SPI()
                tft_cs = board.D10
                tft_dc = board.D9
                display_bus = FourWire(spi, command=tft_dc, chip_select=tft_cs)
                display = ILI9341(display_bus, width=320, height=240,
                    rotation=180)
                group = displayio.Group()
                display.root_group = group
                textbox = label.Label(font=terminalio.FONT, scale=3,
                    color=0xefef00)
                textbox.text = "Ready 0m"
                textbox.anchor_point = (0, 0)
                textbox.anchored_position = (18, 18)
                group.append(textbox)
            except Exception as e:
                print('A', e)  # Log the error and keep going
    else:
        # Try to initialize LoRa module
        try:
            cs, rst = DigitalInOut(D10), DigitalInOut(D9)
            rfm95 = rfm9x_factory(SPI(), cs, rst)
            rfm95.node = 255               # receive from all stations (nodes)
        except Exception as e:
            print('B', e)  # Log the error and keep going

    # Try to initialize an I2C Character LCD
    i2c = busio.I2C(SCL, SDA, frequency=250_000)  # default bus clock is slow
    lcd = None
    try:
        cols, rows = 16, 2
        lcd = Character_LCD_I2C(i2c, cols, rows)
        lcd.clear()
        if LCD_BACKLIGHT:
            lcd.backlight = True
        lcd.message = 'Ready 0m'
    except ValueError as e:
        # This happens if no I2C LCD backpack is present at 0x20
        pass

    # Conditionally try to initialize ESP-NOW over wifi for modes that need it
    espnow_obj = None
    if ESPNOW_GATEWAY or ESPNOW_DISPLAY:
        try:
            import espidf
            import espnow
            import wifi
            # Force wifi radio onto channel 6 because esp-now needs that
            wifi.radio.start_ap(" ", "", channel=6, max_connections=0)
            wifi.radio.stop_ap()
            # Now initialize the ESP-NOW object in broadcast mode
            espnow_obj = espnow.ESPNow()
            peer = espnow.Peer(mac=b'\xff\xff\xff\xff\xff\xff', channel=6)
            espnow_obj.peers.append(peer)
        except Exception as e:
            print('D', e)  # Log the error and keep going

    # -----
    # BEGIN Receiver Loop
    # -----
    reports = SensorReports()
    EXPECTED_SIZE = 4 + 6 + HMAC_TRUNC    # size of header + message + MAC
    seq_list = {}
    TIMEOUT = 60
    while True:
        # Listen for message from ESP-NOW or LoRa radio, depending on settings.
        if ESPNOW_DISPLAY:
            # Radio for RX is ESP-NOW
            # Since espnow.read() is buffered async, put it in a loop to make
            # it act like a blocking read in the style of RFM9x.receive()
            stop_time = time.monotonic() + TIMEOUT
            data = None
            while time.monotonic() < stop_time:
                if len(espnow_obj) > 1:
                    packet = espnow_obj.read()
                    data = packet.msg
                    rssi = packet.rssi
                    snr = 0
                    break
                else:
                    time.sleep(0.01)
        else:
            # Radio for RX is LoRa
            data = rfm95.receive(with_header=True, timeout=TIMEOUT)
            rssi = rfm95.last_rssi                   # signal strength
            snr = rfm95.last_snr                     # signal to noise ratio

        # Handle the packet (check length, verify HMAC, etc).
        # Data should be None for timeout or a bytearry of header+packet.
        if data:
            # Skip wrong-size packets
            if EXPECTED_SIZE != len(data):
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
            seq_check = False
            prev_seq = seq_list.get(node)
            if (prev_seq is None) or (prev_seq < seq):
                seq_check = True
                seq_list[node] = seq

            # Now packet is authenticated (HMAC) but possibly a duplicate.
            # Print decoded packet regardless, as it can be useful to see
            # RSSI and SNR for retry packets.
            check_tag = "OK" if seq_check else "DUP"
            radio_tag = "ESPNOW" if ESPNOW_DISPLAY else "LORA"
            print('%s: %d, %.1f, %d, %08x, %.2f, %.0f, %s' %
                (radio_tag, rssi, snr, node, seq, v, f, check_tag))

            # -----
            # END receive section
            # BEGIN display / repeater / gateway section
            # -----

            # Don't do any of the stuff below for duplicate packets that failed
            # the monotonic sequence number check
            if not seq_check:
                continue

            # Update the reports data structure (for min/max temperature, etc)
            reports.new_report(node, v, f, rssi, snr)

            # If there's a character LCD available, show report message
            if lcd:
                lcd.clear()
                lcd.message = str(reports)

            # If there's a display with textbox available, show report message
            if textbox:
                textbox.text = str(reports)

            # If LORA_REPEATER mode or ESPNOW_GATEWAY mode are enabled, check
            # the hop count then retransmit the packet if hops are low enough.
            to    = data[0]
            from_ = data[1]
            id_   = data[2]
            hops  = data[3] & 0x0f  # Low 4 bits of flags field of LoRa header
            max_hops = 1
            payload = data[4:]      # Slice payload out of header+payload
            if LORA_REPEATER and seq_check and hops < max_hops:
                new_hop = min(16, hops+1)
                rfm95.tx_power = 13  # tx power range is 5..23 dB, default 13
                rfm95.send(payload, node=from_, destination=to, flags=new_hop)
            if ESPNOW_GATEWAY and seq_check and hops < max_hops:
                new_hop = min(16, hops+1)
                enow_msg = bytearray([to, from_, id_, new_hop]) + payload
                try:
                    wifi.radio.enabled = True
                    wifi.radio.start_ap(" ", "", channel=6, max_connections=0)
                    wifi.radio.stop_ap()
                    espnow_obj.send(enow_msg, peer)
                    time.sleep(0.1)
                    # Turn wifi back off in the possibly fruitless attempt to
                    # decrease noise floor for the LoRa radio
                    wifi.radio.enabled = False
                except Exception as e:
                    print('E', e)  # Log the error and keep going

        else:
            # For receive timeout, update report age tags on LCD or TFT display
            if lcd:
                lcd.message = str(reports)
            if textbox:
                textbox.text = str(reports)
