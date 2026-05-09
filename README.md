# lora-rocket-telemetry 📡🚀

Amateur radio telemetry system for mid- and high-power model rocketry. Combines a Feather M0 + LoRa rocket sled with a LePotato SBC ground station that doubles as a portable APRS digipeater for remote launch sites. Streams altitude, G-force, and flight state to the ground in real time at 1 Hz — not post-flight, while it's happening.

Forked and substantially rewritten from [N3VEM/RadioRocketV2](https://github.com/N3VEM/RadioRocketV2). Original concept by Vance Martin (N3VEM). Rewritten for the Feather M0 platform by Francisco Velez (KC3ZTQ).

## System Overview

```
[ Rocket: Feather M0 TX sled ]
    BMP390 + ADXL375
    Launch/apogee detection
    1 Hz LoRa telemetry @ 434 MHz
           |
           | LoRa (434 MHz)
           ↓
[ Ground Station: LePotato SBC ]
    Feather M0 RFM95 — LoRa RX
    RTL-SDR — APRS RX / digipeater (144.39 MHz)
    Direwolf software TNC
    Node-RED telemetry dashboard
```

## Repository Structure

| Folder | Contents |
|--------|----------|
| [`RocketLoRaTelemetry/`](RocketLoRaTelemetry/) | Feather M0 TX + RX firmware, build photos |
| [`GroundStation/`](GroundStation/) | LePotato APRS digipeater build + Node-RED flows |

## Hardware

### TX Sled (rocket)
- Adafruit Feather M0 + RFM95 (434 MHz)
- Adafruit BMP390 — barometric altitude
- Adafruit ADXL375 — high-G accelerometer (±200 g)
- LiPo battery

### RX Ground Station
- Libre Computer LePotato SBC
- Adafruit Feather M0 + RFM95 (434 MHz) — LoRa receive
- RTL-SDR V4 dongle — APRS receive / digipeater
- Custom blue acrylic enclosure with panel-mount connectors

## Firmware Features

- **Ground pressure calibration** — 50-sample average at boot for stable altitude reference
- **Launch detection** — 3-axis vector magnitude threshold
- **Apogee detection** — barometric pressure reversal
- **1 Hz real-time telemetry with ACK** — compact packet: altitude, max alt, G-force, peak G, temp, battery, flight state
- **Battery monitoring** — voltage divider on A7 with Good / Low / Charge Now thresholds

## Status

✅ Flight tested — telemetry received successfully on first flight.

🔧 High-power deployment in progress — Apogee Zephyr nose cone e-bay built, NAR Level 1 certified.

APRS integration planned (QRPLabs LightAPRS 2.0 tracker). Ground station digipeater infrastructure is ready.

## License

MIT — see [LICENSE](LICENSE).

## Attribution

Based on [RadioRocketV2](https://github.com/N3VEM/RadioRocketV2) by Vance Martin (N3VEM).
Rewritten for Feather M0 by Francisco Velez (KC3ZTQ).
