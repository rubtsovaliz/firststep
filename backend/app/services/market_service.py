"""Query saved weather event snapshots."""

from __future__ import annotations

from connectors.polymarket.market_normalizer import WeatherEvent
from connectors.polymarket.settlement_time import enrich_settlement_fields
from backend.app.services.snapshot_service import SnapshotService


class MarketService:
    """Read normalized and per-event stored data."""

    def __init__(self, snapshot_service: SnapshotService) -> None:
        self.snapshots = snapshot_service

    def list_events(
        self,
        *,
        search: str | None = None,
        active_only: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[WeatherEvent], int]:
        events = self.snapshots.load_active_events()

        if active_only:
            events = [e for e in events if e.active and not e.closed]

        if search:
            q = search.lower().strip()
            events = [
                e
                for e in events
                if q in (e.event_title or "").lower()
                or q in (e.storage_key or "").lower()
                or q in (e.city_slug or "").lower()
                or q in (e.city_name or "").lower()
                or q in (e.date or "").lower()
            ]

        total = len(events)
        page = [self._enrich_from_stored_file(e) for e in events[offset : offset + limit]]
        return page, total

    def _enrich_from_stored_file(self, event: WeatherEvent) -> WeatherEvent:
        """
        Per-event JSON is source of truth after discovery scan.

        Always overlay all_outcomes (current bucket prices) and market_snapshots
        (append-only history; UI uses the last entry for top_*).
        """
        record = self.snapshots.load_event(event.storage_key)
        data = event.model_dump()
        if not record:
            enrich_settlement_fields(data)
            return WeatherEvent.model_validate(data)
        if record.get("all_outcomes") is not None:
            data["all_outcomes"] = record["all_outcomes"]
        if record.get("market_snapshots"):
            data["market_snapshots"] = record["market_snapshots"]
        if record.get("last_refreshed_at"):
            data["last_refreshed_at"] = record["last_refreshed_at"]
        if record.get("settle_at"):
            data["settle_at"] = record["settle_at"]
        raw = record.get("raw_source")
        if isinstance(raw, dict) and raw.get("game_start_time"):
            data.setdefault("raw_source", {})
            if isinstance(data["raw_source"], dict):
                data["raw_source"]["game_start_time"] = raw["game_start_time"]
        enrich_settlement_fields(data)
        return WeatherEvent.model_validate(data)

    def get_event_by_key(self, storage_key: str) -> dict | None:
        """Return per-event JSON file with snapshot history."""
        record = self.snapshots.load_event(storage_key)
        if record is not None:
            return record
        normalized = self.get_normalized_by_key(storage_key)
        if normalized is None:
            return None
        return self._enrich_from_stored_file(normalized).model_dump()

    def get_event_detail(self, storage_key: str) -> dict | None:
        """Full event payload for API detail view."""
        return self.get_event_by_key(storage_key)

    def get_normalized_by_key(self, storage_key: str) -> WeatherEvent | None:
        for event in self.snapshots.load_active_events():
            if event.storage_key == storage_key:
                return event
        return None
