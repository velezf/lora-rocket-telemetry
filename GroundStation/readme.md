# Ground Station

Mobile APRS digipeater and LoRa telemetry receiver for rocket launches at remote sites outside APRS network coverage.

## Purpose

Most mid-power launch sites are outside range of any APRS digipeater or I-Gate. This ground station solves that by bringing the infrastructure to the field — a self-contained LePotato SBC running Direwolf as a software TNC and digipeater, paired with an RTL-SDR dongle for APRS receive and a Feather M0 for LoRa telemetry.

When the rocket eventually carries an APRS tracker (planned: QRPLabs LightAPRS 2.0), this station will digipeat its packets so they reach the APRS network even from a remote field.

## Hardware

| Component | Purpose |
|-----------|---------|
| Libre Computer LePotato (AML-S905X-CC) | SBC running Linux + Direwolf |
| RTL-SDR V4 dongle | Software-defined radio for APRS RX (144.39 MHz) |
| Adafruit Feather M0 + RFM95 (434 MHz) | LoRa telemetry receiver |
| 12/24V → 5V DC-DC converter | Field power from vehicle or battery |
| Custom blue acrylic enclosure | Houses all hardware, weather-resistant |
| HYS NA-701 dual-band antennas (×2) | VHF/UHF — one for APRS, one for LoRa |
| RJ45 + USB bulkhead connectors | Rear panel I/O without opening the box |
| SPDT toggle switch (SCE/NORM/AUX) | Power routing |

## Software Stack

| Software | Role |
|----------|------|
| Ubuntu Desktop (LePotato) | Base OS |
| [Direwolf](https://github.com/wb2osz/direwolf) | Software TNC + APRS digipeater/I-Gate |
| Xastir | APRS mapping client |
| Node-RED | Telemetry dashboard (flows in `flows.json`) |
| VNC | Remote headless access from laptop |

## Build Sprints

The station was built iteratively across three ~2-week sprints.

### Sprint 1 — Validate APRS baseline

Confirmed APRS TX/RX capability using a Baofeng UV-5R + Android phone (APRSdroid + BTECH APRS-K1 cable) before committing to the SBC build. Verified packets appearing on aprs.fi.

### Sprint 2 — Alpha build (APRS SDR iGate on LePotato)

- Flashed Ubuntu Desktop to LePotato via balenaEtcher
- Built Direwolf from source following the official docs
- Configured `sdr.conf` for RTL-SDR + Direwolf pipeline:
  ```bash
  rtl_fm -f 144.39M - | direwolf -c sdr.conf -r 24000 -D 1 -
  ```
- Installed Xastir for APRS mapping, Node-RED for telemetry dashboard
- Set up VNC for headless remote access
- Added crontab entry to auto-start the SDR pipeline on boot

### Sprint 3 — Project box build + LoRa integration

- Moved everything into the custom blue acrylic enclosure
- Drilled SMA, power, and USB panel penetrations with a stepped drill bit
- Added Feather M0 RFM95 for LoRa receive (soldered uFL connector + stackable headers, powered from LePotato USB)
- Wired SPDT switch for power routing
- Tested end-to-end: LoRa TX from rocket sled → RX on Feather → serial to LePotato → Node-RED dashboard

## Photos

Build photos are in [`Feather9x_RX/Rx_BaseStation/`](../RocketLoRaTelemetry/Feather9x_RX/Rx_BaseStation/).

## Node-RED

`flows.json` contains the Node-RED flow for displaying incoming LoRa telemetry. Import it via the Node-RED UI: **Menu → Import → select file**.

## Future

- Add QRPLabs LightAPRS 2.0 tracker to rocket for in-flight APRS position packets
- Ground station will digipeat those packets to the APRS network
- Evaluate replacing Xastir with PinpointAPRS or YAAC for better map rendering
