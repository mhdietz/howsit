import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from howsit.tides import _date_range, fetch_tide_window

# --- _date_range ------------------------------------------------------------


def test_date_range_default_window():
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    assert _date_range(now, days_before=1, days_after=2) == ("20260721", "20260724")


def test_date_range_custom_window():
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    assert _date_range(now, days_before=3, days_after=5) == ("20260719", "20260727")


# --- fetch_tide_window ----------------------------------------------------


def _fixture_body(predictions):
    return json.dumps({"predictions": predictions})


def _mock_http_get(text):
    return lambda url, *args, **kwargs: text


def test_fetch_tide_window_happy_path():
    predictions = [
        {"t": "2026-07-22 03:15", "v": "0.12", "type": "L"},
        {"t": "2026-07-22 09:30", "v": "4.85", "type": "H"},
        {"t": "2026-07-22 15:45", "v": "0.34", "type": "L"},
    ]
    with patch(
        "howsit.tides.http_get",
        side_effect=_mock_http_get(_fixture_body(predictions)),
    ):
        rows = fetch_tide_window("9410230")

    assert rows == [
        {
            "predicted_at": "2026-07-22T03:15:00+00:00",
            "height_ft": 0.12,
            "state": "rising",
        },
        {
            "predicted_at": "2026-07-22T09:30:00+00:00",
            "height_ft": 4.85,
            "state": "falling",
        },
        {
            "predicted_at": "2026-07-22T15:45:00+00:00",
            "height_ft": 0.34,
            "state": "rising",
        },
    ]


def test_fetch_tide_window_api_error_raises():
    body = json.dumps({"error": {"message": "Station not found"}})
    with patch("howsit.tides.http_get", side_effect=_mock_http_get(body)):
        with pytest.raises(ValueError, match="Station not found"):
            fetch_tide_window("9410230")


def test_fetch_tide_window_empty_predictions_raises():
    with patch(
        "howsit.tides.http_get",
        side_effect=_mock_http_get(_fixture_body([])),
    ):
        with pytest.raises(ValueError, match="no predictions returned"):
            fetch_tide_window("9410230")


def test_fetch_tide_window_url_has_expected_params():
    calls = []

    def side_effect(url, *args, **kwargs):
        calls.append(url)
        return _fixture_body([{"t": "2026-07-22 03:15", "v": "0.12", "type": "L"}])

    with patch("howsit.tides.http_get", side_effect=side_effect):
        fetch_tide_window("9410230")

    assert len(calls) == 1
    assert "station=9410230" in calls[0]
    assert "interval=hilo" in calls[0]
    assert "format=json" in calls[0]
