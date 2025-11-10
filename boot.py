import board
import digitalio
import supervisor
import usb_hid

usb_hid.disable()

# Toggle A0 to mark start of boot.py for power profiler
a0 = digitalio.DigitalInOut(board.A0)
a0.switch_to_output(value=True)

# Disable status bar to stop the default USB serial escape sequence noise
try:
    supervisor.status_bar.console = False
    supervisor.status_bar.display = False
except Exception:
    pass
