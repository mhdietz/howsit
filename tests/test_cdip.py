from unittest.mock import patch

import pytest

from howsit.cdip import (
    _cdip_fill,
    _dds_dim_size,
    _parse_opendap_ascii,
    fetch_cdip_window,
)

# --- _dds_dim_size -----------------------------------------------------


def test_dds_dim_size_finds_dimension():
    dds = "Dataset {\n    Float64 waveTime[waveTime = 250];\n} station;"
    assert _dds_dim_size(dds, "waveTime") == 250


def test_dds_dim_size_missing_dimension_returns_none():
    dds = "Dataset {\n    Float64 someOtherDim[someOtherDim = 12];\n} station;"
    assert _dds_dim_size(dds, "waveTime") is None


# --- _parse_opendap_ascii -----------------------------------------------


def _ascii_body(*, with_separator=True):
    sep = "---------------------------------------------\n"
    body = (
        "waveHs[3]\n"
        "1.1, 1.2, 1.3\n"
        "\n"
        "waveTp[3]\n"
        "10.0, 11.0, 12.0\n"
        "\n"
        "waveTime[3]\n"
        "1700000000, 1700001800, 1700003600\n"
    )
    return (sep + body) if with_separator else body


def test_parse_opendap_ascii_standard_response():
    result = _parse_opendap_ascii(_ascii_body())
    assert result["waveHs"] == ["1.1", "1.2", "1.3"]
    assert result["waveTp"] == ["10.0", "11.0", "12.0"]
    assert result["waveTime"] == ["1700000000", "1700001800", "1700003600"]


def test_parse_opendap_ascii_without_separator_still_parses():
    result = _parse_opendap_ascii(_ascii_body(with_separator=False))
    assert result["waveHs"] == ["1.1", "1.2", "1.3"]


def test_parse_opendap_ascii_skips_malformed_block():
    sep = "---------------------------------------------\n"
    body = (
        sep
        + "not a header line, no match\n"
        + "\n"
        + "waveHs[2]\n"
        + "1.0, 2.0\n"
    )
    result = _parse_opendap_ascii(body)
    assert result == {"waveHs": ["1.0", "2.0"]}


# --- _cdip_fill -----------------------------------------------------------


def test_cdip_fill_normal_value():
    assert _cdip_fill("4.02") == 4.02


def test_cdip_fill_fill_value_is_none():
    assert _cdip_fill("-999.99") is None


def test_cdip_fill_boundary_is_none():
    assert _cdip_fill("-998.99") is None


def test_cdip_fill_just_above_boundary_is_not_none():
    assert _cdip_fill("-998.98") == -998.98


# --- fetch_cdip_window ----------------------------------------------------


def _dds_for(wave_n, sst_n=None):
    dims = f"Float64 waveTime[waveTime = {wave_n}];"
    if sst_n is not None:
        dims += f"\n    Float64 sstTime[sstTime = {sst_n}];"
    return f"Dataset {{\n    {dims}\n}} station;"


def _dds_offline():
    return "Dataset {\n    Float64 someOtherDim[someOtherDim = 5];\n} station;"


def _ascii_for(hs, tp, dp, times):
    sep = "---------------------------------------------\n"
    return (
        sep
        + f"waveHs[{len(hs)}]\n{', '.join(hs)}\n\n"
        + f"waveTp[{len(tp)}]\n{', '.join(tp)}\n\n"
        + f"waveDp[{len(dp)}]\n{', '.join(dp)}\n\n"
        + f"waveTime[{len(times)}]\n{', '.join(times)}\n"
    )


def _ascii_empty():
    sep = "---------------------------------------------\n"
    return sep + "waveHs[0]\n\n"


def _sst_ascii_for(temps, times):
    sep = "---------------------------------------------\n"
    return (
        sep
        + f"sstSeaSurfaceTemperature[{len(temps)}]\n{', '.join(temps)}\n\n"
        + f"sstTime[{len(times)}]\n{', '.join(times)}\n"
    )


def _mock_http_get(dds_text, ascii_text, calls=None, sst_ascii_text=None, sst_raises=False):
    def side_effect(url, *args, **kwargs):
        if calls is not None:
            calls.append(url)
        if url.endswith(".dds"):
            return dds_text
        if "sstSeaSurfaceTemperature" in url:
            if sst_raises:
                raise RuntimeError("sst fetch failed")
            return sst_ascii_text
        return ascii_text

    return side_effect


def test_fetch_cdip_window_happy_path():
    times = ["1700003600", "1700000000", "1700001800"]
    ascii_body = _ascii_for(
        hs=["1.0", "2.0", "1.5"],
        tp=["10.0", "11.0", "12.0"],
        dp=["200.0", "210.0", "220.0"],
        times=times,
    )
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(_dds_for(3), ascii_body),
    ):
        readings = fetch_cdip_window("999", count=3)

    assert len(readings) == 3
    assert [r["observed_at"] for r in readings] == sorted(
        r["observed_at"] for r in readings
    )
    oldest = readings[0]
    assert oldest["observed_at"] == "2023-11-14T22:13:20+00:00"
    assert oldest["dominant_period_s"] == 11.0
    assert oldest["swell_direction_deg"] == 210.0
    assert oldest["wave_height_ft"] == pytest.approx(2.0 * 3.28084)
    assert oldest["water_temp_f"] is None  # no sstTime dimension in this fixture's dds
    assert all(r["raw_payload"] == ascii_body for r in readings)


def test_fetch_cdip_window_fill_values_become_none():
    ascii_body = _ascii_for(
        hs=["-999.99"],
        tp=["-999.99"],
        dp=["-999.99"],
        times=["1700000000"],
    )
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(_dds_for(1), ascii_body),
    ):
        readings = fetch_cdip_window("999", count=1)

    assert readings == [
        {
            "observed_at": "2023-11-14T22:13:20+00:00",
            "wave_height_ft": None,
            "dominant_period_s": None,
            "swell_direction_deg": None,
            "water_temp_f": None,
            "raw_payload": ascii_body,
        }
    ]


def test_fetch_cdip_window_offline_station_raises_and_skips_ascii_fetch():
    calls = []
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(_dds_offline(), "unused", calls=calls),
    ):
        with pytest.raises(ValueError, match="no waveTime dimension"):
            fetch_cdip_window("999", count=3)

    assert len(calls) == 1
    assert calls[0].endswith(".dds")


def test_fetch_cdip_window_empty_ascii_raises():
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(_dds_for(3), _ascii_empty()),
    ):
        with pytest.raises(ValueError, match="no waveTime values"):
            fetch_cdip_window("999", count=3)


def test_fetch_cdip_window_index_range_within_history():
    calls = []
    ascii_body = _ascii_for(
        hs=["1.0"], tp=["10.0"], dp=["200.0"], times=["1700000000"]
    )
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(_dds_for(250), ascii_body, calls=calls),
    ):
        fetch_cdip_window("999", count=3)

    ascii_url = calls[1]
    assert "[247:1:249]" in ascii_url


def test_fetch_cdip_window_index_range_clamped_when_history_shorter_than_count():
    calls = []
    ascii_body = _ascii_for(
        hs=["1.0"], tp=["10.0"], dp=["200.0"], times=["1700000000"]
    )
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(_dds_for(5), ascii_body, calls=calls),
    ):
        fetch_cdip_window("999", count=200)

    ascii_url = calls[1]
    assert "[0:1:4]" in ascii_url


# --- fetch_cdip_window: SST (water_temp_f) ---------------------------------


def test_fetch_cdip_window_sst_matching_cadence():
    wave_times = ["1700000000", "1700001800", "1700003600"]
    ascii_body = _ascii_for(
        hs=["1.0", "1.0", "1.0"], tp=["10.0", "10.0", "10.0"],
        dp=["200.0", "200.0", "200.0"], times=wave_times,
    )
    sst_ascii = _sst_ascii_for(temps=["10.0", "12.0", "14.0"], times=wave_times)

    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(
            _dds_for(3, sst_n=3), ascii_body, sst_ascii_text=sst_ascii
        ),
    ):
        readings = fetch_cdip_window("999", count=3)

    assert [r["water_temp_f"] for r in readings] == [
        pytest.approx(10.0 * 9 / 5 + 32),
        pytest.approx(12.0 * 9 / 5 + 32),
        pytest.approx(14.0 * 9 / 5 + 32),
    ]


def test_fetch_cdip_window_sst_mismatched_cadence_uses_nearest_neighbor():
    wave_times = ["1700000000", "1700001800", "1700003600"]
    ascii_body = _ascii_for(
        hs=["1.0", "1.0", "1.0"], tp=["10.0", "10.0", "10.0"],
        dp=["200.0", "200.0", "200.0"], times=wave_times,
    )
    # Sparser SST cadence: one sample at t0, one 900s before t2 (closer to t1 and t2 than to t0).
    sst_ascii = _sst_ascii_for(temps=["10.0", "20.0"], times=["1700000000", "1700002700"])

    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(
            _dds_for(3, sst_n=2), ascii_body, sst_ascii_text=sst_ascii
        ),
    ):
        readings = fetch_cdip_window("999", count=3)

    assert [r["water_temp_f"] for r in readings] == [
        pytest.approx(10.0 * 9 / 5 + 32),  # t0: nearest is sst @ t0 (dist 0)
        pytest.approx(20.0 * 9 / 5 + 32),  # t1: nearest is sst @ t0+2700 (dist 900 vs 1800)
        pytest.approx(20.0 * 9 / 5 + 32),  # t2: nearest is sst @ t0+2700 (dist 900 vs 3600)
    ]


def test_fetch_cdip_window_no_sst_dimension_skips_second_fetch():
    calls = []
    ascii_body = _ascii_for(
        hs=["1.0"], tp=["10.0"], dp=["200.0"], times=["1700000000"]
    )
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(_dds_for(1), ascii_body, calls=calls),
    ):
        readings = fetch_cdip_window("999", count=1)

    assert readings[0]["water_temp_f"] is None
    assert len(calls) == 2  # .dds + wave .ascii only, no sst fetch attempted


def test_fetch_cdip_window_sst_fetch_failure_tolerated():
    ascii_body = _ascii_for(
        hs=["1.0"], tp=["10.0"], dp=["200.0"], times=["1700000000"]
    )
    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(
            _dds_for(1, sst_n=1), ascii_body, sst_raises=True
        ),
    ):
        readings = fetch_cdip_window("999", count=1)

    assert readings[0]["water_temp_f"] is None
    assert readings[0]["wave_height_ft"] == pytest.approx(1.0 * 3.28084)


def test_fetch_cdip_window_sst_fill_value_becomes_none():
    ascii_body = _ascii_for(
        hs=["1.0"], tp=["10.0"], dp=["200.0"], times=["1700000000"]
    )
    sst_ascii = _sst_ascii_for(temps=["-999.99"], times=["1700000000"])

    with patch(
        "howsit.cdip.http_get",
        side_effect=_mock_http_get(
            _dds_for(1, sst_n=1), ascii_body, sst_ascii_text=sst_ascii
        ),
    ):
        readings = fetch_cdip_window("999", count=1)

    assert readings[0]["water_temp_f"] is None
