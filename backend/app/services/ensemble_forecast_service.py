"""Fetch Open-Meteo ensemble model temperatures for dashboard."""

from __future__ import annotations

import logging
import time
from datetime import date

from connectors.forecast.city_config import get_city
from connectors.forecast.open_meteo_client import OpenMeteoClient
from connectors.forecast.open_meteo_ensemble_client import OpenMeteoEnsembleClient
from connectors.forecast.schemas import DailyTemperatureForecast, DailyTemperaturePoint
from backend.app.services.forecast_service import (
    EnsembleModelTempResult,
    ForecastLookupKey,
    ForecastLookupResult,
    TemperatureMetric,
)

logger = logging.getLogger(__name__)

HISTORY_ENSEMBLE_PAST_DAYS = 92


class EnsembleForecastService:
    """Resolve per-event ensemble forecast temps via Open-Meteo Ensemble API."""

    def __init__(
        self,
        client: OpenMeteoEnsembleClient | None = None,
        cache_ttl_seconds: float = 900.0,
    ) -> None:
        self.client = client or OpenMeteoEnsembleClient()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[str, str], tuple[float, DailyTemperatureForecast]] = {}

    @staticmethod
    def _point_has_temperature(point: DailyTemperaturePoint | None) -> bool:
        if point is None:
            return False
        if point.temp_max_c is not None or point.temp_min_c is not None:
            return True
        return any(
            reading.temp_max_c is not None or reading.temp_min_c is not None
            for reading in point.by_ensemble_model
        )

    def _cache_get(self, city_slug: str, date: str) -> DailyTemperatureForecast | None:
        entry = self._cache.get((city_slug, date))
        if not entry:
            return None
        expires_at, forecast = entry
        if time.monotonic() > expires_at:
            self._cache.pop((city_slug, date), None)
            return None
        if not self._point_has_temperature(forecast.by_date().get(date)):
            self._cache.pop((city_slug, date), None)
            return None
        return forecast

    def _cache_put(self, city_slug: str, date: str, forecast: DailyTemperatureForecast) -> None:
        day = forecast.by_date().get(date)
        if not self._point_has_temperature(day):
            return
        cached = forecast.model_copy(update={"days": [day]})
        self._cache[(city_slug, date)] = (
            time.monotonic() + self.cache_ttl_seconds,
            cached,
        )

    @staticmethod
    def _temp_for_metric(
        forecast: DailyTemperatureForecast,
        date: str,
        metric: TemperatureMetric,
    ) -> float | None:
        if metric == "high":
            return forecast.temp_max_for(date)
        return forecast.temp_min_for(date)

    @staticmethod
    def _models_temps_for_metric(
        point: DailyTemperaturePoint | None,
        metric: TemperatureMetric,
    ) -> list[EnsembleModelTempResult]:
        if point is None:
            return []
        results: list[EnsembleModelTempResult] = []
        for reading in point.by_ensemble_model:
            temp = reading.temp_max_c if metric == "high" else reading.temp_min_c
            results.append(
                EnsembleModelTempResult(
                    model=reading.model,
                    temp=temp,
                    error=None if temp is not None else "forecast_unavailable",
                )
            )
        return results

    @staticmethod
    def _is_within_past_days(city_slug: str, event_date: str, *, max_days: int) -> bool:
        city = get_city(city_slug)
        if city is None:
            return False
        try:
            parsed = date.fromisoformat(event_date)
        except ValueError:
            return False
        today = OpenMeteoClient._city_today(city)
        delta = (today - parsed).days
        return 0 <= delta <= max_days

    def _fetch_city_dates(
        self,
        city_slug: str,
        dates: set[str],
        *,
        past_days_cap: int | None = None,
        allow_archive_fallback: bool = True,
        for_history: bool = False,
    ) -> dict[str, DailyTemperatureForecast | None]:
        city = get_city(city_slug)
        if city is None:
            return {d: None for d in dates}

        use_cache = not for_history
        missing = [
            d
            for d in dates
            if not use_cache or self._cache_get(city_slug, d) is None
        ]
        if missing:
            fetched = None
            for attempt in range(2):
                try:
                    fetched = self.client.fetch_daily_temperature(
                        city,
                        dates=sorted(missing),
                        past_days_cap=past_days_cap,
                        allow_archive_fallback=allow_archive_fallback,
                        for_history=for_history,
                    )
                    break
                except Exception as exc:
                    logger.warning(
                        "Open-Meteo ensemble fetch failed for %s (attempt %s/2): %s",
                        city_slug,
                        attempt + 1,
                        exc,
                    )
                    if attempt == 0:
                        time.sleep(30.0)
            if fetched is None:
                return {d: None for d in dates}
            if use_cache:
                for day in fetched.days:
                    self._cache_put(city_slug, day.date, fetched)
            else:
                by_date = fetched.by_date()
                return {
                    d: (
                        fetched.model_copy(update={"days": [by_date[d]]})
                        if d in by_date
                        else None
                    )
                    for d in dates
                }

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
                        model="+".join(city.ensemble_models),
                        requested_model="+".join(city.ensemble_models),
                        models_temps=[
                            EnsembleModelTempResult(
                                model=model_id,
                                temp=None,
                                error="forecast_unavailable",
                            )
                            for model_id in city.ensemble_models
                        ],
                        error="forecast_unavailable",
                    )
                )
                continue

            point = forecast.by_date().get(item.date)
            models_temps = self._models_temps_for_metric(point, item.metric)
            primary_temp = next(
                (entry.temp for entry in models_temps if entry.temp is not None),
                None,
            )
            results.append(
                ForecastLookupResult(
                    city_slug=item.city_slug,
                    date=item.date,
                    metric=item.metric,
                    model=forecast.model,
                    requested_model=forecast.requested_model,
                    model_fallback=forecast.model_fallback,
                    unit=forecast.unit,
                    temp=primary_temp,
                    models_temps=models_temps,
                )
            )
        return results

    def resolve_history_batch(self, items: list[ForecastLookupKey]) -> list[ForecastLookupResult]:
        """Ensemble history: configured ensemble models, past_days capped at 92."""
        if not items:
            return []

        fetchable: list[ForecastLookupKey] = []
        prefetch: dict[tuple[str, str, str], ForecastLookupResult] = {}
        for item in items:
            city = get_city(item.city_slug)
            if city is None:
                prefetch[(item.city_slug, item.date, item.metric)] = ForecastLookupResult(
                    city_slug=item.city_slug,
                    date=item.date,
                    metric=item.metric,
                    error="city_not_configured",
                )
                continue
            if not self._is_within_past_days(
                item.city_slug,
                item.date,
                max_days=HISTORY_ENSEMBLE_PAST_DAYS,
            ):
                prefetch[(item.city_slug, item.date, item.metric)] = ForecastLookupResult(
                    city_slug=item.city_slug,
                    date=item.date,
                    metric=item.metric,
                    model="+".join(city.ensemble_models),
                    requested_model="+".join(city.ensemble_models),
                    models_temps=[
                        EnsembleModelTempResult(
                            model=model_id,
                            temp=None,
                            error="outside_ensemble_window",
                        )
                        for model_id in city.ensemble_models
                    ],
                    error="outside_ensemble_window",
                )
                continue
            fetchable.append(item)

        by_city: dict[str, set[str]] = {}
        for item in fetchable:
            by_city.setdefault(item.city_slug, set()).add(item.date)

        city_forecasts: dict[tuple[str, str], DailyTemperatureForecast | None] = {}
        for city_slug, date_set in sorted(by_city.items()):
            fetched = self._fetch_city_dates(
                city_slug,
                date_set,
                past_days_cap=HISTORY_ENSEMBLE_PAST_DAYS,
                allow_archive_fallback=False,
                for_history=True,
            )
            for event_date, forecast in fetched.items():
                city_forecasts[(city_slug, event_date)] = forecast

        fetched_by_key: dict[tuple[str, str, str], ForecastLookupResult] = {}
        for item in fetchable:
            key = (item.city_slug, item.date, item.metric)
            city = get_city(item.city_slug)
            forecast = city_forecasts.get((item.city_slug, item.date))
            if city is None:
                fetched_by_key[key] = ForecastLookupResult(
                    city_slug=item.city_slug,
                    date=item.date,
                    metric=item.metric,
                    error="city_not_configured",
                )
                continue
            if forecast is None:
                fetched_by_key[key] = ForecastLookupResult(
                    city_slug=item.city_slug,
                    date=item.date,
                    metric=item.metric,
                    model="+".join(city.ensemble_models),
                    requested_model="+".join(city.ensemble_models),
                    models_temps=[
                        EnsembleModelTempResult(
                            model=model_id,
                            temp=None,
                            error="forecast_unavailable",
                        )
                        for model_id in city.ensemble_models
                    ],
                    error="forecast_unavailable",
                )
                continue

            point = forecast.by_date().get(item.date)
            models_temps = self._models_temps_for_metric(point, item.metric)
            primary_temp = next(
                (entry.temp for entry in models_temps if entry.temp is not None),
                None,
            )
            fetched_by_key[key] = ForecastLookupResult(
                city_slug=item.city_slug,
                date=item.date,
                metric=item.metric,
                model=forecast.model,
                requested_model=forecast.requested_model,
                model_fallback=forecast.model_fallback,
                unit=forecast.unit,
                temp=primary_temp,
                models_temps=models_temps,
                error=None if primary_temp is not None else "forecast_unavailable",
            )

        results: list[ForecastLookupResult] = []
        for item in items:
            key = (item.city_slug, item.date, item.metric)
            if key in prefetch:
                results.append(prefetch[key])
            else:
                results.append(fetched_by_key[key])
        return results
