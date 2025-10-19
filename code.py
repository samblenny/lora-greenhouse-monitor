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


# -------------------------------------------------------------------
# Config Options for LoRa FeatherWing (see learn guide and API docs)
# -------------------------------------------------------------------
BAUD        = const(1000000)   # SPI baudrate (1 MHz)
LORA_BAND   = const(915)       # LoRa band (915 MHz for US)
TX_POW      = const(5)         # LoRa transmit power (range 5..23 dB)
DESTINATION = const(255)       # Send to all stations (nodes)
NODE        = const(255)       # Receive from all stations (nodes)
RX_TIMEOUT  = const(5)         # timeout (unit is seconds)
# -------------------------------------------------------------------


class Remote:
    """Code for the remote sensor hardware configuration (LoRa TX)"""

    def __init__(self, max17, mcp98, rfm95):
        # args: max17: MAX17048, mcp98: MCP9808, rfm95: RFM9x
        self.max17 = max17
        self.mcp98 = mcp98
        self.rfm95 = rfm95
        rfm95.tx_power = TX_POW
        rfm95.destination = DESTINATION
        rfm95.node = NODE

    def volts(self):
        # Check battery voltage
        self.max17.wake()
        time.sleep(0.1)
        return max17.cell_voltage

    def deg_F(self):
        # Check temperature, converting from Celsius to Fahrenheit
        C = self.mcp98.temperature
        F = (C * 9 / 5) + 32
        return F

    def run(self):
        # Read sensors and transmit measurements
        while True:
            msg = '%.2f,%.1f' % (self.volts(), self.deg_F())
            print('TX:', msg)
            ok = self.rfm95.send(msg, destination=255)
            if not ok:
                print('TX failed')
            time.sleep(5)


class BaseStation:
    """Code for the base station hardware configuration (LoRa RX)"""

    def __init__(self, rfm95):
        # args: rfm95: RFM9x
        self.rfm95 = rfm95
        rfm95.tx_power = TX_POW
        rfm95.destination = DESTINATION
        rfm95.node = NODE

    def run(self):
        # Test sensors and radio RX
        # TODO: implement base station RX and switch this to TX
        print('LoRa RX...')
        while True:
            packet = self.rfm95.receive()
            if packet:
                print('RSSI dB: %d, %s' % (self.rfm95.last_rssi, packet))


# ---------------------------------------------------------------------------
# Initialize hardware based on board_id:
# - ESP32-S3 Feather: remote sensor
# - RP2350 Feather: base station
#
# If you want to use different Feather boards, add a new section here for
# your board's board_id (double check LoRa pinout compatibility first!)
# --------------------------------------------------------------------------
#
if board.board_id == 'adafruit_feather_esp32s3_nopsram':
    # Initialize hardware as remote sensor
    i2c = board.STEMMA_I2C()
    spi = board.SPI()
    max17 = MAX17048(i2c)                   # Built in I2C battery fuel gauge
    mcp98 = MCP9808(i2c)                    # External I2C temperature sensor
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)
    rfm95 = RFM9x(spi, cs, rst, LORA_BAND, baudrate=BAUD)  # LoRa FeatherWing
    remote = Remote(max17, mcp98, rfm95)
    # Send measurements
    remote.run()
elif board.board_id == 'adafruit_feather_rp2350':
    # Initialize hardware as base station
    spi = board.SPI()
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)
    rfm95 = RFM9x(spi, cs, rst, LORA_BAND, baudrate=BAUD)  # LoRa FeatherWing
    base = BaseStation(rfm95)
    # Receive measurements
    base.run()
else:
    raise Error("Unexpected board_id. Halting. (check code.py comments)")
