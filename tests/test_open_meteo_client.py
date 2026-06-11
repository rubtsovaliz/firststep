"""Tests for Open-Meteo forecast connector."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from connectors.forecast.city_config import CityConfig
from connectors.forecast.open_meteo_client import OpenMeteoClient, OpenMeteoError
from connectors.forecast.schemas import DailyTemperatureForecast


def _chicago() -> CityConfig:
    return CityConfig(
        slug="chicago",
        name="Chicago",
        icao="KORD",
        lat=41.9742,
        lon=-87.9073,
        tz="America/Chicago",
        unit="C",
        models="gfs_seamless",
    )


SAMPLE_RESPONSE = {
    "latitude": 41.97,
    "longitude": -87.91,
    "timezone": "America/Chicago",
    "daily": {
        "time": ["2026-06-06", "2026-06-07", "2026-06-08"],
        "temperature_2m_max": [28.4, 30.1, 27.0],
        "temperature_2m_min": [18.2, 19.5, 17.8],
    },
}


class TestOpenMeteoClient(unittest.TestCase):
    def test_build_params_uses_single_city_model(self) -> None:
        client = OpenMeteoClient()
        params = client.build_params(_chicago(), forecast_days=5)
        self.assertEqual(params["latitude"], 41.9742)
        self.assertEqual(params["longitude"], -87.9073)
        self.assertEqual(params["timezone"], "America/Chicago")
        self.assertEqual(params["models"], "gfs_seamless")
        self.assertEqual(params["forecast_days"], 5)
        self.assertEqual(params["temperature_unit"], "celsius")
        self.assertEqual(params["daily"], "temperature_2m_max,temperature_2m_min")

    def test_build_params_with_date_range(self) -> None:
        client = OpenMeteoClient()
        params = client.build_params(
            _chicago(),
            start_date="2026-06-06",
            end_date="2026-06-08",
        )
        self.assertEqual(params["start_date"], "2026-06-06")
        self.assertEqual(params["end_date"], "2026-06-08")
        self.assertNotIn("forecast_days", params)

    def test_build_forecast_from_map(self) -> None:
        client = OpenMeteoClient()
        day_map = client._data_to_day_map(SAMPLE_RESPONSE)
        result = client._build_forecast_from_map(
            _chicago(),
            day_map,
            dates_filter=None,
            forecast_days=3,
            include_raw=False,
            model="gfs_seamless",
            requested_model="gfs_seamless",
            model_fallback=False,
        )
        self.assertEqual(result.city_slug, "chicago")
        self.assertEqual(result.model, "gfs_seamless")
        self.assertEqual(len(result.days), 3)
        self.assertEqual(result.days[0].date, "2026-06-06")
        self.assertEqual(result.days[0].temp_max_c, 28.4)
        self.assertEqual(result.days[0].temp_min_c, 18.2)

    def test_build_forecast_filters_dates(self) -> None:
        client = OpenMeteoClient()
        day_map = client._data_to_day_map(SAMPLE_RESPONSE)
        result = client._build_forecast_from_map(
            _chicago(),
            day_map,
            dates_filter={"2026-06-07"},
            forecast_days=3,
            include_raw=False,
            model="gfs_seamless",
            requested_model="gfs_seamless",
            model_fallback=False,
        )
        self.assertEqual(len(result.days), 1)
        self.assertEqual(result.days[0].date, "2026-06-07")
        self.assertEqual(result.temp_max_for("2026-06-07"), 30.1)

    @patch("connectors.forecast.open_meteo_client.httpx.Client")
    def test_fetch_daily_temperature(self, mock_client_cls: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_RESPONSE
        mock_response.raise_for_status.return_value = None

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = mock_response
        mock_client_cls.return_value = mock_http

        client = OpenMeteoClient()
        result = client.fetch_daily_temperature(_chicago(), forecast_days=3)

        self.assertIsInstance(result, DailyTemperatureForecast)
        mock_http.get.assert_called_once()
        call_kwargs = mock_http.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        self.assertEqual(params["models"], "gfs_seamless")

    @patch("connectors.forecast.open_meteo_client.httpx.Client")
    def test_fetch_raises_on_api_error(self, mock_client_cls: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": True, "reason": "Invalid model"}
        mock_response.raise_for_status.return_value = None

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = mock_response
        mock_client_cls.return_value = mock_http

        client = OpenMeteoClient(max_retries=1)
        with self.assertRaises(OpenMeteoError):
            client.fetch_daily_temperature(_chicago())

    def test_fetch_by_slug_unknown_city(self) -> None:
        client = OpenMeteoClient()
        result = client.fetch_daily_temperature_by_slug("unknown-city-xyz")
        self.assertIsNone(result)

    def test_build_params_fahrenheit_for_us_city(self) -> None:
        city = CityConfig(
            slug="nyc",
            name="New York City",
            icao="KLGA",
            lat=40.7761,
            lon=-73.8727,
            tz="America/New_York",
            unit="F",
            models="gfs_seamless",
        )
        params = OpenMeteoClient().build_params(city)
        self.assertEqual(params["temperature_unit"], "fahrenheit")

    @patch("connectors.forecast.open_meteo_client.httpx.Client")
    def test_fetch_uses_fallback_when_primary_has_no_temps(
        self, mock_client_cls: MagicMock
    ) -> None:
        empty = {
            "daily": {
                "time": ["2026-06-07"],
                "temperature_2m_max": [None],
                "temperature_2m_min": [None],
            }
        }
        filled = {
            "daily": {
                "time": ["2026-06-07"],
                "temperature_2m_max": [24.5],
                "temperature_2m_min": [13.2],
            }
        }

        mock_response_empty = MagicMock()
        mock_response_empty.json.return_value = empty
        mock_response_empty.raise_for_status.return_value = None
        mock_response_filled = MagicMock()
        mock_response_filled.json.return_value = filled
        mock_response_filled.raise_for_status.return_value = None

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.side_effect = [mock_response_empty, mock_response_filled]
        mock_client_cls.return_value = mock_http

        city = CityConfig(
            slug="seoul",
            name="Seoul",
            icao="RKSI",
            lat=37.4691,
            lon=126.4505,
            tz="Asia/Seoul",
            unit="C",
            models="kma_seamless",
            fallback_models="ecmwf_ifs",
        )
        result = OpenMeteoClient().fetch_daily_temperature(
            city, dates=["2026-06-07"]
        )
        self.assertTrue(result.model_fallback)
        self.assertEqual(result.model, "ecmwf_ifs")
        self.assertEqual(result.days[0].temp_max_c, 24.5)
        self.assertEqual(mock_http.get.call_count, 2)

    @patch("connectors.forecast.open_meteo_client.OpenMeteoClient._city_today")
    @patch("connectors.forecast.open_meteo_client.httpx.Client")
    def test_fetch_past_dates_use_fallback_and_archive(
        self, mock_client_cls: MagicMock, mock_today: MagicMock
    ) -> None:
        from datetime import date

        mock_today.return_value = date(2026, 6, 7)

        cma_empty = {
            "daily": {
                "time": ["2026-05-20", "2026-05-21"],
                "temperature_2m_max": [None, None],
                "temperature_2m_min": [None, None],
            }
        }
        ecmwf_filled = {
            "daily": {
                "time": ["2026-05-20", "2026-05-21"],
                "temperature_2m_max": [24.1, 24.9],
                "temperature_2m_min": [16.0, 15.5],
            }
        }
        archive_filled = {
            "daily": {
                "time": ["2026-05-20"],
                "temperature_2m_max": [24.0],
                "temperature_2m_min": [16.9],
            }
        }

        responses = []
        for payload in (cma_empty, ecmwf_filled, archive_filled):
            mock_response = MagicMock()
            mock_response.json.return_value = payload
            mock_response.raise_for_status.return_value = None
            responses.append(mock_response)

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.side_effect = responses
        mock_client_cls.return_value = mock_http

        city = CityConfig(
            slug="zhengzhou",
            name="Zhengzhou",
            icao="ZHCC",
            lat=34.5197,
            lon=113.8410,
            tz="Asia/Shanghai",
            unit="C",
            models="cma_grapes_global",
            fallback_models="ecmwf_ifs",
        )
        result = OpenMeteoClient().fetch_daily_temperature(
            city, dates=["2026-05-20", "2026-05-21"]
        )
        self.assertTrue(result.model_fallback)
        self.assertEqual(result.temp_max_for("2026-05-20"), 24.1)
        self.assertEqual(result.temp_max_for("2026-05-21"), 24.9)

    @patch("connectors.forecast.open_meteo_client.OpenMeteoClient._city_today")
    @patch("connectors.forecast.open_meteo_client.httpx.Client")
    def test_today_date_uses_minimum_forecast_days(
        self, mock_client_cls: MagicMock, mock_today: MagicMock
    ) -> None:
        from datetime import date

        mock_today.return_value = date(2026, 6, 7)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "daily": {
                "time": ["2026-06-06", "2026-06-07"],
                "temperature_2m_max": [36.4, 38.5],
                "temperature_2m_min": [25.0, 26.0],
            }
        }
        mock_response.raise_for_status.return_value = None

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = mock_response
        mock_client_cls.return_value = mock_http

        city = CityConfig(
            slug="lucknow",
            name="Lucknow",
            icao="VILK",
            lat=26.7606,
            lon=80.8893,
            tz="Asia/Kolkata",
            unit="C",
            models="ecmwf_ifs",
        )
        result = OpenMeteoClient().fetch_daily_temperature(
            city, dates=["2026-06-07"]
        )
        self.assertEqual(result.temp_max_for("2026-06-07"), 38.5)
        params = mock_http.get.call_args.kwargs.get("params") or mock_http.get.call_args[1]["params"]
        self.assertGreaterEqual(params["forecast_days"], 2)

    @patch("connectors.forecast.open_meteo_client.httpx.Client")
    def test_fetch_archive_daily_temperature_uses_archive_api(self, mock_client_cls) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "daily": {
                "time": ["2026-06-05"],
                "temperature_2m_max": [22.0],
                "temperature_2m_min": [12.0],
            }
        }
        mock_response.raise_for_status.return_value = None

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = mock_response
        mock_client_cls.return_value = mock_http

        result = OpenMeteoClient().fetch_archive_daily_temperature(
            _chicago(),
            ["2026-06-05"],
        )
        self.assertEqual(result.model, "archive")
        self.assertEqual(result.temp_max_for("2026-06-05"), 22.0)
        called_url = mock_http.get.call_args.args[0]
        self.assertIn("archive-api.open-meteo.com", called_url)


if __name__ == "__main__":
    unittest.main()
