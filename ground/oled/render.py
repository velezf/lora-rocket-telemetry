"""Pure OLED render — a dashboard panel dict -> up to 4 short lines for a 128x64
SSD1306. Host-tested. Consumes the same view_model panels as the dashboard (AGL
altitude/peak included), so both surfaces agree. The luma shell is Pi-only.
"""


def _ft(v):
    return f"{v}ft" if v is not None else "--"


def oled_lines(panel):
    call = panel.get("callsign") or ""
    fid = panel.get("flight_id")
    flight = fid.split("-")[-1] if fid else ("FLY" if panel.get("flight_open") else "idle")
    return [
        f"SRC:{panel['src']} {call}".rstrip(),
        f"ALT {_ft(panel.get('altitude_ft'))} P{_ft(panel.get('peak_ft'))}",
        f"{panel.get('state', '?').upper()} {flight}",
        f"RSSI {panel.get('rssi', '--')} L{panel.get('seq_loss_pct', 0)}%",
    ]
