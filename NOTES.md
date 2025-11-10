# Notes


## Base Station Notes

Related Products and Learn Guides:
- https://www.adafruit.com/product/292 (i2c/SPI character LCD backpack)
- https://learn.adafruit.com/i2c-spi-lcd-backpack
- https://learn.adafruit.com/esp-now-in-circuitpython/overview
- https://www.adafruit.com/product/1651 (2.8" TFT Touch Shield v2)
- https://learn.adafruit.com/adafruit-2-8-tft-touch-shield-v2
- https://learn.adafruit.com/circuitpython-display-text-library/types-of-labels


Related API Docs:
- https://docs.circuitpython.org/projects/charlcd/en/latest/api.html
https://docs.python.org/3/library/collections.html#namedtuple-factory-function-for-tuples-with-named-fields
- https://docs.circuitpython.org/en/latest/shared-bindings/espnow/


## Sensor Notes

Related Learn Guides:
- https://learn.adafruit.com/radio-featherwing (LoRa FeatherWing)
- https://learn.adafruit.com/adafruit-mcp9808-precision-i2c-temperature-sensor-guide
- https://learn.adafruit.com/adafruit-esp32-s3-feather
- https://learn.adafruit.com/adafruit-feather-rp2350

Related API Docs:
- https://docs.circuitpython.org/projects/max1704x/en/latest/api.html
- https://docs.circuitpython.org/projects/mcp9808/en/latest/
- https://docs.circuitpython.org/projects/rfm9x/en/latest/api.html (LoRa API docs)

To use the RFM95W LoRa FeatherWing, you have to solder wires to route its
RST, CS, and IRQ signals to match the pin capabilities of your Feather board.
The pinout here matches my build for the RP2350 Feather and ESP32-S3 Feather.
If you want to use this code with a different board, check the LoRa
FeatherWing docs for compatibility with your Feather board and adjust the
pinouts as needed.

LoRa FeatherWing Pinout for use with ESP32-S3 Feather and RP2350 Feather:
| Signal | LoRa Silkscreen | S3 Silkscreen | RP2350 SilkScreen |
| ------ | --------------- | ------------- | ----------------- |
|   RST  |        C        |       9       |          9        |
|   CS   |        B        |      10       |         10        |
|   IRQ  |        A        |      11       |         11        |

