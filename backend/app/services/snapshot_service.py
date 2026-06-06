"""Local JSON snapshot storage — one file per weather event (city + date)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from connectors.polymarket.market_normalizer import WeatherEvent
from backend.app.core.config import Settings
from backend.app.models.api_models import ActiveEventsSnapshot, DiscoveryStatusResponse
from backend.app.models.market_models import EventMarketSnapshotEntry

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_to_resolution(end_date_str: str | None) -> float | None:
    if not end_date_str:
        return None
    try:
        end = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        return round(
            max(0.0, (end - datetime.now(timezone.utc)).total_seconds() / 3600),
            1,
        )
    except Exception:
        return None


class SnapshotService:
    """Read/write aggregate and per-event JSON snapshots."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for path in (
            self.settings.raw_dir,
            self.settings.snapshot_dir,
            self.settings.events_snapshot_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def event_path(self, storage_key: str) -> Path:
        return self.settings.events_snapshot_dir / f"{storage_key}.json"

    def load_event(self, storage_key: str) -> dict[str, Any] | None:
        path = self.event_path(storage_key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load event file %s: %s", path, exc)
            return None

    def save_event(self, record: dict[str, Any]) -> None:
        key = record.get("storage_key", "unknown")
        path = self.event_path(key)
        path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_all_events(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.settings.events_snapshot_dir.glob("*.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return records

    def new_event_file(
        self,
        weather_event: WeatherEvent,
        *,
        ts: str | None = None,
        discovery_source: str = "combined",
    ) -> dict[str, Any]:
        now = ts or _utc_now()
        data = weather_event.model_dump()
        return {
            **data,
            "status": "discovered",
            "discovery_source": discovery_source,
            "hours_at_discovery": _hours_to_resolution(weather_event.event_end_date),
            "first_seen_at": now,
            "last_seen_at": now,
            "last_refreshed_at": now,
            "created_at": now,
            "updated_at": now,
            "forecast_snapshots": [],
            "market_snapshots": [],
            "raw_payload_ref": str(self.settings.raw_events_path),
            "extensions": {},
            "legacy": None,
        }

    def _build_market_snapshot(self, weather_event: WeatherEvent, ts: str) -> dict[str, Any]:
        top = None
        if weather_event.all_outcomes:
            top = max(
                weather_event.all_outcomes,
                key=lambda o: o.yes_price if o.yes_price is not None else -1,
            )
        unit = weather_event.unit or (top.unit if top else "")
        top_bucket = None
        if top:
            if top.bucket_low == -999:
                top_bucket = f"<={top.bucket_high}{unit}"
            elif top.bucket_high == 999:
                top_bucket = f">={top.bucket_low}{unit}"
            else:
                top_bucket = f"{top.bucket_low}-{top.bucket_high}{unit}"

        entry = EventMarketSnapshotEntry(
            ts=ts,
            active=weather_event.active,
            closed=weather_event.closed,
            end_date=weather_event.end_date,
            liquidity=weather_event.liquidity,
            volume=weather_event.volume,
            outcomes_count=len(weather_event.all_outcomes),
            top_bucket=top_bucket,
            top_price=top.yes_price if top else None,
            event_title=weather_event.event_title,
        )
        return entry.model_dump()

    def upsert_event(
        self,
        weather_event: WeatherEvent,
        *,
        discovery_source: str = "combined",
    ) -> dict[str, Any]:
        """Create or update one event file and append market snapshot."""
        now = _utc_now()
        existing = self.load_event(weather_event.storage_key)

        if existing is None:
            record = self.new_event_file(
                weather_event, ts=now, discovery_source=discovery_source
            )
        else:
            record = existing
            record.update(weather_event.model_dump())
            record["last_seen_at"] = now
            record["last_refreshed_at"] = now
            record["updated_at"] = now
            record["discovery_source"] = discovery_source
            record["hours_at_discovery"] = _hours_to_resolution(
                weather_event.event_end_date
            )
            if weather_event.closed:
                record["status"] = "closed"
            elif weather_event.active:
                record["status"] = "discovered"
            else:
                record["status"] = "inactive"

        snapshot = self._build_market_snapshot(weather_event, now)
        record.setdefault("market_snapshots", []).append(snapshot)
        self.save_event(record)
        return record

    def mark_missing_as_inactive(self, active_keys: set[str]) -> None:
        for record in self.load_all_events():
            key = record.get("storage_key", "")
            if key in active_keys:
                continue
            if record.get("status") in ("archived", "closed"):
                continue
            record["status"] = "inactive"
            record["updated_at"] = _utc_now()
            self.save_event(record)

    def save_raw_events(
        self,
        events: list[dict[str, Any]],
        *,
        sources: dict[str, int] | None = None,
    ) -> Path:
        payload = {
            "fetched_at": _utc_now(),
            "count": len(events),
            "discovery_mode": "combined",
            "sources": sources or {},
            "events": events,
        }
        path = self.settings.raw_events_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def save_active_events(self, events: list[WeatherEvent]) -> Path:
        snapshot = ActiveEventsSnapshot(
            generated_at=_utc_now(),
            source="gamma_api_combined",
            count=len(events),
            events=events,
        )
        path = self.settings.active_events_path
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_active_events(self) -> list[WeatherEvent]:
        path = self.settings.active_events_path
        if not path.exists():
            legacy = self.settings.active_markets_path
            if legacy.exists():
                path = legacy
            else:
                return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("events", data.get("markets", []))
            return [WeatherEvent.model_validate(item) for item in raw]
        except Exception as exc:
            logger.warning("Failed to load active events snapshot: %s", exc)
            return []

    def save_discovery_status(
        self,
        *,
        total_events: int,
        total_weather_events: int,
        full_scan_count: int = 0,
        weather_tag_count: int = 0,
        status: str = "ok",
    ) -> Path:
        payload = DiscoveryStatusResponse(
            last_refresh_at=_utc_now(),
            total_events_fetched=total_events,
            total_weather_events=total_weather_events,
            total_weather_markets=total_weather_events,
            full_scan_events=full_scan_count,
            weather_tag_events=weather_tag_count,
            discovery_mode="combined",
            raw_snapshot_path=str(self.settings.raw_events_path),
            normalized_snapshot_path=str(self.settings.active_events_path),
            per_event_snapshot_dir=str(self.settings.events_snapshot_dir),
            per_market_snapshot_dir=str(self.settings.events_snapshot_dir),
            status=status,
        )
        path = self.settings.discovery_status_path
        path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_discovery_status(self) -> DiscoveryStatusResponse:
        path = self.settings.discovery_status_path
        defaults = DiscoveryStatusResponse(
            raw_snapshot_path=str(self.settings.raw_events_path),
            normalized_snapshot_path=str(self.settings.active_events_path),
            per_event_snapshot_dir=str(self.settings.events_snapshot_dir),
            per_market_snapshot_dir=str(self.settings.events_snapshot_dir),
            status="never_refreshed",
        )
        if not path.exists():
            return defaults
        try:
            return DiscoveryStatusResponse.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception:
            return defaults
