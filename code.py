# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2024 Sam Blenny
#
# Related Learn Guides:
# - https://learn.adafruit.com/radio-featherwing (LoRa FeatherWing)
# - https://learn.adafruit.com/adafruit-mcp9808-precision-i2c-temperature-sensor-guide
# - https://learn.adafruit.com/adafruit-esp32-s3-feather
# - https://learn.adafruit.com/adafruit-feather-rp2350
#
# Related API Docs:
# - https://docs.circuitpython.org/projects/max1704x/en/latest/api.html
# - https://docs.circuitpython.org/projects/mcp9808/en/latest/
# - https://docs.circuitpython.org/projects/rfm9x/en/latest/api.html (LoRa API docs)
#
#
# To use the RFM95W LoRa FeatherWing, you have to solder wires to route its
# RST, CS, and IRQ signals to match the pin capabilities of your Feather board.
# The pinout here matches my build for the RP2350 Feather and ESP32-S3 Feather.
# If you want to use this code with a different board, check the LoRa
# FeatherWing docs for compatibility with your Feather board and adjust the
# pinouts as needed.
#
# LoRa FeatherWing Pinout for use with ESP32-S3 Feather and RP2350 Feather:
# | Signal | LoRa Silkscreen | S3 Silkscreen | RP2350 SilkScreen |
# | ------ | --------------- | ------------- | ----------------- |
# |   RST  |        C        |       9       |          9        |
# |   CS   |        B        |      10       |         10        |
# |   IRQ  |        A        |      11       |         11        |
#
import board
import busio
from digitalio import DigitalInOut
from micropython import const
import os
import struct
import time

from adafruit_max1704x import MAX17048
from adafruit_mcp9808 import MCP9808
from adafruit_rfm9x import RFM9x

from sb_hmac import hmac_sha1


# -------------------------------------------------------------------------
# Config Options
# -------------------------------------------------------------------------
#
# LoRa Radio Config (see learn guide and API docs)
#
BAUD        = const(1000000)   # SPI baudrate (1 MHz, default 10MHz)
LORA_BAND   = const(915)       # LoRa band (915 MHz for US)
TX_POW      = const(8)         # LoRa TX power (range 5..23 dB, default 13)
SF          = const(9)         # Spreading factor (range 6..12, default 7)
CODING_RATE = const(5)         # Coding rate (range 5..8, default 5)
PREAMBLE    = const(10)         # Preamble (range uint16, default 8)
TX_RETRIES  = const(2)         # How many times to transmit each message
TX_INTERVAL = const(10)        # How many sleep seconds between measurements
#
# Sensor Float Range Limits (for encoding LoRa messages)
#
BATT_LO = const(3.2)
BATT_HI = const(4.2)
TEMP_LO = const(-128)
TEMP_HI = const(127)
#
# Defaults for optional settings.toml variables
#
HMAC_KEY = b'Please set your own HMAC_KEY in settings.toml'
HMAC_TRUNC = 4    # size in bytes of truncated hash (similar to HOTP)
#
# -------------------------------------------------------------------------
# Read settings.toml
if key := os.getenv("HMAC_KEY"):
    HMAC_KEY = key
if trunc := os.getenv("HMAC_TRUNC"):
    HMAC_TRUNC = trunc
# -------------------------------------------------------------------------


def rfm9x_factory(spi, cs, rst):
    # Configure an RFM9x object for the 900 MHz RFM95W LoRa FeatherWing.
    r = RFM9x(spi, cs, rst, LORA_BAND, baudrate=BAUD, agc=False, crc=False)
    r.tx_power = TX_POW
    r.spreading_factor = SF
    r.coding_rate = CODING_RATE
    r.preamble_length = PREAMBLE
    r.destination = 255             # send to all stations (nodes)
    r.node = 255                    # receive from all stations (nodes)
    return r

def scale_to_byte(val, lo, hi):
    # Scale and convert float in range lo..hi to integer in range 0..255
    return min(255, max(0, round(255 * (val - lo) / (hi - lo))))

def scale_from_byte(b, lo, hi):
    # Scale and convert integer in range 0..255 to float in range lo..hi
    return (b * (hi - lo) / 255) + lo

def encode_(count_, volt, degree_F):
    # Compress message counter and float measurements into bytes value
    v = scale_to_byte(volt, BATT_LO, BATT_HI)
    t = scale_to_byte(degree_F, TEMP_LO, TEMP_HI)
    return struct.pack('>LBB', count_, v, t)

def decode_(data):
    # Expand bytes into float measurements with correct range
    count_, v_byte, t_byte = struct.unpack('>LBB', data)
    v = scale_from_byte(v_byte, BATT_LO, BATT_HI)
    t = scale_from_byte(t_byte, TEMP_LO, TEMP_HI)
    return count_, v, t

def start_tx_mode(i2c, spi, cs, rst):
    # Initialize and run in remote sensor hardware configuration (LoRa TX)
    max17 = MAX17048(i2c)                  # battery fuel gauge
    mcp98 = MCP9808(i2c)                   # temperature sensor
    rfm95 = rfm9x_factory(spi, cs, rst)    # LoRa radio
    key = HMAC_KEY
    truncate = HMAC_TRUNC
    seq = 0                                # 32-bit message sequence number
    while True:
        seq = (seq + 1) & 0xffffffff       # increment sequence number
        v = max17.cell_voltage             # measure battery Volts
        c = mcp98.temperature              # measure temperature (°C)
        f = (c * 9/5) + 32                 # convert °C to °F
        msg = encode_(seq, v, f)           # pack measurements as bytes
        hash_ = hmac_sha1(key, msg)        # get HMAC of message
        hash_ = hash_[:truncate]           # truncate hash (like HOTP)
        print('TX: %08x, %.2f, %.1f, %s' %
            (seq, v, f, hash_.hex()))
        msg += hash_                       # append truncated MAC hash
        for _ in range(TX_RETRIES):        # start transmitting packets
            rfm95.send(msg)
        time.sleep(0.02)                   # wait for packets to finish
        rfm95.idle()                       # put radio in low power mode
        time.sleep(TX_INTERVAL)

def start_rx_mode(spi, cs, rst):
    # Initialize and run in base station hardware configuration (LoRa RX)
    EXPECTED_SIZE = 6 + HMAC_TRUNC            # byte-size of message + MAC
    truncate = HMAC_TRUNC
    key = HMAC_KEY
    print('Starting LoRa Receiver.')
    rfm95 = rfm9x_factory(spi, cs, rst)       # LoRa radio
    prev_seq = 0
    while True:
        if data := rfm95.receive():           # get packet as bytearray
            rssi = rfm95.last_rssi            # check signal strength
            snr = rfm95.last_snr
            if EXPECTED_SIZE != len(data):    # skip wrong-size packets
                continue
            # Decode and print the payload. Payload should contain
            # a message with the sequence number, volts, °F, then a
            # truncated HMAC of the message
            msg = data[:-truncate]
            msg_hash = data[-truncate:]
            seq, v, f = decode_(msg)
            check_hash = hmac_sha1(key, msg)[:truncate]
            # Check for monotonic sequence number and valid HMAC
            if (seq <= prev_seq) or (msg_hash != check_hash):
                continue
            # Making it here means packet is in sequence and authenticated.
            # Print decoded packet then update sequence number.
            print('RX:  rssi=%d, snr=%.1f, %08x, %.2f, %.0f, %s' %
                (rssi, snr, seq, v, f, msg_hash.hex()))
            prev_seq = seq


# -------------------------------------------
# At boot, select mode according to board_id:
# -------------------------------------------

time.sleep(0.01)  # SX127x radio needs 10ms after reset
if board.board_id == 'adafruit_feather_esp32s3_nopsram':
    # Remote Sensor (TX)
    time.sleep(0.01)  # SX127x radio needs 10ms after reset
    i2c = board.STEMMA_I2C()
    spi = board.SPI()
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)
    start_tx_mode(i2c, spi, cs, rst)
elif board.board_id == 'adafruit_feather_rp2350':
    # Base Station (RX)
    spi = board.SPI()
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)
    start_rx_mode(spi, cs, rst)
else:
    raise ValueError("Unexpected board_id. Halting. (check code.py)")
