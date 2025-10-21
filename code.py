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
import time

from adafruit_max1704x import MAX17048
from adafruit_mcp9808 import MCP9808
from adafruit_rfm9x import RFM9x


# ------------------------------------------------------------------------
# Config Options for LoRa FeatherWing (see learn guide and API docs)
# ------------------------------------------------------------------------
BAUD        = const(1000000)   # SPI baudrate (1 MHz, default 10MHz)
LORA_BAND   = const(915)       # LoRa band (915 MHz for US)
TX_POW      = const(8)         # LoRa TX power (range 5..23 dB, default 13)
SF          = const(9)         # Spreading factor (range 6..12, default 7)
CODING_RATE = const(5)         # Coding rate (range 5..8, default 5)
DESTINATION = const(255)       # Send to all stations (nodes)
NODE        = const(255)       # Receive from all stations (nodes)
# ------------------------------------------------------------------------

# ------------------------------------------------
# Sensor Range Limits (for encoding LoRa messages)
# ------------------------------------------------
BATT_LO = const(3.2)
BATT_HI = const(4.2)
TEMP_LO = const(-128)
TEMP_HI = const(127)
# ------------------------------------------------


def rfm9x_factory(spi, cs, rst):
    """Configure an RFM9x object for the 900 MHz RFM95W LoRa FeatherWing"""
    r = RFM9x(spi, cs, rst, LORA_BAND, baudrate=BAUD)
    r.tx_power = TX_POW
    r.spreading_factor = SF
    r.coding_rate = CODING_RATE
    r.destination = DESTINATION
    r.node = NODE
    return r

def scale_to_byte(val, lo, hi):
    return min(255, max(0, round(255 * (val - lo) / (hi - lo))))

def scale_from_byte(b, lo, hi):
    return (b * (hi - lo) / 255) + lo

def encode_msg(volt, degree_F):
    v = scale_to_byte(volt, BATT_LO, BATT_HI)
    t = scale_to_byte(degree_F, TEMP_LO, TEMP_HI)
    return bytes((v, t))

def decode_msg(data):
    v = scale_from_byte(data[0], BATT_LO, BATT_HI)
    t = scale_from_byte(data[1], TEMP_LO, TEMP_HI)
    return v, t


class Remote:
    """Controller class for remote sensor hardware configuration (LoRa TX)"""

    def __init__(self, i2c, spi, cs, rst):
        # CAUTION: Older versions of the ESP32-S3 Feather used a different I2C
        # fuel gauge chip. This code is for current board revision.
        self.max17 = MAX17048(i2c)                # Built in battery fuel gauge
        self.mcp98 = MCP9808(i2c)                 # External temperature sensor
        self.rfm95 = rfm9x_factory(spi, cs, rst)  # LoRa FeatherWing

    def volts(self):
        # Return battery volts.
        self.max17.wake()
        time.sleep(0.1)
        return self.max17.cell_voltage

    def deg_F(self):
        # Return temperature in Fahrenheit (converted from Celsius)
        return (self.mcp98.temperature * 9 / 5) + 32

    def run(self):
        # Read sensors and transmit measurements
        while True:
            v = self.volts()
            f = self.deg_F()
            msg = encode_msg(v, f)
            print('TX: %.2f, %.1f' % (v, f))
            if err := not self.rfm95.send(msg, destination=255):
                print('TX failed')
            time.sleep(5)


class BaseStation:
    """Controller class for base station hardware configuration (LoRa RX)"""

    def __init__(self, spi, cs, rst):
        self.rfm95 = rfm9x_factory(spi, cs, rst)  # LoRa FeatherWing

    def handle_packet(self, rssi, snr, msg):
        print('RX: rssi:%d, snr:%.1f, ' % (rssi, snr), end='')
        if len(msg) == 2:
            v, f = decode_msg(msg)
            print('%.2f, %.0f' % (v, f))
        else:
            print(msg)

    def run(self):
        # Receive, decode, and print measurements
        print('Starting LoRa Receiver.')
        lora = self.rfm95
        while True:
            if packet := lora.receive():
                msg = bytes(packet)
                self.handle_packet(lora.last_rssi, lora.last_snr, msg)


# ------------------------------------------
# At boot: Select mode according to board_id
# ------------------------------------------

if board.board_id == 'adafruit_feather_esp32s3_nopsram':
    # Remote Sensor Mode
    i2c = board.STEMMA_I2C()
    spi = board.SPI()
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)
    Remote(i2c, spi, cs, rst).run()
elif board.board_id == 'adafruit_feather_rp2350':
    # Base Station Mode
    spi = board.SPI()
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)
    BaseStation(spi, cs, rst).run()
else:
    raise ValueError("Unexpected board_id. Halting. (check code.py comments)")
