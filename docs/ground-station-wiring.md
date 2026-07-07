# Ground Station Wiring — Apogee Zephyr (`apogee-gs`, Raspberry Pi 5)

Locked pin map for the Pi 5 ground station peripherals. Physical pin numbers refer to
the 40-pin header; BCM = Broadcom GPIO number. Bench-verified 2026-07-07 (radio RX
confirmed against the live V1 sled; OLED + PiSugar on I²C1).

> This is the authoritative wiring reference. The radio's `CS`/`RST` and the OLED's
> address are deliberately chosen to match the handheld bonnet convention so ground and
> handheld code stay in parity.

## RFM96W LoRa radio — SPI0

| Signal | Radio pin | Pi phys pin | BCM GPIO | Notes |
|--------|-----------|-------------|----------|-------|
| Power  | VIN       | **1**       | 3.3 V    | breakout has no regulator — 3.3 V only |
| Ground | GND       | **6**       | GND      | |
| Clock  | SCK       | **23**      | GPIO 11  | SPI0 SCLK |
| MISO   | MISO      | **21**      | GPIO 9   | SPI0 MISO |
| MOSI   | MOSI      | **19**      | GPIO 10  | SPI0 MOSI |
| Select | CS        | **26**      | GPIO 7 (**CE1**) | `/dev/spidev0.1` |
| Reset  | RST       | **22**      | GPIO 25  | active-low |

- **Unconnected:** `EN`, `G0` (DIO0), `G1`–`G5`. The driver **polls** `RegIrqFlags` — no DIO
  interrupt lines are wired.
- **SPI baudrate: 1 MHz** in code (breakout reliability).
- **CS/RST = CE1 / D25** to match the handheld bonnet convention for code parity.
- Verified: `RegVersion = 0x12` (SX1276); live RX from the V1 sled at 434.0 MHz,
  BW 125 kHz / SF7 / CR 4-5, PHY CRC on, RadioHead 4-byte header stripped.

## OLED — Adafruit 938 (STEMMA QT rev), I²C1

| Signal | OLED pin | Pi phys pin | BCM GPIO | Notes |
|--------|----------|-------------|----------|-------|
| Power  | VIN      | **17**      | 3.3 V    | |
| Ground | GND      | **9**       | GND      | |
| Data   | SDA      | **3**       | GPIO 2   | I²C1 SDA |
| Clock  | SCL      | **5**       | GPIO 3   | I²C1 SCL |

- **I²C address `0x3D`** (not `0x3C` — board silkscreen confirms).
- `Rst` / `CS` / `A0` / `DC` unwired; the board auto-resets on power-up.

## Front-panel LEDs — active-high

Wiring: `GPIO → series resistor → LED anode`, `LED cathode → GND`. Drive the GPIO **HIGH**
to light the LED.

A bring-up sweep (2026-07-07) mapped each GPIO to its **physical** panel position — the
physical order is **not** the GPIO numeric order (LED3–LED6 were cross-wired in the
harness). Corrected map, by physical position (LED1 = leftmost, LED6 = rightmost):

| LED (L→R) | Color | BCM GPIO |
|-----------|-------|----------|
| LED1 | green | GPIO 5   |
| LED2 | green | GPIO 6   |
| LED3 | green | GPIO 13  |
| LED4 | red   | GPIO 26  |
| LED5 | blue  | GPIO 12  |
| LED6 | blue  | GPIO 16  |

Physical layout, left→right: 🟢🟢🟢 🔴 🔵🔵. Firing sequence in physical order:
GPIO `5, 6, 13, 26, 12, 16`.

Bring-up / troubleshoot with [`ground/tools/led_check.py`](../ground/tools/led_check.py),
whose default pin list is in this physical order.

## Shared-bus notes

- **I²C1** also carries the **PiSugar 3 Plus** UPS: `0x57` (battery) + `0x68` (RTC). No
  address conflict with the OLED (`0x3D`).
- **SPI0** carries only the radio, on **CE1**. CE0 (`/dev/spidev0.0`) is free.
