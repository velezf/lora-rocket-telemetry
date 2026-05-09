# RocketLoRaTelemetry

LoRa telemetry firmware for the Feather M0 rocket sled and ground station. Forked and substantially rewritten from [N3VEM/RadioRocketV2](https://github.com/N3VEM/RadioRocketV2); see repo root LICENSE and attribution headers in each source file.

## Hardware

### TX Sled (rocket)

| Component | Purpose |
|-----------|---------|
| Adafruit Feather M0 + RFM95 (434 MHz) | Microcontroller + LoRa radio |
| Adafruit BMP390 | Barometric pressure / altitude |
| Adafruit ADXL375 | High-G accelerometer (±200 g) |
| LiPo battery | Power |

### RX Ground Station

| Component | Purpose |
|-----------|---------|
| Adafruit Feather M0 + RFM95 (434 MHz) | LoRa receiver |

## Firmware

| Folder | Description |
|--------|-------------|
| [`Feather9x_TX/`](Feather9x_TX/) | Transmitter firmware (rocket sled) |
| [`Feather9x_RX/`](Feather9x_RX/) | Receiver firmware (ground station) |

### Key features

- **Trimmed-mean baseline calibration** — averages pressure readings at startup, discarding outliers, to establish a stable ground-level reference
- **Launch detection** — triggers on sustained high-G acceleration threshold
- **Apogee detection** — triggers on pressure reversal after ascent
- **1 Hz telemetry with ACK** — RX acknowledges each packet; TX retransmits on timeout
- **434 MHz ISM band** — operates under Part 97 (amateur) or Part 15 (unlicensed) depending on power level; see your regional regulations

## Dependencies

Install via Arduino Library Manager:

- `Adafruit BMP3XX Library`
- `Adafruit ADXL375`
- `Adafruit Unified Sensor`
- `RadioHead`
- `ArduinoJson`

## Configuration

Before flashing, edit the top of each `.ino` to set:

- Your callsign (TX beacon identifier)
- LoRa frequency (default: 434.0 MHz)
- Spread factor / bandwidth if you change link parameters

## License

MIT — see [LICENSE](../LICENSE) in the repo root.
