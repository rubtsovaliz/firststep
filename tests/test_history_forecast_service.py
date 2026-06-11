"""Tests for history forecast loading."""

from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from backend.app.core.config import Settings
from backend.app.services.ensemble_forecast_service import HISTORY_ENSEMBLE_PAST_DAYS
from backend.app.services.forecast_service import (
    HISTORY_SINGLE_PAST_DAYS,
    EnsembleModelTempResult,
    ForecastLookupKey,
    ForecastLookupResult,
)
from backend.app.services.history_forecast_store import persist_history_forecasts
from backend.app.services.history_forecast_service import HistoryForecastService
from backend.app.services.snapshot_service import SnapshotService


def _recent_date() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def _old_date() -> str:
    return (date.today() - timedelta(days=30)).isoformat()


class TestHistoryForecastService(unittest.TestCase):
    def setUp(self) -> None:
        self.events_dir = Path(self._testMethodName) / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.settings = Settings(events_snapshot_dir=self.events_dir)
        self.snapshots = SnapshotService(self.settings)

    def tearDown(self) -> None:
        import shutil

        root = Path(self._testMethodName)
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)

    def _write_event(self, *, storage_key: str, city_slug: str, event_date: str) -> None:
        record = {
            "storage_key": storage_key,
            "city_slug": city_slug,
            "date": event_date,
            "event_title": f"{city_slug} {event_date}",
            "temperature_metric": "high",
            "unit": "C",
            "extensions": {"winning_bucket": {"winning_bucket": "20C"}},
        }
        (self.events_dir / f"{storage_key}.json").write_text(
            json.dumps(record),
            encoding="utf-8",
        )

    def test_fetch_and_persist_uses_configured_models(self) -> None:
        recent = _recent_date()
        storage_key = f"chicago_{recent}_high"
        self._write_event(storage_key=storage_key, city_slug="chicago", event_date=recent)

        forecast_service = MagicMock()
        ensemble_service = MagicMock()
        single = ForecastLookupResult(
            city_slug="chicago",
            date=recent,
            metric="high",
            model="gfs_seamless",
            requested_model="gfs_seamless",
            unit="C",
            temp=21.5,
        )
        ensemble = ForecastLookupResult(
            city_slug="chicago",
            date=recent,
            metric="high",
            model="ncep_gefs_seamless+ecmwf_ifs025_ensemble",
            requested_model="ncep_gefs_seamless+ecmwf_ifs025_ensemble",
            unit="C",
            temp=21.0,
        )
        forecast_service.resolve_history_batch.return_value = [single]
        ensemble_service.resolve_history_batch.return_value = [ensemble]

        service = HistoryForecastService(
            self.snapshots,
            forecast_service,
            ensemble_service,
        )
        results = service.fetch_and_persist([storage_key])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].forecasts_cached)
        self.assertEqual(results[0].single_model.model, "gfs_seamless")
        forecast_service.resolve_history_batch.assert_called_once()
        ensemble_service.resolve_history_batch.assert_called_once()
        forecast_service.client.fetch_archive_daily_temperature.assert_not_called()

    def test_batches_multiple_events_per_city(self) -> None:
        recent = _recent_date()
        keys = [
            f"chicago_{recent}_high",
            f"chicago_{(date.today() - timedelta(days=2)).isoformat()}_high",
        ]
        for key in keys:
            event_date = key.split("_")[1]
            self._write_event(storage_key=key, city_slug="chicago", event_date=event_date)

        forecast_service = MagicMock()
        ensemble_service = MagicMock()
        forecast_service.resolve_history_batch.return_value = [
            ForecastLookupResult(
                city_slug="chicago",
                date=key.split("_")[1],
                metric="high",
                model="gfs_seamless",
                temp=20.0,
                unit="C",
            )
            for key in keys
        ]
        ensemble_service.resolve_history_batch.return_value = [
            ForecastLookupResult(
                city_slug="chicago",
                date=key.split("_")[1],
                metric="high",
                model="ncep_gefs_seamless",
                temp=19.5,
                unit="C",
            )
            for key in keys
        ]

        service = HistoryForecastService(
            self.snapshots,
            forecast_service,
            ensemble_service,
        )
        service.fetch_and_persist(keys)

        self.assertEqual(forecast_service.resolve_history_batch.call_count, 1)
        batch_arg = forecast_service.resolve_history_batch.call_args.args[0]
        self.assertEqual(len(batch_arg), 2)

    def test_refetches_ensemble_when_cached_single_ok_but_ensemble_failed(self) -> None:
        recent = _recent_date()
        storage_key = f"ankara_{recent}_high"
        self._write_event(storage_key=storage_key, city_slug="ankara", event_date=recent)

        forecast_service = MagicMock()
        ensemble_service = MagicMock()
        ensemble = ForecastLookupResult(
            city_slug="ankara",
            date=recent,
            metric="high",
            model="ecmwf_ifs025_ensemble+ncep_gefs_seamless",
            requested_model="ecmwf_ifs025_ensemble+ncep_gefs_seamless",
            unit="C",
            temp=24.2,
            models_temps=[],
        )
        ensemble_service.resolve_history_batch.return_value = [ensemble]

        service = HistoryForecastService(
            self.snapshots,
            forecast_service,
            ensemble_service,
        )
        persist_history_forecasts(
            self.snapshots,
            storage_key,
            single=ForecastLookupResult(
                city_slug="ankara",
                date=recent,
                metric="high",
                model="ecmwf_ifs",
                requested_model="ecmwf_ifs",
                unit="C",
                temp=25.0,
            ),
            ensemble=ForecastLookupResult(
                city_slug="ankara",
                date=recent,
                metric="high",
                model="ecmwf_ifs025_ensemble+ncep_gefs_seamless",
                requested_model="ecmwf_ifs025_ensemble+ncep_gefs_seamless",
                error="forecast_unavailable",
                models_temps=[],
            ),
        )

        results = service.fetch_and_persist([storage_key])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].ensemble.temp, 24.2)
        forecast_service.resolve_history_batch.assert_not_called()
        ensemble_service.resolve_history_batch.assert_called_once()

    def test_persists_ensemble_when_single_missing_for_old_date(self) -> None:
        old = _old_date()
        storage_key = f"ankara_{old}_high"
        self._write_event(storage_key=storage_key, city_slug="ankara", event_date=old)

        forecast_service = MagicMock()
        ensemble_service = MagicMock()
        forecast_service.resolve_history_batch.return_value = [
            ForecastLookupResult(
                city_slug="ankara",
                date=old,
                metric="high",
                model="ecmwf_ifs",
                error="forecast_unavailable",
            )
        ]
        ensemble_service.resolve_history_batch.return_value = [
            ForecastLookupResult(
                city_slug="ankara",
                date=old,
                metric="high",
                model="ecmwf_ifs025_ensemble+ncep_gefs_seamless",
                unit="C",
                temp=6.2,
                models_temps=[
                    EnsembleModelTempResult(model="ecmwf_ifs025_ensemble", temp=6.2),
                    EnsembleModelTempResult(model="ncep_gefs_seamless", temp=6.1),
                ],
            )
        ]

        service = HistoryForecastService(
            self.snapshots,
            forecast_service,
            ensemble_service,
        )
        results = service.fetch_and_persist([storage_key])

        self.assertTrue(results[0].forecasts_cached)
        self.assertIsNone(results[0].single_model.temp)
        self.assertEqual(results[0].ensemble.temp, 6.2)
        saved = json.loads((self.events_dir / f"{storage_key}.json").read_text(encoding="utf-8"))
        self.assertIn("history_forecasts", saved["extensions"])


class TestHistoryForecastWindows(unittest.TestCase):
    def test_history_window_constants(self) -> None:
        self.assertEqual(HISTORY_SINGLE_PAST_DAYS, 92)
        self.assertEqual(HISTORY_ENSEMBLE_PAST_DAYS, 92)

    def test_resolve_history_batch_disables_archive(self) -> None:
        from unittest.mock import MagicMock, patch

        from backend.app.services.forecast_service import ForecastService

        service = ForecastService(client=MagicMock())
        items = [
            ForecastLookupKey(city_slug="chicago", date="2026-06-01", metric="high"),
        ]
        with patch.object(
            ForecastService,
            "resolve_batch",
            return_value=[],
        ) as resolve_batch:
            service.resolve_history_batch(items)
        resolve_batch.assert_called_once_with(
            items,
            past_days_cap=HISTORY_SINGLE_PAST_DAYS,
            allow_archive_fallback=False,
        )


if __name__ == "__main__":
    unittest.main()
