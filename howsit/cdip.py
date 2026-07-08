"""
CDIP nearshore buoy wave readings via THREDDS OPeNDAP (plain-text ascii
access — no netCDF library required).

The low-level OPeNDAP mechanics here (_dds_dim_size, _parse_opendap_ascii,
_cdip_fill) are ported unchanged from partiwave/pipeline/fetch.py's
fetch_cdip(). fetch_cdip_window() itself is new: partiwave's version fetches
only the single latest reading (right for "current conditions"); this fetches
a time window of recent readings so a caller can align multiple readings per
day against another source's snapshots (e.g. Surfline's 5 daily readings).
"""

import re
from datetime import datetime, timezone

from ._http import http_get

CDIP_BASE = "https://thredds.cdip.ucsd.edu/thredds/dodsC/cdip/realtime"
CDIP_FILL_VALUE = -999.99
M_TO_FT = 3.28084

_DIM_RE_TEMPLATE = r"{name}\[{name}\s*=\s*(\d+)\]"


def _dds_dim_size(dds_text: str, dim_name: str):
    match = re.search(_DIM_RE_TEMPLATE.format(name=re.escape(dim_name)), dds_text)
    return int(match.group(1)) if match else None


def _parse_opendap_ascii(body: str) -> dict:
    """Parse an OPeNDAP .ascii response into {variable_name: [values]}."""
    sep = "---------------------------------------------"
    tail = body.split(sep, 1)[1] if sep in body else body
    blocks = [b.strip() for b in tail.strip().split("\n\n") if b.strip()]
    result = {}
    for block in blocks:
        lines = block.splitlines()
        header_match = re.match(r"(\w+)\[\d+\]", lines[0].strip())
        if not header_match or len(lines) < 2:
            continue
        name = header_match.group(1)
        raw_values = lines[1].strip()
        result[name] = [v.strip() for v in raw_values.split(",") if v.strip()]
    return result


def _cdip_fill(raw: str):
    value = float(raw)
    return None if value <= (CDIP_FILL_VALUE + 1) else value


def fetch_cdip_window(station_id: str, count: int = 200) -> list[dict]:
    """
    Fetch the most recent `count` wave readings for a CDIP station.

    CDIP realtime buoys typically report on a ~30min cadence, so count=200
    covers roughly 4 days. Counting samples (rather than computing an index
    range from a requested time span) avoids assuming an exact cadence,
    since it varies slightly station to station.

    Returns readings sorted oldest-first, each a dict:
        {'observed_at': iso8601 str (UTC),
         'wave_height_ft': float | None,
         'dominant_period_s': float | None,
         'swell_direction_deg': float | None}

    Raises ValueError if the station has no waveTime dimension (offline) or
    the ascii response has no timestamps.
    """
    dataset = f"{station_id}p1_rt.nc"
    dds = http_get(f"{CDIP_BASE}/{dataset}.dds")

    wave_n = _dds_dim_size(dds, "waveTime")
    if not wave_n:
        raise ValueError(f"CDIP station {station_id}: no waveTime dimension (likely offline)")

    idx_end = wave_n - 1
    idx_start = max(0, idx_end - count + 1)

    ascii_body = http_get(
        f"{CDIP_BASE}/{dataset}.ascii"
        f"?waveHs[{idx_start}:1:{idx_end}],waveTp[{idx_start}:1:{idx_end}],"
        f"waveDp[{idx_start}:1:{idx_end}],waveTime[{idx_start}:1:{idx_end}]"
    )
    values = _parse_opendap_ascii(ascii_body)
    if not values.get("waveTime"):
        raise ValueError(f"CDIP station {station_id}: ascii response had no waveTime values")

    hs_vals = values.get("waveHs", [])
    tp_vals = values.get("waveTp", [])
    dp_vals = values.get("waveDp", [])

    readings = []
    for i, ts_raw in enumerate(values["waveTime"]):
        observed_at = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        hs = _cdip_fill(hs_vals[i]) if i < len(hs_vals) else None
        tp = _cdip_fill(tp_vals[i]) if i < len(tp_vals) else None
        dp = _cdip_fill(dp_vals[i]) if i < len(dp_vals) else None
        readings.append({
            "observed_at": observed_at.isoformat(),
            "wave_height_ft": hs * M_TO_FT if hs is not None else None,
            "dominant_period_s": tp,
            "swell_direction_deg": dp,
        })

    readings.sort(key=lambda r: r["observed_at"])
    return readings
