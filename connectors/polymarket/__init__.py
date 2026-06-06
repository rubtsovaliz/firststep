"""Polymarket Gamma API connector."""

from connectors.polymarket.gamma_client import GammaClient
from connectors.polymarket.market_normalizer import (
    WeatherEvent,
    WeatherOutcome,
    merge_gamma_events,
    normalize_weather_event,
    parse_temp_range,
)
from connectors.polymarket.temperature_type import normalize_market_type
from connectors.polymarket.weather_market_filter import is_weather_event, is_weather_market

__all__ = [
    "GammaClient",
    "WeatherEvent",
    "WeatherOutcome",
    "merge_gamma_events",
    "normalize_weather_event",
    "parse_temp_range",
    "normalize_market_type",
    "is_weather_event",
    "is_weather_market",
]
