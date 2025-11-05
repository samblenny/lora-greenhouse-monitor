# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
from micropython import const
import os
import struct

from adafruit_rfm9x import RFM9x


# -------------------------------------------------------------------------
# Config Options

# Sensor Float Range Limits (for encoding LoRa messages)
BATT_LO = const(3.2)
BATT_HI = const(4.2)
TEMP_LO = const(-128)
TEMP_HI = const(127)

# Defaults for optional settings.toml variables
HMAC_KEY = b'Please set your own HMAC_KEY in settings.toml'
HMAC_TRUNC = 4    # size in bytes of truncated hash (similar to HOTP)

# Read settings.toml
if key := os.getenv("HMAC_KEY"):
    HMAC_KEY = key
if trunc := os.getenv("HMAC_TRUNC"):
    HMAC_TRUNC = trunc
# -------------------------------------------------------------------------


def rfm9x_factory(spi, cs, rst):
    # Configure an RFM9x object for the 900 MHz RFM95W LoRa FeatherWing.
    r = RFM9x(spi, cs, rst, 915.0, baudrate=5_000_000, agc=False, crc=False)
    r.tx_power = 14          # range 5..23 dB, default: 13
    r.spreading_factor = 7   # default: 7
    r.preamble_length = 10   # range uint16, default: 8
    r.destination = 255      # send to all stations (nodes)
    r.node = 255             # receive from all stations (nodes)
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
