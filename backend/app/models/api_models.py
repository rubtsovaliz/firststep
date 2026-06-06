"""API response models."""

from typing import Any

from pydantic import BaseModel, Field

from connectors.polymarket.market_normalizer import WeatherEvent


class HealthResponse(BaseModel):
    status: str = "ok"


class DiscoveryRefreshResponse(BaseModel):
    total_events_fetched: int
    total_weather_events: int = 0
    total_weather_markets: int = 0
    full_scan_events: int = 0
    weather_tag_events: int = 0
    discovery_mode: str = "combined"
    generated_at: str
    raw_snapshot_path: str
    normalized_snapshot_path: str
    per_event_snapshot_dir: str
    per_market_snapshot_dir: str = ""


class DiscoveryStatusResponse(BaseModel):
    last_refresh_at: str | None = None
    total_events_fetched: int = 0
    total_weather_events: int = 0
    total_weather_markets: int = 0
    full_scan_events: int = 0
    weather_tag_events: int = 0
    discovery_mode: str = "never_refreshed"
    raw_snapshot_path: str
    normalized_snapshot_path: str
    per_event_snapshot_dir: str
    per_market_snapshot_dir: str = ""
    status: str = "never_refreshed"


class ActiveEventsSnapshot(BaseModel):
    generated_at: str
    source: str = "gamma_api_combined"
    count: int
    events: list[WeatherEvent]


class MarketsListResponse(BaseModel):
    count: int
    events: list[WeatherEvent] = Field(default_factory=list)
    markets: list[WeatherEvent] = Field(default_factory=list)


class MarketDetailResponse(BaseModel):
    market: dict[str, Any]
