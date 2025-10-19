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


def rfm9x_factory(spi, cs, rst):
    """Configure an RFM9x object for the 900 MHz RFM95W LoRa FeatherWing"""
    r = RFM9x(spi, cs, rst, LORA_BAND, baudrate=BAUD)
    r.tx_power = TX_POW
    r.spreading_factor = SF
    r.coding_rate = CODING_RATE
    r.destination = DESTINATION
    r.node = NODE
    return r


class Remote:
    """Controller class for remote sensor hardware configuration (LoRa TX)"""

    def __init__(self, i2c, spi, cs, rst):
        # CAUTION: Older versions of the ESP32-S3 Feather used a different I2C
        # fuel gauge chip. This code is for current board revision.
        self.max17 = MAX17048(i2c)                # Built in battery fuel gauge
        self.mcp98 = MCP9808(i2c)                 # External temperature sensor
        self.rfm95 = rfm9x_factory(spi, cs, rst)  # LoRa FeatherWing

    def centivolts(self):
        # Return battery voltage as centivolts integer (hundredths of a Volt).
        # The point of cV units is to encode as an integer instead of a float.
        self.max17.wake()
        time.sleep(0.1)
        return round(self.max17.cell_voltage * 100)

    def deg_F(self):
        # Return temperature as Fahrenheit integer (converted from Celsius)
        return round((self.mcp98.temperature * 9 / 5) + 32)

    def run(self):
        # Read sensors and transmit measurements
        while True:
            msg = '%d,%d' % (self.centivolts(), self.deg_F())
            print('TX:', msg)
            if err := not self.rfm95.send(msg, destination=255):
                print('TX failed')
            time.sleep(5)


class BaseStation:
    """Controller class for base station hardware configuration (LoRa RX)"""

    def __init__(self, spi, cs, rst):
        self.rfm95 = rfm9x_factory(spi, cs, rst)  # LoRa FeatherWing

    def run(self):
        # Receive measurements
        print('LoRa RX Started.')
        lora = self.rfm95
        while True:
            if packet := lora.receive():
                rssi = lora.last_rssi
                snr = lora.last_snr
                msg = bytes(packet)
                print('rssi: %d, snr: %.1f, %s' % (rssi, snr, msg))


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
