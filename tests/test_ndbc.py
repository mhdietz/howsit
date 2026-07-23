from unittest.mock import patch

import pytest

from howsit.ndbc import fetch_ndbc_window

_HEADER = (
    "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE\n"
    "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft\n"
)


def _row(
    yy="2026", mo="07", dd="22", hh="18", mi="00",
    wdir="220", wspd="5.1", gst="6.2", wvht="1.2", dpd="10.0",
    apd="8.0", mwd="210", pres="1015.0", atmp="18.5", wtmp="17.2",
    dewp="MM", vis="MM", ptdy="MM", tide="MM",
):
    return " ".join([
        yy, mo, dd, hh, mi, wdir, wspd, gst, wvht, dpd,
        apd, mwd, pres, atmp, wtmp, dewp, vis, ptdy, tide,
    ])


def _feed(*rows):
    return _HEADER + "\n".join(rows) + "\n"


def _mock_http_get(text):
    return lambda url, *args, **kwargs: text


# --- happy path -----------------------------------------------------------


def test_fetch_ndbc_window_happy_path_sorted_and_converted():
    rows = [
        _row(hh="18", mi="00"),  # newest
        _row(hh="17", mi="30"),
        _row(hh="17", mi="00"),  # oldest
    ]
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(_feed(*rows))):
        readings = fetch_ndbc_window("46223", count=200)

    assert len(readings) == 3
    assert [r["observed_at"] for r in readings] == sorted(
        r["observed_at"] for r in readings
    )
    oldest = readings[0]
    assert oldest["observed_at"] == "2026-07-22T17:00:00+00:00"
    assert oldest["wave_height_ft"] == pytest.approx(1.2 * 3.28084)
    assert oldest["dominant_period_s"] == 10.0
    assert oldest["swell_direction_deg"] == 210.0
    assert oldest["wind_speed_mph"] == pytest.approx(5.1 * 2.23694)
    assert oldest["wind_direction_deg"] == 220.0
    assert oldest["water_temp_f"] == pytest.approx(17.2 * 9 / 5 + 32)


def test_fetch_ndbc_window_dominant_period_falls_back_to_apd():
    rows = [_row(dpd="MM", apd="7.5")]
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(_feed(*rows))):
        readings = fetch_ndbc_window("46223", count=200)

    assert readings[0]["dominant_period_s"] == 7.5


# --- fill values ------------------------------------------------------------


def test_fetch_ndbc_window_fill_values_become_none_row_kept():
    rows = [_row(wvht="MM", wdir="MM", wspd="MM", wtmp="MM", mwd="MM")]
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(_feed(*rows))):
        readings = fetch_ndbc_window("46223", count=200)

    assert len(readings) == 1
    reading = readings[0]
    assert reading["wave_height_ft"] is None
    assert reading["wind_direction_deg"] is None
    assert reading["wind_speed_mph"] is None
    assert reading["water_temp_f"] is None
    assert reading["swell_direction_deg"] is None


# --- malformed / comment lines ----------------------------------------------


def test_fetch_ndbc_window_skips_malformed_line():
    text = _HEADER + "2026 07 22 16 30 220 5.1\n" + _row() + "\n"
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(text)):
        readings = fetch_ndbc_window("46223", count=200)

    assert len(readings) == 1


def test_fetch_ndbc_window_ignores_comment_lines():
    rows = [_row()]
    text = _feed(*rows)
    assert text.startswith("#")
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(text)):
        readings = fetch_ndbc_window("46223", count=200)

    assert len(readings) == 1


# --- errors -------------------------------------------------------------


def test_fetch_ndbc_window_empty_feed_raises():
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(_HEADER)):
        with pytest.raises(ValueError, match="no data rows"):
            fetch_ndbc_window("46223", count=200)


def test_fetch_ndbc_window_all_rows_malformed_raises():
    text = _HEADER + "2026 07 22 16 30 220 5.1\n"
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(text)):
        with pytest.raises(ValueError, match="no parseable rows"):
            fetch_ndbc_window("46223", count=200)


# --- count limiting -----------------------------------------------------


def test_fetch_ndbc_window_count_limits_to_newest_rows():
    rows = [
        _row(hh="20", mi="00"),  # newest
        _row(hh="19", mi="00"),
        _row(hh="18", mi="00"),
        _row(hh="17", mi="00"),  # oldest
    ]
    with patch("howsit.ndbc.http_get", side_effect=_mock_http_get(_feed(*rows))):
        readings = fetch_ndbc_window("46223", count=2)

    assert len(readings) == 2
    assert [r["observed_at"] for r in readings] == [
        "2026-07-22T19:00:00+00:00",
        "2026-07-22T20:00:00+00:00",
    ]
