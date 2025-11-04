# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Sensor
#
import alarm
from board import A0, A1, A2, A3, D9, D10, SPI, STEMMA_I2C
import digitalio
import struct
import sys
import time

from adafruit_max1704x import MAX17048
from adafruit_mcp9808 import MCP9808

from common import HMAC_KEY, HMAC_TRUNC, encode_, rfm9x_factory
from sb_hmac import hmac_sha1


def light_sleep(seconds):
    alarm.light_sleep_until_alarms(
        alarm.time.TimeAlarm(monotonic_time=(time.monotonic() + seconds)))

def run(a1, tx_interval_s=5.0):
    # Initialize and run in remote sensor hardware configuration (LoRa TX)

    # Use GPIO outs to mark progress of run() for power analyzer logic inputs
    DIO = digitalio.DigitalInOut
    a0, a2, a3 = DIO(A0), DIO(A2), DIO(A3)   # a1 comes from code.py
    a0.switch_to_output(value=True)
    a2.switch_to_output(value=True)
    a3.switch_to_output(value=False)

    # Configure I2C sensors first to allow warm-up time before measurements
    i2c = STEMMA_I2C()
    mcp98 = MCP9808(i2c)             # temperature sensor
    max17 = MAX17048(i2c)            # battery fuel gauge
    # -----
    # TODO: `mcp98.resolution = 1`   # this sets sample time to 65ms
    # -----
    ts = time.monotonic() + 0.065    # schedule the temperature sampling time
    a3.value = True

    # Configure LoRa radio
    cs, rst = DIO(D10), DIO(D9)
    rfm95 = rfm9x_factory(SPI(), cs, rst)
    a1.value = False

    # Get truncated Unix timestamp from RTC to use as message sequence number
    tstamp = time.time() & 0xffffffff

    # Wait until a full temperature sensor sample period has elapsed
    pre_sample_delay = max(0, ts - time.monotonic())
    light_sleep(pre_sample_delay)
    a2.value = False

    # Check sensors, encode message with (timestamp, volts, temperature)
    v = max17.cell_voltage
    f = (mcp98.temperature * 9/5) + 32  # °C -> °F
    msg = encode_(tstamp, v, f)         # pack (uint32, float, float) as bytes
    a3.value = False

    # Full packet = message + truncated HMAC of message (modeled on TOTP)
    msg += hmac_sha1(HMAC_KEY, msg)[:HMAC_TRUNC]
    a1.value = True

    # Send packet on LoRa radio twice for better reliability
    sys.stdout.write('%08x, %.2f, %.1f\n' % (tstamp, v, f))
    rfm95.send(msg)
    a2.value = True
    rfm95.send(msg)
    a3.value = True

    # Put peripherals in low power mode
    rfm95.sleep()
    max17.hibernate()

    # Mark end of run() for the power analyzer's logic inputs
    a0.value, a1.value, a2.value, a3.value = False, False, False, False

    # Begin deep sleep
    alarm.exit_and_deep_sleep_until_alarms(
        alarm.time.TimeAlarm(monotonic_time=time.monotonic() + tx_interval_s))
