"""Fetch Open-Meteo single-model temperatures for dashboard."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

from connectors.forecast.city_config import get_city
from connectors.forecast.open_meteo_client import OpenMeteoClient
from connectors.forecast.schemas import DailyTemperatureForecast

logger = logging.getLogger(__name__)

TemperatureMetric = Literal["high", "low"]
HISTORY_SINGLE_PAST_DAYS = 92


@dataclass(frozen=True)
class ForecastLookupKey:
    city_slug: str
    date: str
    metric: TemperatureMetric


@dataclass
class EnsembleModelTempResult:
    model: str
    temp: float | None = None
    error: str | None = None


@dataclass
class ForecastLookupResult:
    city_slug: str
    date: str
    metric: TemperatureMetric
    model: str | None = None
    requested_model: str | None = None
    model_fallback: bool = False
    unit: str | None = None
    temp: float | None = None
    error: str | None = None
    models_temps: list[EnsembleModelTempResult] | None = None


class ForecastService:
    """Resolve per-event single-model forecast temps via Open-Meteo."""

    def __init__(
        self,
        client: OpenMeteoClient | None = None,
        cache_ttl_seconds: float = 900.0,
    ) -> None:
        self.client = client or OpenMeteoClient()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[str, str], tuple[float, DailyTemperatureForecast]] = {}

    def _cache_get(self, city_slug: str, date: str) -> DailyTemperatureForecast | None:
        key = (city_slug, date)
        entry = self._cache.get(key)
        if not entry:
            return None
        expires_at, forecast = entry
        if time.monotonic() > expires_at:
            self._cache.pop(key, None)
            return None
        if (
            forecast.temp_max_for(date) is None
            and forecast.temp_min_for(date) is None
        ):
            self._cache.pop(key, None)
            return None
        return forecast

    def _cache_put(self, city_slug: str, date: str, forecast: DailyTemperatureForecast) -> None:
        day = forecast.by_date().get(date)
        if day is None or (day.temp_max_c is None and day.temp_min_c is None):
            return
        cached = forecast.model_copy(update={"days": [day]})
        self._cache[(city_slug, date)] = (
            time.monotonic() + self.cache_ttl_seconds,
            cached,
        )

    def _temp_for_metric(
        self,
        forecast: DailyTemperatureForecast,
        date: str,
        metric: TemperatureMetric,
    ) -> float | None:
        if metric == "high":
            return forecast.temp_max_for(date)
        return forecast.temp_min_for(date)

    def _fetch_city_dates(
        self,
        city_slug: str,
        dates: set[str],
        *,
        past_days_cap: int | None = None,
        allow_archive_fallback: bool = True,
    ) -> dict[str, DailyTemperatureForecast | None]:
        city = get_city(city_slug)
        if city is None:
            return {d: None for d in dates}

        missing = [d for d in dates if self._cache_get(city_slug, d) is None]
        if missing:
            fetched = None
            for attempt in range(2):
                try:
                    fetched = self.client.fetch_daily_temperature(
                        city,
                        dates=sorted(missing),
                        past_days_cap=past_days_cap,
                        allow_archive_fallback=allow_archive_fallback,
                    )
                    break
                except Exception as exc:
                    logger.warning(
                        "Open-Meteo fetch failed for %s (attempt %s/2): %s",
                        city_slug,
                        attempt + 1,
                        exc,
                    )
                    if attempt == 0:
                        time.sleep(3.0)
            if fetched is None:
                return {d: None for d in dates}
            for day in fetched.days:
                self._cache_put(city_slug, day.date, fetched)

        return {d: self._cache_get(city_slug, d) for d in dates}

    def resolve_batch(
        self,
        items: list[ForecastLookupKey],
        *,
        past_days_cap: int | None = None,
        allow_archive_fallback: bool = True,
    ) -> list[ForecastLookupResult]:
        if not items:
            return []

        by_city: dict[str, set[str]] = {}
        for item in items:
            by_city.setdefault(item.city_slug, set()).add(item.date)

        city_forecasts: dict[tuple[str, str], DailyTemperatureForecast | None] = {}
        for city_slug, dates in sorted(by_city.items()):
            fetched = self._fetch_city_dates(
                city_slug,
                dates,
                past_days_cap=past_days_cap,
                allow_archive_fallback=allow_archive_fallback,
            )
            for date, forecast in fetched.items():
                city_forecasts[(city_slug, date)] = forecast

        results: list[ForecastLookupResult] = []
        for item in items:
            city = get_city(item.city_slug)
            forecast = city_forecasts.get((item.city_slug, item.date))
            if city is None:
                results.append(
                    ForecastLookupResult(
                        city_slug=item.city_slug,
                        date=item.date,
                        metric=item.metric,
                        error="city_not_configured",
                    )
                )
                continue
            if forecast is None:
                results.append(
                    ForecastLookupResult(
                        city_slug=item.city_slug,
                        date=item.date,
                        metric=item.metric,
                        model=city.models,
                        error="forecast_unavailable",
                    )
                )
                continue
            results.append(
                ForecastLookupResult(
                    city_slug=item.city_slug,
                    date=item.date,
                    metric=item.metric,
                    model=forecast.model,
                    requested_model=forecast.requested_model,
                    model_fallback=forecast.model_fallback,
                    unit=forecast.unit,
                    temp=self._temp_for_metric(forecast, item.date, item.metric),
                )
            )
        return results

    def resolve_history_batch(self, items: list[ForecastLookupKey]) -> list[ForecastLookupResult]:
        """Single-model history: same forecast API as dashboard, past_days capped at 92, no archive."""
        return self.resolve_batch(
            items,
            past_days_cap=HISTORY_SINGLE_PAST_DAYS,
            allow_archive_fallback=False,
        )
