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


class HistoryForecastModelTemp(BaseModel):
    model: str
    temp: float | None = None
    error: str | None = None


class HistoryForecastSlice(BaseModel):
    city_slug: str
    date: str
    metric: str
    model: str | None = None
    requested_model: str | None = None
    model_fallback: bool = False
    unit: str | None = None
    temp: float | None = None
    error: str | None = None
    models_temps: list[HistoryForecastModelTemp] | None = None


class HistoryEventSummary(BaseModel):
    storage_key: str
    date: str
    event_title: str
    city_slug: str
    metric: str
    win: str
    unit: str | None = None
    forecasts_cached: bool = False
    forecasts_saved_at: str | None = None
    single_model: HistoryForecastSlice | None = None
    ensemble: HistoryForecastSlice | None = None


class HistoryCitySummary(BaseModel):
    city_slug: str
    event_count: int
    forecasts_cached_count: int = 0


class HistoryCitiesResponse(BaseModel):
    count: int
    cities: list[HistoryCitySummary] = Field(default_factory=list)


class HistoryListResponse(BaseModel):
    count: int
    events: list[HistoryEventSummary] = Field(default_factory=list)


class HistoryForecastsFetchRequest(BaseModel):
    storage_keys: list[str] = Field(default_factory=list, max_length=100)


class HistoryForecastsFetchResponse(BaseModel):
    events: list[HistoryEventSummary] = Field(default_factory=list)
