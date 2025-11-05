# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Sensor
#
import alarm
from board import A0, A1, D9, D10, SCL, SDA, SPI
import busio
from digitalio import DigitalInOut
from microcontroller import cpu
from micropython import const
import os
import struct
import sys
import time

from adafruit_max1704x import MAX17048
from adafruit_mcp9808 import MCP9808

from common import HMAC_KEY, HMAC_TRUNC, LORA_NODE, encode_, rfm9x_factory
from sb_hmac import hmac_sha1


TARGET_INTERVAL = const(20.0)    # approximate seconds between transmits
WAKE_SECONDS = const(1.963)      # wake runtime as measured by power profiler

def light_sleep(seconds):
    alarm.light_sleep_until_alarms(
        alarm.time.TimeAlarm(monotonic_time=(time.monotonic() + seconds)))

def run(a1, tx_interval_s=5.0):
    # Initialize and run in remote sensor hardware configuration (LoRa TX)

    # Use GPIO outs to mark progress of run() for power analyzer logic inputs
    a0 = DigitalInOut(A0)
    a0.switch_to_output(value=True)
    a1.value = False

    # Reduce CPU frequency to save power during I2C and LoRa IO delays. The
    # default frequency is 240 MHz. To avoid messing up time.monotonic(), don't
    # attempt to set this below 80 MHz.
    cpu.frequency = 80_000_000

    # Configure I2C sensors first to allow warm-up time before measurements
    i2c = busio.I2C(SCL, SDA, frequency=250_000)  # Use fast bus clock
    mcp98 = MCP9808(i2c)           # temperature sensor
    mcp98.resolution = 1           # 0.25°C resolution @ 65ms conversion time
    ts = time.monotonic() + 0.067  # schedule the temperature sampling time
    max17 = MAX17048(i2c)          # battery fuel gauge

    # Configure LoRa radio
    cs, rst = DigitalInOut(D10), DigitalInOut(D9)
    rfm95 = rfm9x_factory(SPI(), cs, rst)

    # Get truncated Unix timestamp from RTC to use as message sequence number
    tstamp = time.time() & 0xffffffff

    # Wait until a full temperature sensor sample period has elapsed
    pre_sample_delay = max(0, ts - time.monotonic())
    light_sleep(pre_sample_delay)

    # Check sensors then build packet with message (node address, timestamp,
    # volts, temperature) + truncated HMAC of message (modeled on TOTP)
    v = max17.cell_voltage                        # lipo cell volts
    f = (mcp98.temperature * 9/5) + 32            # °C -> °F
    msg = encode_(LORA_NODE, tstamp, v, f)        # pack everything into bytes
    msg += hmac_sha1(HMAC_KEY, msg)[:HMAC_TRUNC]  # append truncated HMAC

    # Send packet on LoRa radio with one repeat for better reliability. This
    # uses two different power levels for range testing. Note that the node
    # address is included in the message for the HMAC, but the node byte gets
    # sent as part of the header rather than in the payload.
    sys.stdout.write('%d, %08x, %.2f, %.1f\n' % (LORA_NODE, tstamp, v, f))
    a1.value = True
    rfm95.tx_power = 10               # tx power range is 5..23 dB, default 13
    rfm95.send(msg[1:], node=msg[0])
    a1.value = False
    rfm95.tx_power = 16               # +6 dB for the second one
    rfm95.send(msg[1:], node=msg[0])
    a1.value = True

    # Prepare peripherals and pins for low power
    rfm95.sleep()
    max17.hibernate()
    a0.value, a1.value = False, False

    # Begin deep sleep with ±2% random jitter added to target sleep interval
    t1 = TARGET_INTERVAL - WAKE_SECONDS
    t2 = t1 + (t1 * 0.02 * os.urandom(1)[0] / 255)
    alarm.exit_and_deep_sleep_until_alarms(
        alarm.time.TimeAlarm(monotonic_time=time.monotonic() + t2))
