"""
NDBC buoy observations via the realtime2.txt feed (plain-text, no parsing
library required).

Ported from partiwave/pipeline/fetch.py's fetch_ndbc(), which returns only
the single most recent reading with a usable wave height. fetch_ndbc_window()
generalizes that the same way howsit's cdip.py generalized CDIP's fetch: into
a time window of readings, so a caller can align multiple readings per day
against another source's snapshots. Unlike CDIP's OPeNDAP index queries,
NDBC's feed has no server-side windowing — it always returns its full
newest-first rolling buffer in one GET, so `count` is applied client-side.
"""

from datetime import datetime, timezone

from ._http import http_get

NDBC_BASE = "https://www.ndbc.noaa.gov/data/realtime2"
NDBC_FILL = "MM"
M_TO_FT = 3.28084
MS_TO_MPH = 2.23694

# realtime2.txt columns: YY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES
#                        ATMP WTMP DEWP VIS PTDY TIDE
_NDBC_MIN_FIELDS = 15


def _c_to_f(celsius: float) -> float:
    return celsius * 9 / 5 + 32


def fetch_ndbc_window(station_id: str, count: int = 200) -> list[dict]:
    """
    Fetch the most recent `count` observations for an NDBC buoy.

    NDBC realtime2.txt reports on a ~hourly (station-dependent) cadence and
    lists newest-first with no way to request a specific range server-side,
    so `count` simply limits how many of the newest rows are parsed.

    Returns readings sorted oldest-first, each a dict:
        {'observed_at': iso8601 str (UTC),
         'wave_height_ft': float | None,
         'dominant_period_s': float | None,
         'swell_direction_deg': float | None,
         'wind_speed_mph': float | None,
         'wind_direction_deg': float | None,
         'water_temp_f': float | None,
         'raw_payload': str (the untouched source line, for replaying a bad parse)}

    Raises ValueError if the feed has no data rows, or if every row is
    structurally malformed.
    """
    text = http_get(f"{NDBC_BASE}/{station_id}.txt")
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    if not data_lines:
        raise ValueError(f"NDBC station {station_id}: feed returned no data rows")

    readings = []
    for line in data_lines[:count]:
        fields = line.split()
        if len(fields) < _NDBC_MIN_FIELDS:
            continue

        def val(i: int):
            v = fields[i] if i < len(fields) else NDBC_FILL
            return None if v == NDBC_FILL else float(v)

        yy, mo, dy, hh, mi = (int(fields[j]) for j in range(5))
        observed_at = datetime(yy, mo, dy, hh, mi, tzinfo=timezone.utc)
        wvht = val(8)
        dpd = val(9)
        apd = val(10)
        mwd = val(11)
        wdir = val(5)
        wspd = val(6)
        wtmp = val(14)

        readings.append({
            "observed_at": observed_at.isoformat(),
            "wave_height_ft": wvht * M_TO_FT if wvht is not None else None,
            "dominant_period_s": dpd if dpd is not None else apd,
            "swell_direction_deg": mwd,
            "wind_speed_mph": wspd * MS_TO_MPH if wspd is not None else None,
            "wind_direction_deg": wdir,
            "water_temp_f": _c_to_f(wtmp) if wtmp is not None else None,
            "raw_payload": line,
        })

    if not readings:
        raise ValueError(f"NDBC station {station_id}: no parseable rows in feed")

    readings.sort(key=lambda r: r["observed_at"])
    return readings
