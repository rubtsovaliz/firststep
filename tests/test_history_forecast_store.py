"""Tests for persisted history forecasts in event JSON."""

import json
from pathlib import Path

from backend.app.services.forecast_service import ForecastLookupResult
from backend.app.services.history_forecast_store import (
    HISTORY_FORECASTS_EXT_KEY,
    is_forecasts_cached,
    persist_history_forecasts,
    read_history_forecasts,
)
from backend.app.services.snapshot_service import SnapshotService
from backend.app.core.config import Settings


def test_persist_and_read_history_forecasts(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    storage_key = "test-city_2026-06-01_high"
    record = {
        "storage_key": storage_key,
        "city_slug": "test-city",
        "date": "2026-06-01",
        "extensions": {},
    }
    (events_dir / f"{storage_key}.json").write_text(json.dumps(record), encoding="utf-8")

    settings = Settings(
        data_dir=tmp_path,
        snapshot_dir=tmp_path,
        events_snapshot_dir=events_dir,
    )
    snapshots = SnapshotService(settings)

    single = ForecastLookupResult(
        city_slug="test-city",
        date="2026-06-01",
        metric="high",
        model="gfs_seamless",
        temp=25.0,
        unit="C",
    )
    ensemble = ForecastLookupResult(
        city_slug="test-city",
        date="2026-06-01",
        metric="high",
        model="ncep_gefs_seamless",
        temp=24.5,
        unit="C",
        models_temps=[],
    )

    persist_history_forecasts(snapshots, storage_key, single=single, ensemble=ensemble)
    saved = json.loads((events_dir / f"{storage_key}.json").read_text(encoding="utf-8"))

    assert is_forecasts_cached(saved)
    stored = read_history_forecasts(saved)
    assert stored is not None
    assert stored["single"]["temp"] == 25.0
    assert stored["ensemble"]["temp"] == 24.5
    assert HISTORY_FORECASTS_EXT_KEY in saved["extensions"]
