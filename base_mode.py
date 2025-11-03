# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# LoRa Base Station
#
import board
from digitalio import DigitalInOut
import time

from common import HMAC_TRUNC, HMAC_KEY, decode_, rfm9x_factory
from sb_hmac import hmac_sha1


def run():
    # Initialize and run in base station hardware configuration (LoRa RX)
    spi = board.SPI()
    cs = DigitalInOut(board.D10)
    rst = DigitalInOut(board.D9)

    print('Starting LoRa Receiver.')
    time.sleep(0.01)                      # SX127x radio needs 10ms after reset
    rfm95 = rfm9x_factory(spi, cs, rst)   # LoRa radio

    EXPECTED_SIZE = 6 + HMAC_TRUNC        # byte-size of message + MAC
    truncate = HMAC_TRUNC
    key = HMAC_KEY
    prev_seq = None                       # first sequence num can be anything
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
            # CAUTION: first sequence number after boot will always be accepted
            non_monotonic = (prev_seq is not None) and (seq <= prev_seq)
            if non_monotonic or (msg_hash != check_hash):
                continue
            # Making it here means packet is in sequence and authenticated.
            # Print decoded packet then update sequence number.
            print('RX:  rssi=%d, snr=%.1f, %08x, %.2f, %.0f, %s' %
                (rssi, snr, seq, v, f, msg_hash.hex()))
            prev_seq = seq
