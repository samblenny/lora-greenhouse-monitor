import board
import digitalio
import usb_hid

usb_hid.disable()

# Toggle A0 to mark start of boot.py for power profiler
a0 = digitalio.DigitalInOut(board.A0)
a0.switch_to_output(value=True)
