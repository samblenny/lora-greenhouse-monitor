# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# See NOTES.md for documentation links and pinout info.
#
import board
import digitalio


# Toggle A1 to mark the start of code.py for the power profiler
a1 = digitalio.DigitalInOut(board.A1)
a1.switch_to_output(value=True)

# Each time board resets or wakes from deep sleep, select mode from board_id:
if board.board_id == 'adafruit_feather_esp32s3_nopsram':
    import sensor_mode
    sensor_mode.run(a1)

elif board.board_id == 'adafruit_feather_rp2350':
    import base_mode
    base_mode.run()

else:
    raise ValueError("Unexpected board_id. Halting. (check code.py)")
