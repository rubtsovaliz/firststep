"""Tests for Open-Meteo ensemble connector."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from connectors.forecast.city_config import CityConfig
from connectors.forecast.open_meteo_ensemble_client import (
    OpenMeteoEnsembleClient,
    history_ensemble_model_id,
)
from connectors.forecast.schemas import DailyTemperatureForecast


def _city() -> CityConfig:
    return CityConfig(
        slug="chicago",
        name="Chicago",
        icao="KORD",
        lat=41.9742,
        lon=-87.9073,
        tz="America/Chicago",
        unit="F",
        models="gfs_seamless",
        daily=("temperature_2m_max", "temperature_2m_min"),
        ensemble_models=(
            "ncep_gefs_seamless",
            "ecmwf_ifs025_ensemble",
            "gem_global_ensemble",
        ),
    )


SAMPLE_ENSEMBLE = {
    "daily": {
        "time": ["2026-06-06", "2026-06-07"],
        "temperature_2m_max": [87.0, 85.0],
        "temperature_2m_min": [65.0, 63.0],
    }
}


class TestOpenMeteoEnsembleClient(unittest.TestCase):
    def test_build_ensemble_params(self) -> None:
        client = OpenMeteoEnsembleClient()
        params = client.build_ensemble_params(
            _city(),
            forecast_days=5,
            model="ecmwf_ifs025_ensemble",
        )
        self.assertEqual(params["models"], "ecmwf_ifs025_ensemble")
        self.assertEqual(params["temperature_unit"], "fahrenheit")
        self.assertEqual(params["forecast_days"], 5)
        self.assertEqual(params["daily"], "temperature_2m_max,temperature_2m_min")
        self.assertEqual(params["timezone"], "America/Chicago")

    @patch("connectors.forecast.open_meteo_client.httpx.Client")
    def test_fetch_daily_temperature_all_models(self, mock_client_cls: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_ENSEMBLE
        mock_response.raise_for_status.return_value = None

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = mock_response
        mock_client_cls.return_value = mock_http

        result = OpenMeteoEnsembleClient().fetch_daily_temperature(_city(), forecast_days=2)

        self.assertIsInstance(result, DailyTemperatureForecast)
        self.assertEqual(result.source, "open-meteo-ensemble")
        self.assertEqual(result.requested_model, "ncep_gefs_seamless+ecmwf_ifs025_ensemble+gem_global_ensemble")
        self.assertEqual(len(result.days[0].by_ensemble_model), 3)
        self.assertEqual(result.days[0].by_ensemble_model[0].model, "ncep_gefs_seamless")
        self.assertEqual(result.days[0].by_ensemble_model[0].temp_max_c, 87.0)
        self.assertEqual(mock_http.get.call_count, 3)
        for call in mock_http.get.call_args_list:
            self.assertIn("ensemble", call.args[0])
            params = call.kwargs.get("params") or call[1]["params"]
            self.assertIn(
                params["models"],
                {
                    "ncep_gefs_seamless",
                    "ecmwf_ifs025_ensemble",
                    "gem_global_ensemble",
                },
            )

    def test_history_ensemble_model_mapping(self) -> None:
        self.assertEqual(
            history_ensemble_model_id("ecmwf_ifs025_ensemble"),
            "ecmwf_ifs025_ensemble_mean",
        )
        self.assertEqual(
            history_ensemble_model_id("ncep_gefs_seamless"),
            "ncep_gefs_ensemble_mean_seamless",
        )


if __name__ == "__main__":
    unittest.main()
