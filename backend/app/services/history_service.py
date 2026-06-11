"""Resolved weather events from per-event snapshot files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings
from backend.app.models.api_models import HistoryCitySummary, HistoryEventSummary
from backend.app.services.history_forecast_store import is_forecasts_cached
from backend.app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)


class HistoryIndexCache:
    def __init__(self) -> None:
        self._events_dir: Path | None = None
        self._file_count: int | None = None
        self._rows: list[HistoryEventSummary] | None = None


_index_cache = HistoryIndexCache()


class HistoryCitiesCache:
    def __init__(self) -> None:
        self._events_dir: Path | None = None
        self._cities: list[HistoryCitySummary] | None = None


_cities_cache = HistoryCitiesCache()


def _history_index_path(events_dir: Path) -> Path:
    return events_dir.parent / "history_index.json"


def _history_cities_path(events_dir: Path) -> Path:
    return events_dir.parent / "history_cities.json"


def _events_file_count(events_dir: Path) -> int:
    try:
        return sum(
            1
            for entry in events_dir.iterdir()
            if entry.is_file() and entry.suffix.lower() == ".json"
        )
    except OSError:
        return -1


def _save_index_to_disk(
    path: Path,
    *,
    file_count: int,
    rows: list[HistoryEventSummary],
) -> None:
    payload = {
        "file_count": file_count,
        "rows": [row.model_dump() for row in rows],
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write history index %s: %s", path, exc)


def _load_index_from_disk(
    path: Path,
    *,
    file_count: int,
) -> list[HistoryEventSummary] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Skip history index file %s: %s", path, exc)
        return None
    if payload.get("file_count") != file_count:
        return None
    rows: list[HistoryEventSummary] = []
    for raw in payload.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        try:
            rows.append(HistoryEventSummary(**raw))
        except (TypeError, ValueError):
            continue
    return rows


def _save_cities_to_disk(
    path: Path,
    *,
    file_count: int,
    cities: list[HistoryCitySummary],
) -> None:
    payload = {
        "file_count": file_count,
        "cities": [city.model_dump() for city in cities],
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write history cities %s: %s", path, exc)


def _load_cities_from_disk(path: Path) -> list[HistoryCitySummary] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Skip history cities file %s: %s", path, exc)
        return None
    cities: list[HistoryCitySummary] = []
    for raw in payload.get("cities") or []:
        if not isinstance(raw, dict):
            continue
        try:
            cities.append(HistoryCitySummary(**raw))
        except (TypeError, ValueError):
            continue
    return cities


def _aggregate_cities(rows: list[HistoryEventSummary]) -> list[HistoryCitySummary]:
    by_city: dict[str, list[HistoryEventSummary]] = {}
    for row in rows:
        by_city.setdefault(row.city_slug, []).append(row)

    cities: list[HistoryCitySummary] = []
    for slug, city_rows in by_city.items():
        cities.append(
            HistoryCitySummary(
                city_slug=slug,
                event_count=len(city_rows),
                forecasts_cached_count=sum(1 for row in city_rows if row.forecasts_cached),
            )
        )
    cities.sort(key=lambda city: city.city_slug)
    return cities


def _filter_cities(
    cities: list[HistoryCitySummary],
    *,
    search: str | None = None,
) -> list[HistoryCitySummary]:
    if not search:
        return cities
    q = search.lower().strip()
    return [city for city in cities if q in city.city_slug.lower()]


def _store_cities_cache(
    events_dir: Path,
    cities: list[HistoryCitySummary],
    *,
    file_count: int | None = None,
) -> None:
    global _cities_cache
    _cities_cache._events_dir = events_dir
    _cities_cache._cities = cities
    resolved_count = file_count if file_count is not None else _index_cache._file_count
    if resolved_count is not None:
        _save_cities_to_disk(
            _history_cities_path(events_dir),
            file_count=resolved_count,
            cities=cities,
        )


def invalidate_history_index() -> None:
    """Drop cached history indexes after new event snapshots are written."""
    global _index_cache, _cities_cache
    events_dir = _index_cache._events_dir or _cities_cache._events_dir
    _index_cache = HistoryIndexCache()
    _cities_cache = HistoryCitiesCache()
    if events_dir is not None:
        for path in (_history_index_path(events_dir), _history_cities_path(events_dir)):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.debug("Failed to remove history cache %s: %s", path, exc)


def mark_history_forecasts_cached(storage_key: str, *, city_slug: str | None = None) -> None:
    """Keep city counts accurate after persisting forecasts without a full rescan."""
    global _index_cache, _cities_cache

    if _index_cache._rows is not None:
        updated = False
        rows: list[HistoryEventSummary] = []
        for row in _index_cache._rows:
            if row.storage_key == storage_key:
                rows.append(row.model_copy(update={"forecasts_cached": True}))
                city_slug = city_slug or row.city_slug
                updated = True
            else:
                rows.append(row)

        if updated:
            _index_cache._rows = rows
            if _index_cache._events_dir is not None and _index_cache._file_count is not None:
                _save_index_to_disk(
                    _history_index_path(_index_cache._events_dir),
                    file_count=_index_cache._file_count,
                    rows=rows,
                )

    if _cities_cache._cities is not None and city_slug:
        updated_cities = False
        cities: list[HistoryCitySummary] = []
        for city in _cities_cache._cities:
            if city.city_slug == city_slug:
                cities.append(
                    city.model_copy(
                        update={"forecasts_cached_count": city.forecasts_cached_count + 1}
                    )
                )
                updated_cities = True
            else:
                cities.append(city)
        if updated_cities:
            _cities_cache._cities = cities
            if _cities_cache._events_dir is not None:
                _store_cities_cache(_cities_cache._events_dir, cities)


def _format_outcome_bucket(outcome: dict[str, Any], unit: str | None) -> str:
    low = outcome.get("bucket_low")
    high = outcome.get("bucket_high")
    u = unit or outcome.get("unit") or ""
    if low == -999 and high is not None:
        return f"<={high}{u}"
    if high == 999 and low is not None:
        return f">={low}{u}"
    if low is not None and high is not None:
        if low == high:
            return f"{low}{u}"
        return f"{low}-{high}{u}"
    return outcome.get("question") or "—"


def extract_winning_bucket(record: dict[str, Any]) -> str | None:
    extensions = record.get("extensions") or {}
    winning = extensions.get("winning_bucket")
    if isinstance(winning, dict):
        for key in ("winning_bucket", "resolved_value"):
            value = winning.get(key)
            if value:
                return str(value)

    unit = record.get("unit")
    for outcome in record.get("all_outcomes") or []:
        yes_price = outcome.get("yes_price")
        if yes_price is not None and yes_price >= 0.99:
            return _format_outcome_bucket(outcome, unit)

    snapshots = record.get("market_snapshots") or []
    if snapshots:
        last = snapshots[-1]
        top_price = last.get("top_price")
        top_bucket = last.get("top_bucket")
        if top_price is not None and top_price >= 0.99 and top_bucket:
            return str(top_bucket)

    return None


def resolve_metric(record: dict[str, Any]) -> str | None:
    metric = record.get("temperature_metric")
    if metric in ("high", "low"):
        return metric
    market_type = record.get("market_type")
    if market_type == "max_temperature":
        return "high"
    if market_type == "min_temperature":
        return "low"
    storage_key = record.get("storage_key") or ""
    if storage_key.endswith("_high"):
        return "high"
    if storage_key.endswith("_low"):
        return "low"
    return None


def is_history_event(record: dict[str, Any]) -> bool:
    if resolve_metric(record) is None:
        return False
    return extract_winning_bucket(record) is not None


class HistoryService:
    """List resolved events stored under data/snapshots/events/."""

    def __init__(
        self,
        snapshot_service: SnapshotService,
        *,
        forecast_enricher: Any | None = None,
    ) -> None:
        self.snapshots = snapshot_service
        self._forecast_enricher = forecast_enricher

    def _events_dir(self) -> Path:
        return self.snapshots.settings.events_snapshot_dir

    def _load_index(self) -> list[HistoryEventSummary]:
        events_dir = self._events_dir()

        global _index_cache
        if _index_cache._rows is not None and _index_cache._events_dir == events_dir:
            return _index_cache._rows

        file_count = _events_file_count(events_dir)
        if file_count < 0:
            return []

        index_path = _history_index_path(events_dir)
        rows = _load_index_from_disk(index_path, file_count=file_count)
        if rows is None:
            rows = self._build_index_rows(events_dir)
            rows.sort(key=lambda row: (row.date, row.city_slug, row.metric), reverse=True)
            _save_index_to_disk(index_path, file_count=file_count, rows=rows)

        _index_cache = HistoryIndexCache()
        _index_cache._events_dir = events_dir
        _index_cache._file_count = file_count
        _index_cache._rows = rows
        return rows

    def _build_index_rows(self, events_dir: Path) -> list[HistoryEventSummary]:
        rows: list[HistoryEventSummary] = []
        for path in events_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Skip history file %s: %s", path.name, exc)
                continue
            if not is_history_event(record):
                continue
            metric = resolve_metric(record)
            win = extract_winning_bucket(record)
            if metric is None or win is None:
                continue
            rows.append(
                HistoryEventSummary(
                    storage_key=str(record.get("storage_key") or path.stem),
                    date=str(record.get("date") or ""),
                    event_title=str(record.get("event_title") or ""),
                    city_slug=str(record.get("city_slug") or ""),
                    metric=metric,
                    win=win,
                    unit=record.get("unit"),
                    forecasts_cached=is_forecasts_cached(record),
                )
            )
        return rows

    def _filter_rows(
        self,
        rows: list[HistoryEventSummary],
        *,
        search: str | None = None,
        city_slug: str | None = None,
    ) -> list[HistoryEventSummary]:
        filtered = rows
        if city_slug:
            slug = city_slug.strip().lower()
            filtered = [row for row in filtered if row.city_slug == slug]
        if search:
            q = search.lower().strip()
            filtered = [
                row
                for row in filtered
                if q in row.event_title.lower()
                or q in row.storage_key.lower()
                or q in row.city_slug.lower()
                or q in row.date.lower()
                or q in row.win.lower()
            ]
        return filtered

    def list_cities(
        self,
        *,
        search: str | None = None,
    ) -> list[HistoryCitySummary]:
        events_dir = self._events_dir()
        global _cities_cache

        if _cities_cache._cities is not None and _cities_cache._events_dir == events_dir:
            return _filter_cities(_cities_cache._cities, search=search)

        cities = _load_cities_from_disk(_history_cities_path(events_dir))
        if cities is not None:
            _cities_cache._events_dir = events_dir
            _cities_cache._cities = cities
            return _filter_cities(cities, search=search)

        rows = self._load_index()
        cities = _aggregate_cities(rows)
        _store_cities_cache(events_dir, cities)
        return _filter_cities(cities, search=search)

    def list_history(
        self,
        *,
        search: str | None = None,
        city_slug: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[HistoryEventSummary], int]:
        rows = self._filter_rows(
            self._load_index(),
            search=search,
            city_slug=city_slug,
        )
        total = len(rows)
        page = rows[offset : offset + limit]
        if self._forecast_enricher is not None:
            page = [self._forecast_enricher.enrich_event(row) for row in page]
        return page, total


def build_history_service(settings: Settings | None = None) -> HistoryService:
    from backend.app.core.config import get_settings

    resolved = settings or get_settings()
    return HistoryService(SnapshotService(resolved))
