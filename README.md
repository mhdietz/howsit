# howsit

Public ocean/weather data fetch layer: NDBC, CDIP, NOAA CO-OPS tides. No DB writes, no
Surfline (or any proprietary source), no scoring/research logic — that lives in the
projects that consume this one.

Meant as an intentionally-built, understood, maintained replacement for the parts of
[surfpy](https://github.com/mpiannucci/surfpy) that [surfpy-clean](../surfpy-clean)'s
`evaluation/` and [partiwave](../partiwave) both currently duplicate or depend on.
Grown by need, one function at a time, proven out in `evaluation/` (which has live
Surfline ground truth to validate against) before `partiwave`'s product pipeline
depends on it.

## Status

- `cdip.py` — CDIP nearshore buoy wave readings via THREDDS OPeNDAP (plain-text ascii
  access, no netCDF library). First module; seeded from `partiwave/pipeline/fetch.py`'s
  existing (single-latest-reading) CDIP fetcher, generalized here into a time-windowed
  fetch so callers can align multiple readings per day against another source's snapshots.
  **Live and in production use** as of 2026-07-08 — `surfpy-clean/evaluation/fetch/cdip.py`
  is the first consumer, both locally and via GitHub Actions (installed from this repo's
  `main` branch through `pip install git+https://github.com/mhdietz/howsit.git`).
- `ndbc.py`, `tides.py` — not yet ported. `partiwave/pipeline/fetch.py` has working
  surfpy-free implementations of both; porting is the next step now that `cdip.py` has
  proven the pattern works end-to-end (local dev, real DB writes, and CI all verified).

## Install

From a consuming project's virtualenv, for local development against an editable copy:

```bash
pip install -e /path/to/howsit
```

Or, in a `requirements.txt` / CI context, directly from GitHub:

```
howsit @ git+https://github.com/mhdietz/howsit.git
```

## Design notes

- Stdlib-only (`urllib`, `re`, `datetime`) — no `requests`, no `netCDF4`/`pygrib`. Keep it
  that way; it's a deliberate constraint, not an oversight.
- Every fetch function takes plain parameters (station id, etc.) — never a caller's DB
  row or ORM object. No project-specific coupling belongs in this repo.
