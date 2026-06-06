"""Internal event storage models."""

from typing import Any

from pydantic import BaseModel, Field

from connectors.polymarket.market_normalizer import WeatherEvent, WeatherOutcome
from connectors.polymarket.temperature_type import MarketType, TemperatureMetric


class EventMarketSnapshotEntry(BaseModel):
    """Append-only summary snapshot for one weather event."""

    ts: str
    active: bool
    closed: bool
    end_date: str | None = None
    liquidity: float | None = None
    volume: float | None = None
    outcomes_count: int = 0
    top_bucket: str | None = None
    top_price: float | None = None
    event_title: str | None = None


class StoredEventFile(BaseModel):
    """Per-event JSON file: one city + date + all buckets."""

    storage_key: str
    event_id: str | int | None = None
    event_slug: str | None = None
    event_title: str
    city_slug: str
    city_name: str | None = None
    date: str
    unit: str | None = None
    station: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    closed: bool = False
    end_date: str | None = None
    event_end_date: str | None = None
    liquidity: float | None = None
    volume: float | None = None
    # Temperature-only; None for rain/wind/precipitation until types are extended.
    market_type: MarketType | None = None
    temperature_metric: TemperatureMetric | None = None
    all_outcomes: list[WeatherOutcome] = Field(default_factory=list)
    status: str = "discovered"
    discovery_source: str | None = None
    hours_at_discovery: float | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    last_refreshed_at: str | None = None
    forecast_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    market_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    raw_source: dict[str, Any] = Field(default_factory=dict)
    raw_payload_ref: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)
    legacy: dict[str, Any] | None = None


__all__ = ["WeatherEvent", "WeatherOutcome", "EventMarketSnapshotEntry", "StoredEventFile"]
