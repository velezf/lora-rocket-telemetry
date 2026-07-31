#!/usr/bin/env python3
"""Front-panel LED bring-up / troubleshoot for the Apogee Zephyr ground station.

The six front-panel LEDs are active-high (GPIO -> series resistor -> LED anode,
cathode -> GND), so driving a GPIO HIGH lights its LED. Defaults to the locked
LED1..LED6 pin map in physical panel order, left->right (see
docs/ground-station-wiring.md; the physical order is not the GPIO numeric order --
LED3..LED6 are cross-wired). Left->right the panel is green/green/green/red/blue/blue:

    LED1 GPIO5=grn  LED2 GPIO6=grn  LED3 GPIO13=grn
    LED4 GPIO26=red LED5 GPIO12=blu LED6 GPIO16=blu

Usage:
    python3 led_check.py               # test the six default LEDs
    python3 led_check.py 5 6 12        # test only these GPIOs

For each pin it prints the pin, drives it HIGH for 1.0 s then LOW for 0.5 s so you
can match each GPIO to its physical LED, then runs a continuous chase across all
pins until Ctrl-C. Use it to tell apart a wiring fault, reversed polarity, or a
wrong pin assignment.

Pi 5 safe: gpiozero uses the lgpio backend. Runs on the system python3 with
gpiozero preinstalled on Raspberry Pi OS -- no venv or extra packages needed.
"""
import sys
import time

try:
    from gpiozero import LED  # pyright: ignore[reportMissingImports]  # Pi-only dep
except ImportError:
    sys.exit("gpiozero not found -- install with: sudo apt install python3-gpiozero")

# LED1..LED6 in physical panel order (left->right), corrected 2026-07-31 — the original
# bring-up map was fully reversed. Canonical copy: LED_GPIO/lamp_test_order in
# ground/panel/leds.py (host-tested); this is a standalone bring-up tool, kept independent
# of the panel package on purpose so it still works when that package is broken.
DEFAULT_PINS = [16, 12, 26, 13, 6, 5]


def parse_pins(argv):
    if not argv:
        return DEFAULT_PINS
    try:
        return [int(a) for a in argv]
    except ValueError:
        sys.exit(f"invalid GPIO list {argv!r} -- pass integers, e.g. 5 6 12")


def main():
    pins = parse_pins(sys.argv[1:])
    # active_high=True: the LED lights when the GPIO is driven HIGH (our wiring).
    # initial_value=False: start with every LED off.
    leds = [LED(p, active_high=True, initial_value=False) for p in pins]
    try:
        print(f"Testing {len(pins)} LED(s) on GPIO {pins}")
        # 1) individual sweep -- identify which physical LED each GPIO drives
        for i, (pin, led) in enumerate(zip(pins, leds), start=1):
            print(f"  LED{i}: GPIO {pin}  ->  HIGH 1.0s, LOW 0.5s")
            led.on()
            time.sleep(1.0)
            led.off()
            time.sleep(0.5)
        # 2) continuous chase until Ctrl-C
        print("Chase running -- press Ctrl-C to stop.")
        while True:
            for led in leds:
                led.on()
                time.sleep(0.15)
                led.off()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        for led in leds:
            led.off()
            led.close()


if __name__ == "__main__":
    main()
