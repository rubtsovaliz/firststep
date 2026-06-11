"""Tests for forecast batch service."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from datetime import datetime, timezone

from connectors.forecast.schemas import DailyTemperatureForecast, DailyTemperaturePoint
from backend.app.services.forecast_service import ForecastLookupKey, ForecastService


def _forecast() -> DailyTemperatureForecast:
    return DailyTemperatureForecast(
        city_slug="chicago",
        city_name="Chicago",
        model="gfs_seamless",
        unit="C",
        timezone="America/Chicago",
        latitude=41.97,
        longitude=-87.91,
        icao="KORD",
        fetched_at=datetime.now(timezone.utc),
        forecast_days=1,
        days=[
            DailyTemperaturePoint(date="2026-06-06", temp_max_c=30.9, temp_min_c=19.4),
        ],
    )


class TestForecastService(unittest.TestCase):
    def test_resolve_batch_high_and_low(self) -> None:
        mock_client = MagicMock()
        mock_client.fetch_daily_temperature.return_value = _forecast()

        service = ForecastService(client=mock_client, cache_ttl_seconds=60)
        results = service.resolve_batch(
            [
                ForecastLookupKey("chicago", "2026-06-06", "high"),
                ForecastLookupKey("chicago", "2026-06-06", "low"),
            ]
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].temp, 30.9)
        self.assertEqual(results[0].model, "gfs_seamless")
        self.assertEqual(results[1].temp, 19.4)
        mock_client.fetch_daily_temperature.assert_called_once()

    def test_cache_skips_null_temperature_entries(self) -> None:
        mock_client = MagicMock()
        empty = DailyTemperatureForecast(
            city_slug="lucknow",
            city_name="Lucknow",
            model="ecmwf_ifs",
            unit="C",
            timezone="Asia/Kolkata",
            latitude=26.76,
            longitude=80.88,
            icao="VILK",
            fetched_at=datetime.now(timezone.utc),
            forecast_days=1,
            days=[DailyTemperaturePoint(date="2026-06-07", temp_max_c=None, temp_min_c=None)],
        )
        filled = DailyTemperatureForecast(
            city_slug="lucknow",
            city_name="Lucknow",
            model="ecmwf_ifs",
            unit="C",
            timezone="Asia/Kolkata",
            latitude=26.76,
            longitude=80.88,
            icao="VILK",
            fetched_at=datetime.now(timezone.utc),
            forecast_days=2,
            days=[DailyTemperaturePoint(date="2026-06-07", temp_max_c=38.5, temp_min_c=26.0)],
        )
        mock_client.fetch_daily_temperature.side_effect = [empty, filled]

        service = ForecastService(client=mock_client, cache_ttl_seconds=60)
        first = service.resolve_batch(
            [ForecastLookupKey("lucknow", "2026-06-07", "high")]
        )
        self.assertIsNone(first[0].temp)
        second = service.resolve_batch(
            [ForecastLookupKey("lucknow", "2026-06-07", "high")]
        )
        self.assertEqual(second[0].temp, 38.5)
        self.assertEqual(mock_client.fetch_daily_temperature.call_count, 2)

    def test_unknown_city_returns_error(self) -> None:
        service = ForecastService(client=MagicMock())
        results = service.resolve_batch(
            [ForecastLookupKey("unknown-city-xyz", "2026-06-06", "high")]
        )
        self.assertEqual(results[0].error, "city_not_configured")


if __name__ == "__main__":
    unittest.main()
