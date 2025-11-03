import board
import digitalio
import usb_hid

usb_hid.disable()

a1 = digitalio.DigitalInOut(board.A1)
a1.switch_to_output(value=True)
