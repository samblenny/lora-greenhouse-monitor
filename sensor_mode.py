# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Sensor
#
import alarm
import board
import digitalio
from digitalio import DigitalInOut
import struct
import time

from adafruit_max1704x import MAX17048
from adafruit_mcp9808 import MCP9808
from adafruit_rfm9x import RFM9x

from common import (
    HMAC_KEY, HMAC_TRUNC, TX_INTERVAL, TX_RETRIES, encode_, rfm9x_factory
)
from sb_hmac import hmac_sha1


def light_sleep(seconds):
    # Power saving light sleep (preserves memory, IO ops, and program counter)
    alarm.light_sleep_until_alarms(
        alarm.time.TimeAlarm(monotonic_time=(time.monotonic() + seconds)))

def deep_sleep(seconds):
    # Power saving deep sleep (wakes as if reset, but preserves sleep_memory)
    alarm.exit_and_deep_sleep_until_alarms(
        alarm.time.TimeAlarm(monotonic_time=time.monotonic() + seconds))

def set_nvram(uint32):
    # Save a uint32 to sleep_memory to persist across deep sleeps
    alarm.sleep_memory[:4] = struct.pack('<I', uint32 & 0xffffffff)

def get_nvram():
    # Return a uint32 from sleep_memory (saved from before deep sleep)
    return struct.unpack_from('<I', alarm.sleep_memory[:4], 0)[0]

def run():
    # Initialize and run in remote sensor hardware configuration (LoRa TX)

    # Mark start of run() for power analyzer's logic inputs
    a0 = digitalio.DigitalInOut(board.A0)
    a0.switch_to_output(value=True)
    a1 = digitalio.DigitalInOut(board.A1)
    a1.switch_to_output(value=False)

    i2c = board.STEMMA_I2C()
    spi = board.SPI()
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)

    light_sleep(0.01)                     # SX127x radio needs 10ms after reset
    max17 = MAX17048(i2c)                 # battery fuel gauge
    mcp98 = MCP9808(i2c)                  # temperature sensor
    # NOTE: It might save power to set
    # MCP9808's resolution register to 1
    # for reduced sample time, but
    # `mcp98.resolution = 1` throws
    # an OSError exception (a bug?)
    rfm95 = rfm9x_factory(spi, cs, rst)   # LoRa radio
    key = HMAC_KEY
    truncate = HMAC_TRUNC

    seq = get_nvram()                     # 32-bit message sequence number
    seq = (seq + 1) & 0xffffffff          # increment sequence number
    set_nvram(seq)                        # save sequence number in NV RAM
    v = max17.cell_voltage                # measure battery Volts
    c = mcp98.temperature                 # measure temperature (°C)
    f = (c * 9/5) + 32                    # convert °C to °F
    msg = encode_(seq, v, f)              # pack measurements as bytes
    hash_ = hmac_sha1(key, msg)           # get HMAC of message
    hash_ = hash_[:truncate]              # truncate hash (like HOTP)
    print('TX: %08x, %.2f, %.1f, %s' %
        (seq, v, f, hash_.hex()))
    msg += hash_                          # append truncated MAC hash
    for _ in range(TX_RETRIES):           # start transmitting packets
        rfm95.send(msg)

    # Put peripherals in low power mode
    rfm95.sleep()
    max17.hibernate()

    # Mark end of run() for the power analyzer's logic inputs
    a0.value = False
    a1.value = False

    # Begin deep sleep
    deep_sleep(TX_INTERVAL)
