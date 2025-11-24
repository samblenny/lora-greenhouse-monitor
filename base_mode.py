# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Base Station
#
# See NOTES.md for related documentation
#
import board
from board import SCL, SDA, SPI
import busio
from collections import namedtuple
from digitalio import DigitalInOut
from microcontroller import cpu
import os
import struct
import time

from adafruit_character_lcd.character_lcd_i2c import Character_LCD_I2C

from common import HMAC_TRUNC, HMAC_KEY, decode_, rfm9x_factory
from sb_hmac import hmac_sha1

# ---------------------------------------------------------------------------
# Options for settings.toml
# - `LCD_BACKLIGHT = 1` enable character LCD backlight
# - `ESPNOW_GATEWAY = 1` retransmit LoRa packets as ESP-NOW packets
# - `ESPNOW_RX = 1` use ESP-NOW radio on builds that don't have a LoRa radio
#
LCD_BACKLIGHT = False
if (backlight := os.getenv("LCD_BACKLIGHT")) is not None:
    LCD_BACKLIGHT = bool(backlight)
ESPNOW_GATEWAY = False
if (gateway := os.getenv("ESPNOW_GATEWAY")) is not None:
    ESPNOW_GATEWAY = bool(gateway)
ESPNOW_RX = False
if (display_ := os.getenv("ESPNOW_RX")) is not None:
    ESPNOW_RX = bool(display_)
# ---------------------------------------------------------------------------


Report = namedtuple("Report",
        ["node_id", "timestamp", "volts", "temp_f", "rssi", "snr"])

class SensorReports:
    # This tracks reports from multiple sensors to format them for a 2x16 LCD
    def __init__(self):
        self.ready_timestamp = time.monotonic()
        self.lora_nodes = {}
        self.last_report = None

    def new_report(self, node_id, volts, temp_f, rssi, snr):
        r = Report(node_id, time.monotonic(), volts, temp_f, rssi, snr)
        self.lora_nodes[node_id] = r
        self.last_report = r

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
        # Display latest report info formatted for 2x16 LCD
        r = self.last_report
        centivolts = round(r.volts * 100)
        tag = self.freshness_tag(now - r.timestamp)
        return '%d %d %d %s\n r%d s%.1f' % (
            r.node_id, r.temp_f, centivolts, tag, r.rssi, r.snr)


def run():
    # Initialize and run in base station hardware configuration (LoRa RX)

    # Print a banner showing which modes are active from settings.toml
    modes = ['=== Base Station']
    if ESPNOW_GATEWAY:
        modes.append(' + ESP-NOW Gateway')
    if ESPNOW_RX:
        modes.append(' + ESP-NOW Display')
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
    if 'esp32s3' in board.board_id:
        cpu.frequency = 80_000_000

    # Try to initialize LoRa raido on SPI unless ESPNOW_RX option is turned on
    rfm95 = None
    if not ESPNOW_RX:
        cs, rst = DigitalInOut(board.D10), DigitalInOut(board.D9)
        rfm95 = rfm9x_factory(SPI(), cs, rst)
        rfm95.node = 255               # receive from all stations (nodes)

    # Try to initialize an I2C Character LCD. This is an optional feature
    # to assist with placing the antenna for good RSSI & SNR. The main output
    # for logging and charting goes over USB serial to a Raspberry Pi.
    lcd = None
    try:
        i2c = busio.I2C(SCL, SDA, frequency=250_000)  # default clock is slow
        cols, rows = 16, 2
        lcd = Character_LCD_I2C(i2c, cols, rows)
        lcd.clear()
        if LCD_BACKLIGHT:
            lcd.backlight = True
        lcd.message = 'Ready 0m'
    except RuntimeError as e:
        # This can happen on QT Py if you don't have pullups connected:
        # - RuntimeError: No pull up found on SDA or SCL; check your wiring
        pass
    except ValueError as e:
        # This happens if no I2C LCD backpack is present at 0x20
        pass

    # If one of the ESP-NOW modes is active, try to initialize wifi radio
    espnow_obj = None
    if ESPNOW_GATEWAY or ESPNOW_RX:
        import espidf
        import espnow
        import wifi
        # Force wifi radio onto channel 6 because esp-now needs that
        wifi.radio.start_ap(" ", "", channel=6, max_connections=0)
        wifi.radio.stop_ap()
        # Initialize the ESP-NOW object in broadcast mode
        espnow_obj = espnow.ESPNow()
        peer = espnow.Peer(mac=b'\xff\xff\xff\xff\xff\xff', channel=6)
        espnow_obj.peers.append(peer)

    # -----
    # BEGIN Receiver Loop
    # -----
    reports = SensorReports()
    EXPECTED_SIZE = 4 + 6 + HMAC_TRUNC    # size of header + message + MAC
    seq_list = {}
    TIMEOUT = 60
    while True:
        # Listen for message from ESP-NOW or LoRa radio, depending on settings
        if ESPNOW_RX:
            # Radio for RX is ESP-NOW
            # Since espnow.read() is buffered async, put it in a loop to make
            # it act like a blocking read in the style of RFM9x.receive()
            stop_time = time.monotonic() + TIMEOUT
            data = None
            while time.monotonic() < stop_time:
                if len(espnow_obj) > 1:
                    packet = espnow_obj.read()
                    data = packet.msg
                    espnow_rssi = packet.rssi
                    # ESP-NOW packets have int16_t rssi and snr at the end of
                    # the payload so the ESP-NOW receiver can see how good the
                    # signal was at the LoRa receiver on the gateway
                    if len(data) == EXPECTED_SIZE + 4:
                        i = EXPECTED_SIZE
                        # pop the LoRa rssi and snr values
                        snr = struct.unpack('>h', data[i+2:i+4])[0]
                        rssi = struct.unpack('>h', data[i:i+2])[0]
                        data = data[:EXPECTED_SIZE]
                    else:
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
            radio_tag = "ESPNOW" if ESPNOW_RX else "LORA"
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

            # Update the reports data structure
            reports.new_report(node, v, f, rssi, snr)

            # If there's a character LCD available, show report message
            if lcd:
                lcd.clear()
                lcd.message = str(reports)

            # If ESPNOW_GATEWAY mode is enabled, check the hop count then
            # retransmit the packet if hops are low enough.
            to    = data[0]
            from_ = data[1]
            id_   = data[2]
            hops  = data[3] & 0x0f  # Low 4 bits of flags field of LoRa header
            max_hops = 1
            # Slice payload out of header+payload
            payload = data[4:]
            # Sush RSSI & SNR at end of payload
            payload += struct.pack('>hh', max(-256, min(0, round(rssi))),
                max(-256, min(256, round(snr))))
            if ESPNOW_GATEWAY and seq_check and hops < max_hops:
                new_hop = min(16, hops+1)
                enow_msg = bytearray([to, from_, id_, new_hop]) + payload
                try:
                    espnow_obj.send(enow_msg, peer)
                except Exception as e:
                    print('E', e)  # Log the error and keep going

        else:
            # For receive timeout, update report age tags on LCD
            if lcd:
                lcd.message = str(reports)
