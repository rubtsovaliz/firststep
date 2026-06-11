"""Tests for resolved history indexing."""

import json

from backend.app.core.config import Settings
from backend.app.services.history_service import (
    HistoryIndexCache,
    HistoryService,
    _history_index_path,
    extract_winning_bucket,
    is_history_event,
    mark_history_forecasts_cached,
    resolve_metric,
)
from backend.app.services.snapshot_service import SnapshotService


def test_extract_winning_bucket_from_extensions() -> None:
    record = {
        "extensions": {
            "winning_bucket": {
                "winning_bucket": "19C",
                "resolved_value": "19C",
            }
        },
        "all_outcomes": [],
    }
    assert extract_winning_bucket(record) == "19C"


def test_extract_winning_bucket_from_yes_price() -> None:
    record = {
        "unit": "C",
        "all_outcomes": [
            {"bucket_low": 18, "bucket_high": 18, "yes_price": 0.0},
            {"bucket_low": 19, "bucket_high": 19, "yes_price": 1.0},
        ],
    }
    assert extract_winning_bucket(record) == "19C"


def test_is_history_event_requires_metric_and_win() -> None:
    record = {
        "storage_key": "amsterdam_2026-06-04_high",
        "temperature_metric": "high",
        "extensions": {"winning_bucket": {"winning_bucket": "19C"}},
    }
    assert is_history_event(record) is True
    assert resolve_metric(record) == "high"

    assert is_history_event({"storage_key": "rain-event", "temperature_metric": None}) is False


def _write_history_event(path, *, storage_key: str, city_slug: str, date: str) -> None:
    path.write_text(
        json.dumps(
            {
                "storage_key": storage_key,
                "city_slug": city_slug,
                "date": date,
                "event_title": f"{city_slug} {date}",
                "temperature_metric": "high",
                "unit": "C",
                "extensions": {"winning_bucket": {"winning_bucket": "20C"}},
            }
        ),
        encoding="utf-8",
    )


def test_history_index_uses_disk_cache(tmp_path, monkeypatch) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_history_event(
        events_dir / "alpha_2026-06-01_high.json",
        storage_key="alpha_2026-06-01_high",
        city_slug="alpha",
        date="2026-06-01",
    )
    _write_history_event(
        events_dir / "beta_2026-06-02_high.json",
        storage_key="beta_2026-06-02_high",
        city_slug="beta",
        date="2026-06-02",
    )

    settings = Settings(events_snapshot_dir=events_dir)
    service = HistoryService(SnapshotService(settings))

    import backend.app.services.history_service as history_module

    history_module._index_cache = HistoryIndexCache()

    cities_first = service.list_cities()
    assert [city.city_slug for city in cities_first] == ["alpha", "beta"]
    assert _history_index_path(events_dir).is_file()

    history_module._index_cache = HistoryIndexCache()
    cities_second = service.list_cities()
    assert [city.city_slug for city in cities_second] == ["alpha", "beta"]


def test_mark_history_forecasts_cached_updates_city_counts(tmp_path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_history_event(
        events_dir / "alpha_2026-06-01_high.json",
        storage_key="alpha_2026-06-01_high",
        city_slug="alpha",
        date="2026-06-01",
    )

    settings = Settings(events_snapshot_dir=events_dir)
    service = HistoryService(SnapshotService(settings))

    import backend.app.services.history_service as history_module

    history_module._index_cache = HistoryIndexCache()
    assert service.list_cities()[0].forecasts_cached_count == 0

    mark_history_forecasts_cached("alpha_2026-06-01_high", city_slug="alpha")
    assert service.list_cities()[0].forecasts_cached_count == 1
