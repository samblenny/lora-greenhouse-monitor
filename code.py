# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# See NOTES.md for documentation links and pinout info.
#
import board
import digitalio
import time


# Each time board resets or wakes from deep sleep, select mode from board_id:
if board.board_id == 'adafruit_feather_esp32s3_nopsram':
    # Toggle A1 to mark the start of code.py for the power profiler
    a1 = digitalio.DigitalInOut(board.A1)
    a1.switch_to_output(value=True)

    # Record powerup time for calculating delay until I2C power is stable. The
    # Feather ESP32-S3 board draws a big current spike when I2C_POWER gets
    # turned on by the supervisor prior to loading boot.py on boot or wake from
    # deep sleep. So, when running on a small lipo, we must allow time to
    # recover from a possible brownout on the I2C bus power rail and pullups.
    t0 = time.monotonic()

    # start sensor mode
    import sensor_mode
    sensor_mode.run(a1, t0)

elif board.board_id == 'adafruit_feather_rp2350':
    import base_mode
    base_mode.run()

else:
    raise ValueError("Unexpected board_id. Halting. (check code.py)")
