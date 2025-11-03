<!-- SPDX-License-Identifier: MIT -->
<!-- SPDX-FileCopyrightText: Copyright 2025 Sam Blenny -->
# Power Analysis

These are my notes on power consumption for the code running in the sensor
configuration (ESP32-S3).


## Baseline (tag v0.2.0, commit 87ec20c)

This uses 5 second ESP32-S3 deep sleeps between wake cycles. Each wake cycle
transmits two LoRa packets at TX power 8 dB, spreading factor 9, coding rate 5,
and preamble 10, and a 10 byte payload.

Interesting features:

1. Large transient (0.9 A peak) that only appears on the initial boot. This is
   probably for bypass capacitors.

2. Smaller transient (0.7 A peak) in the middle of each boot and wake cycle.
   I'm not sure what causes this. It might have to do with either the LiPo fuel
   gauge chip or the LoRa radio module initializing.

3. Two back-to-back fuzzy-plateau sections lasting about 150 ms each with an
   average power draw of about 130 mA. These are the two LoRa packets.

4. Deep sleep current averages about 2.1 mA, which is absolutely terrible. I
   definitely need to look into this one.


### Entire PPK2 Capture (30 s)

![PPK2 screenshot](baseline/baseline-30s-capture.png)


### Initial Boot Cycle

![PPK2 screenshot](baseline/baseline-boot-cycle.png)


### Deep Sleep After Boot Cycle

![PPK2 screenshot](baseline/baseline-deep-sleep.png)


### Wake Cycle After Deep Sleep

![PPK2 screenshot](baseline/baseline-wake-cycle.png)


### Zoomed View of 0.7 A Peak Transient

![PPK2 screenshot](baseline/baseline-weird-transient.png)


### Zoomed View of LoRa Packet TX

![PPK2 screenshot](baseline/baseline-two-lora-packets.png)


## Switch to RFM9x.sleep() (commit c7d0e89)

This is what the average deep sleep current looks like after I switched from
using `RFM9x.idle()` to `RFM9x.sleep()`. The average current drops to 41 µA,
which is a lot better, but hopefully it can still go lower.

![PPK2 screenshot](rfm9x_sleep.png)


## Use MAX17048.hibernate() before sleep (commit d329866)

Putting the MAX17048 fuel gauge chip into hibernate mode drops another 8 µA off
the average deep sleep current, bringing it down to 33 µA. That's pretty good.


### Average Deep Sleep Current

![PPK2 screenshot](max17048_hibernate/max17048_hibernate_deep_sleep.png)


### Wake Cycle Total Charge

Total charge used for a wake cycle is currently 113.25 mC.

![PPK2 screenshot](max17048_hibernate/max17048_hibernate_wake_cycle.png)


## Add Timing Markers (commit 68f1b43)

This adds gray code timing markers on A0 and A1 so it's possible to see in the
Nordic Power Profiler chart when boot.py, code.py, and the sensor's run()
function are active.

Interesting features:

1. Each wake cycle takes about 1.835 seconds. Of that, about the first 1.346 s
   is overhead that happens before boot.py starts running. The overhead section
   of the wake cycle uses about 66.2 mC of charge. The Python code section,
   including `boot.py` and `code.py` lasts for a total of about 489 ms and uses
   about 49 mC of charge.

2. From the start of `boot.py` to the start of `code.py` takes about 12 ms and
   uses about 733 µC of charge. This might include compile time for `code.py`,
   but I'm not sure about that.

3. From the start of `code.py` to the start of `sensor_mode.run()` takes 99 ms
   and uses 7.54 mC of charge. This might include compile time for
   `sensor_mode.py`.

4. From start to end of `sensor_mode.run()` takes about 371 ms and uses about
   40.6 mC of charge. That includes the charge to transmit two LoRa packets.

### Full Wake Cycle

![PPK2 screenshot](add_timing_markers/add_timing_markers_wake_cycle.png)


### Overhead Section Before boot.py

![PPK2 screenshot](add_timing_markers/add_timing_markers_pre_boot_py.png)


### Entire Code Section with boot.py and code.py

![PPK2 screenshot](add_timing_markers/add_timing_markers_boot_and_code.png)


### Start of boot.py to Start of code.py

![PPK2 screenshot](add_timing_markers/add_timing_markers_boot_py.png)


### Start of code.py to Start of sensor_mode.run()

![PPK2 screenshot](add_timing_markers/add_timing_markers_code_to_sensor_run.png)


### Start to End of sensor_mode.run()

![PPK2 screenshot](add_timing_markers/add_timing_markers_sensor_run.png)
