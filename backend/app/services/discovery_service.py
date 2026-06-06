"""Orchestrates combined Gamma discovery and event-level persistence."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from connectors.polymarket.gamma_client import GammaClient
from connectors.polymarket.market_normalizer import (
    WeatherEvent,
    merge_gamma_events,
    normalize_weather_event,
)
from connectors.polymarket.weather_market_filter import is_weather_event
from backend.app.core.config import Settings
from backend.app.models.api_models import DiscoveryRefreshResponse
from backend.app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Application service for weather market discovery."""

    def __init__(self, settings: Settings, snapshot_service: SnapshotService) -> None:
        self.settings = settings
        self.snapshots = snapshot_service
        self.gamma = GammaClient(
            base_url=settings.gamma_base_url,
            timeout_seconds=settings.request_timeout_seconds,
            page_limit=settings.gamma_page_limit,
            max_pages=settings.gamma_max_pages,
        )

    def _fetch_combined_events(
        self,
    ) -> tuple[list[dict], int, int, set[str]]:
        full_scan = self.gamma.fetch_active_events()
        weather_tag = self.gamma.fetch_active_events(tag_slug="weather")
        combined = merge_gamma_events(full_scan, weather_tag)
        tag_ids = {
            str(e.get("id") or e.get("slug"))
            for e in weather_tag
            if e.get("id") or e.get("slug")
        }
        return combined, len(full_scan), len(weather_tag), tag_ids

    def refresh(self) -> DiscoveryRefreshResponse:
        """Combined discovery: full /events scan + tag_slug=weather shortcut."""
        logger.info("Starting combined discovery refresh")
        raw_events, full_count, tag_count, tag_ids = self._fetch_combined_events()
        self.snapshots.save_raw_events(
            raw_events,
            sources={"full_scan": full_count, "weather_tag": tag_count, "combined": len(raw_events)},
        )

        weather_events: list[WeatherEvent] = []
        active_keys: set[str] = set()

        for event in raw_events:
            if not isinstance(event, dict):
                continue

            event_key = str(event.get("id") or event.get("slug") or "")
            from_tag = event_key in tag_ids
            if not from_tag and not is_weather_event(event):
                continue

            normalized = normalize_weather_event(event)
            if normalized is None:
                continue

            source = "weather_tag" if from_tag else "full_scan"
            if from_tag and is_weather_event(event):
                source = "combined"

            if normalized.storage_key in active_keys:
                logger.warning(
                    "Duplicate storage_key skipped (unexpected): %s slug=%s",
                    normalized.storage_key,
                    normalized.event_slug,
                )
                continue
            active_keys.add(normalized.storage_key)
            weather_events.append(normalized)
            self.snapshots.upsert_event(normalized, discovery_source=source)

        self.snapshots.mark_missing_as_inactive(active_keys)
        self.snapshots.save_active_events(weather_events)
        self.snapshots.save_discovery_status(
            total_events=len(raw_events),
            total_weather_events=len(weather_events),
            full_scan_count=full_count,
            weather_tag_count=tag_count,
            status="ok",
        )

        generated_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Discovery complete: combined=%s weather_events=%s",
            len(raw_events),
            len(weather_events),
        )

        return DiscoveryRefreshResponse(
            total_events_fetched=len(raw_events),
            total_weather_events=len(weather_events),
            total_weather_markets=len(weather_events),
            full_scan_events=full_count,
            weather_tag_events=tag_count,
            discovery_mode="combined",
            generated_at=generated_at,
            raw_snapshot_path=str(self.settings.raw_events_path),
            normalized_snapshot_path=str(self.settings.active_events_path),
            per_event_snapshot_dir=str(self.settings.events_snapshot_dir),
            per_market_snapshot_dir=str(self.settings.events_snapshot_dir),
        )
