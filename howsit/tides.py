"""
NOAA CO-OPS tide predictions (high/low extrema only).

Ported from partiwave/pipeline/fetch.py's fetch_tide(). Uses interval=hilo
rather than a continuous hourly curve because subordinate stations (e.g.
TWC0419) only support hilo output — using it uniformly for every station
keeps fetch logic source-agnostic. fetch_tide_window() generalizes
partiwave's hardcoded -1/+2 day window into caller-configurable
days_before/days_after, for consistency with fetch_cdip_window() and
fetch_ndbc_window()'s caller-controlled windows.
"""

import json
from datetime import datetime, timedelta, timezone

from ._http import http_get

CO_OPS_BASE = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


def _date_range(now: datetime, days_before: int, days_after: int) -> tuple[str, str]:
    """Return (begin, end) as YYYYMMDD strings around `now`."""
    begin = (now - timedelta(days=days_before)).strftime("%Y%m%d")
    end = (now + timedelta(days=days_after)).strftime("%Y%m%d")
    return begin, end


def fetch_tide_window(station_id: str, days_before: int = 1, days_after: int = 2) -> list[dict]:
    """
    Fetch high/low tide predictions for a CO-OPS station.

    Returns predictions in the range [now - days_before, now + days_after],
    each a dict:
        {'predicted_at': iso8601 str (UTC),
         'height_ft': float,
         'state': 'rising' | 'falling'}

    Raises ValueError if the CO-OPS API returns an error, or no predictions.
    """
    begin, end = _date_range(datetime.now(timezone.utc), days_before, days_after)
    url = (
        f"{CO_OPS_BASE}?product=predictions&application=howsit&station={station_id}"
        f"&datum=MLLW&time_zone=gmt&units=english&interval=hilo&format=json"
        f"&begin_date={begin}&end_date={end}"
    )
    body = http_get(url)
    data = json.loads(body)
    if "error" in data:
        message = data["error"].get("message", "CO-OPS API error")
        raise ValueError(f"CO-OPS station {station_id}: {message}")

    predictions = data.get("predictions", [])
    if not predictions:
        raise ValueError(f"CO-OPS station {station_id}: no predictions returned")

    rows = []
    for p in predictions:
        predicted_at = datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        # Convention: a Low is the start of a rising phase, a High the start
        # of a falling phase — this labels the state *from this point on*.
        state = "rising" if p["type"] == "L" else "falling"
        rows.append({
            "predicted_at": predicted_at.isoformat(),
            "height_ft": float(p["v"]),
            "state": state,
        })
    return rows
