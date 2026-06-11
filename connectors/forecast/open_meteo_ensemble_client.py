"""Open-Meteo Ensemble API client (multi-model per city)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from connectors.forecast.city_config import DEFAULT_DAILY_VARS, CityConfig, get_city
from connectors.forecast.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoError,
    _optional_api_key_params,
)
from connectors.forecast.schemas import (
    DailyTemperatureForecast,
    DailyTemperaturePoint,
    EnsembleModelReading,
)

logger = logging.getLogger(__name__)

ENSEMBLE_BASE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
ENSEMBLE_MIN_REQUEST_INTERVAL_SECONDS = 8.0
# Mean variants retain hindcast in past_days=92; raw member ids often do not.
HISTORY_ENSEMBLE_MODEL_IDS: dict[str, str] = {
    "ecmwf_ifs025_ensemble": "ecmwf_ifs025_ensemble_mean",
    "ncep_gefs_seamless": "ncep_gefs_ensemble_mean_seamless",
    "gem_global_ensemble": "gem_global_ensemble_mean",
}


def history_ensemble_model_id(model: str) -> str:
    return HISTORY_ENSEMBLE_MODEL_IDS.get(model, model)
_ensemble_last_request_at = 0.0
_ensemble_request_lock = threading.Lock()


class OpenMeteoEnsembleClient(OpenMeteoClient):
    """
    Fetch daily temperature from Open-Meteo Ensemble API.

    Uses all ``ensemble_models`` from config/cities.yaml.
    See https://open-meteo.com/en/docs/ensemble-api
    """

    def __init__(
        self,
        base_url: str = ENSEMBLE_BASE_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max(max_retries, 7),
            retry_backoff_seconds=retry_backoff_seconds,
        )

    @staticmethod
    def _throttle_ensemble_requests() -> None:
        global _ensemble_last_request_at
        elapsed = time.monotonic() - _ensemble_last_request_at
        if elapsed < ENSEMBLE_MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(ENSEMBLE_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        _ensemble_last_request_at = time.monotonic()

    @staticmethod
    def _ensemble_retry_delay_seconds(attempt: int, exc: Exception) -> float:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            retry_after = exc.response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(float(retry_after), ENSEMBLE_MIN_REQUEST_INTERVAL_SECONDS)
                except ValueError:
                    pass
            return 30.0 + attempt * 30.0
        return ENSEMBLE_MIN_REQUEST_INTERVAL_SECONDS + attempt * ENSEMBLE_MIN_REQUEST_INTERVAL_SECONDS

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            with _ensemble_request_lock:
                self._throttle_ensemble_requests()
                try:
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        response = client.get(url, params=params)
                        response.raise_for_status()
                        data = response.json()
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    last_error = exc
                    logger.warning(
                        "Open-Meteo ensemble request failed (attempt %s/%s): %s",
                        attempt + 1,
                        self.max_retries,
                        exc,
                    )
                    retry_delay = self._ensemble_retry_delay_seconds(attempt, exc)
                    if attempt < self.max_retries - 1:
                        time.sleep(retry_delay)
                    continue

            if data.get("error"):
                reason = data.get("reason") or data.get("error")
                raise OpenMeteoError(f"Open-Meteo API error: {reason}")
            return data

        raise OpenMeteoError(f"Open-Meteo request failed: {url}") from last_error

    def build_ensemble_params(
        self,
        city: CityConfig,
        *,
        forecast_days: int = 7,
        past_days: int = 0,
        start_date: str | None = None,
        end_date: str | None = None,
        daily_vars: tuple[str, ...] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Build query params for /v1/ensemble."""
        if model is None:
            raise ValueError("ensemble model id is required")
        effective_daily = daily_vars or city.daily
        params: dict[str, Any] = {
            "latitude": city.lat,
            "longitude": city.lon,
            "daily": ",".join(effective_daily),
            "timezone": city.tz,
            "temperature_unit": "celsius" if city.unit.upper() == "C" else "fahrenheit",
            "models": model,
        }
        if start_date and end_date and past_days == 0:
            params["start_date"] = start_date
            params["end_date"] = end_date
        else:
            if past_days > 0:
                params["past_days"] = past_days
            params["forecast_days"] = forecast_days
        params.update(_optional_api_key_params())
        return params

    def _fetch_ensemble(
        self,
        city: CityConfig,
        *,
        model: str,
        past_days: int,
        forecast_days: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, tuple[float | None, float | None]]:
        params = self.build_ensemble_params(
            city,
            forecast_days=forecast_days,
            past_days=past_days,
            start_date=start_date,
            end_date=end_date,
            model=model,
        )
        data = self._request(self.base_url, params)
        return self._data_to_day_map(data, city.daily)

    def _fetch_ensemble_day_map(
        self,
        city: CityConfig,
        *,
        model: str,
        dates_filter: set[str] | None,
        past_days: int,
        forecast_days: int,
        past_days_cap: int | None,
    ) -> dict[str, tuple[float | None, float | None]]:
        if dates_filter:
            date_range = self._history_date_range(
                city,
                dates_filter,
                max_past_days=past_days_cap,
            )
            if date_range:
                start_date, end_date = date_range
                return self._fetch_ensemble(
                    city,
                    model=model,
                    past_days=0,
                    forecast_days=1,
                    start_date=start_date,
                    end_date=end_date,
                )
        if past_days_cap is not None:
            past_days = min(past_days, past_days_cap)
        return self._fetch_ensemble(
            city,
            model=model,
            past_days=past_days,
            forecast_days=forecast_days,
        )

    def _target_dates(
        self,
        model_maps: dict[str, dict[str, tuple[float | None, float | None]]],
        dates_filter: set[str] | None,
    ) -> list[str]:
        if dates_filter:
            return sorted(dates_filter)
        all_dates: set[str] = set()
        for day_map in model_maps.values():
            all_dates.update(day_map.keys())
        return sorted(all_dates)

    def _build_day_point(
        self,
        city: CityConfig,
        day: str,
        models: tuple[str, ...],
        model_maps: dict[str, dict[str, tuple[float | None, float | None]]],
    ) -> DailyTemperaturePoint:
        readings: list[EnsembleModelReading] = []
        first_max: float | None = None
        first_min: float | None = None

        for model_id in models:
            mx, mn = model_maps.get(model_id, {}).get(day, (None, None))
            max_rounded = self._round_temp(mx, city.unit)
            min_rounded = self._round_temp(mn, city.unit)
            readings.append(
                EnsembleModelReading(
                    model=model_id,
                    temp_max_c=max_rounded,
                    temp_min_c=min_rounded,
                )
            )
            if first_max is None and max_rounded is not None:
                first_max = max_rounded
            if first_min is None and min_rounded is not None:
                first_min = min_rounded

        return DailyTemperaturePoint(
            date=day,
            temp_max_c=first_max,
            temp_min_c=first_min,
            by_ensemble_model=readings,
        )

    def fetch_daily_temperature(
        self,
        city: CityConfig,
        *,
        forecast_days: int = 7,
        dates: list[str] | None = None,
        include_raw: bool = False,
        past_days_cap: int | None = None,
        allow_archive_fallback: bool = True,
        for_history: bool = False,
    ) -> DailyTemperatureForecast:
        """Fetch ensemble daily max/min for every configured ensemble model."""
        past_days, effective_forecast_days, dates_filter = self._compute_time_window(
            city, dates, forecast_days
        )

        models = city.ensemble_models
        model_maps: dict[str, dict[str, tuple[float | None, float | None]]] = {}
        for model_id in models:
            api_model_id = history_ensemble_model_id(model_id) if for_history else model_id
            try:
                model_maps[model_id] = self._fetch_ensemble_day_map(
                    city,
                    model=api_model_id,
                    dates_filter=dates_filter,
                    past_days=past_days,
                    forecast_days=effective_forecast_days,
                    past_days_cap=past_days_cap,
                )
            except Exception as exc:
                logger.warning(
                    "Ensemble model %s failed for %s: %s",
                    api_model_id,
                    city.slug,
                    exc,
                )
                model_maps[model_id] = {}

        used_archive = False
        if dates_filter and allow_archive_fallback:
            today = self._city_today(city)
            missing_dates: set[str] = set()
            for model_id in models:
                missing_dates.update(
                    self._missing_dates(model_maps.get(model_id, {}), dates_filter)
                )
            archive_dates = [
                day for day in sorted(missing_dates) if date.fromisoformat(day) < today
            ]
            if archive_dates:
                logger.info(
                    "Ensemble gaps for %s; filling past dates from archive: %s",
                    city.slug,
                    ", ".join(archive_dates),
                )
                archive_map = self._fetch_archive(city, archive_dates)
                for model_id in models:
                    model_maps[model_id] = self._merge_day_maps(
                        model_maps.get(model_id, {}),
                        archive_map,
                    )
                used_archive = self._day_map_has_temperatures(archive_map)

        days = [
            self._build_day_point(city, day, models, model_maps)
            for day in self._target_dates(model_maps, dates_filter)
        ]

        successful_models = [
            model_id
            for model_id in models
            if self._day_map_has_temperatures(model_maps.get(model_id, {}))
        ]
        model_label = "+".join(successful_models or models)
        if used_archive:
            model_label = f"{model_label}+archive"

        result = DailyTemperatureForecast(
            city_slug=city.slug,
            city_name=city.name,
            model=model_label,
            requested_model="+".join(models),
            model_fallback=False,
            unit=city.unit,
            timezone=city.tz,
            latitude=city.lat,
            longitude=city.lon,
            icao=city.icao,
            fetched_at=datetime.now(timezone.utc),
            forecast_days=effective_forecast_days,
            days=days,
            raw=None if not include_raw else {"models": list(models)},
        )
        return result.model_copy(update={"source": "open-meteo-ensemble"})

    def fetch_daily_temperature_by_slug(
        self,
        slug: str,
        *,
        forecast_days: int = 7,
        dates: list[str] | None = None,
        include_raw: bool = False,
    ) -> DailyTemperatureForecast | None:
        city = get_city(slug)
        if city is None:
            logger.warning("Unknown city slug for Open-Meteo ensemble: %s", slug)
            return None
        return self.fetch_daily_temperature(
            city,
            forecast_days=forecast_days,
            dates=dates,
            include_raw=include_raw,
        )
