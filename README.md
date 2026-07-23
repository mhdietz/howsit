# howsit

Public ocean/weather data fetch layer: NDBC, CDIP, NOAA CO-OPS tides. No DB writes, no
Surfline (or any proprietary source), no scoring/research logic — that lives in the
projects that consume this one.

Meant as an intentionally-built, understood, maintained replacement for the parts of
[surfpy](https://github.com/mpiannucci/surfpy) that [surfpy-clean](../surfpy-clean)'s
`evaluation/` and [partiwave](../partiwave) both currently duplicate or depend on.
All three fetchers (CDIP, NDBC, tides) are now ported and tested; `surfpy-clean/evaluation`
is the first live consumer. Next step: migrate `partiwave/pipeline/fetch.py` off its own
duplicated fetch code onto this repo.

## Status

All three fetchers ported from `partiwave/pipeline/fetch.py`, each generalized from a
single-latest/hardcoded-window fetch into a caller-configurable windowed one, and each with
test coverage in `tests/`.

- `cdip.py` — CDIP nearshore buoy wave readings via THREDDS OPeNDAP (plain-text ascii
  access, no netCDF library). Seeded from `partiwave/pipeline/fetch.py`'s existing
  (single-latest-reading) CDIP fetcher, generalized here into a time-windowed fetch
  (`fetch_cdip_window()`) so callers can align multiple readings per day against another
  source's snapshots. Also fetches water temp (SST) when the station has that sensor,
  nearest-neighbor-joined per reading since SST's sampling cadence doesn't necessarily
  match wave's over a window. Each reading carries `raw_payload` (the untouched ascii
  response) so a bad parse can be replayed without re-fetching. **Live and in production
  use** as of 2026-07-08 — `surfpy-clean/evaluation/fetch/cdip.py` is the first consumer,
  both locally and via GitHub Actions (installed from this repo's `main` branch through
  `pip install git+https://github.com/mhdietz/howsit.git`).
- `ndbc.py` — NDBC buoy observations via the `realtime2.txt` feed. Ported from
  `partiwave/pipeline/fetch.py`'s `fetch_ndbc()`, generalized the same way `cdip.py` was:
  from a single-latest-reading fetch into a time-windowed `fetch_ndbc_window()`, for API
  consistency with `fetch_cdip_window()`.
- `tides.py` — NOAA CO-OPS high/low tide predictions. Ported from
  `partiwave/pipeline/fetch.py`'s `fetch_tide()`, generalized from its hardcoded -1/+2 day
  window into caller-configurable `fetch_tide_window(station_id, days_before, days_after)`.

## Install

From a consuming project's virtualenv, for local development against an editable copy:

```bash
pip install -e /path/to/howsit
```

Or, in a `requirements.txt` / CI context, directly from GitHub:

```
howsit @ git+https://github.com/mhdietz/howsit.git
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

## Design notes

- Stdlib-only (`urllib`, `re`, `datetime`) — no `requests`, no `netCDF4`/`pygrib`. Keep it
  that way; it's a deliberate constraint, not an oversight.
- Every fetch function takes plain parameters (station id, etc.) — never a caller's DB
  row or ORM object. No project-specific coupling belongs in this repo.
