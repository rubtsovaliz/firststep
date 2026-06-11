"""Low-level HTTP client for Open-Meteo Weather Forecast API."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from connectors.forecast.city_config import DEFAULT_DAILY_VARS, CityConfig, get_city
from connectors.forecast.schemas import DailyTemperatureForecast, DailyTemperaturePoint

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
MIN_REQUEST_INTERVAL_SECONDS = 2.5
_last_request_at = 0.0
_request_lock = threading.Lock()


def _optional_api_key_params() -> dict[str, str]:
    key = os.environ.get("OPEN_METEO_API_KEY", "").strip()
    return {"apikey": key} if key else {}


class OpenMeteoError(RuntimeError):
    """Raised when Open-Meteo returns an error or the request fails."""


class OpenMeteoClient:
    """
    Read-only Open-Meteo client.

    Each city uses exactly one weather model from config/cities.yaml (``models`` field).
    See https://open-meteo.com/en/docs
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        archive_base_url: str = ARCHIVE_BASE_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.archive_base_url = archive_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def build_params(
        self,
        city: CityConfig,
        *,
        forecast_days: int = 7,
        past_days: int = 0,
        daily_vars: tuple[str, ...] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Build query params for /v1/forecast with a single model per city."""
        effective_daily = daily_vars or city.daily
        params: dict[str, Any] = {
            "latitude": city.lat,
            "longitude": city.lon,
            "daily": ",".join(effective_daily),
            "timezone": city.tz,
            "temperature_unit": "celsius" if city.unit.upper() == "C" else "fahrenheit",
            "models": model or city.models,
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

    @staticmethod
    def _throttle_requests() -> None:
        global _last_request_at
        elapsed = time.monotonic() - _last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        _last_request_at = time.monotonic()

    @staticmethod
    def _retry_delay_seconds(attempt: int, exc: Exception) -> float:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            retry_after = exc.response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(float(retry_after), 2.0)
                except ValueError:
                    pass
            return max(10.0 + attempt * 10.0, MIN_REQUEST_INTERVAL_SECONDS)
        return MIN_REQUEST_INTERVAL_SECONDS + attempt * MIN_REQUEST_INTERVAL_SECONDS

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            with _request_lock:
                self._throttle_requests()
                try:
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        response = client.get(url, params=params)
                        response.raise_for_status()
                        data = response.json()
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    last_error = exc
                    logger.warning(
                        "Open-Meteo request failed (attempt %s/%s): %s",
                        attempt + 1,
                        self.max_retries,
                        exc,
                    )
                    retry_delay = self._retry_delay_seconds(attempt, exc)
                    if attempt < self.max_retries - 1:
                        time.sleep(retry_delay)
                    continue

            if data.get("error"):
                reason = data.get("reason") or data.get("error")
                raise OpenMeteoError(f"Open-Meteo API error: {reason}")
            return data

        raise OpenMeteoError(f"Open-Meteo request failed: {url}") from last_error

    @staticmethod
    def _city_today(city: CityConfig) -> date:
        try:
            tz = ZoneInfo(city.tz)
        except Exception:
            tz = timezone.utc
        return datetime.now(tz).date()

    @staticmethod
    def _compute_time_window(
        city: CityConfig,
        dates: list[str] | None,
        forecast_days: int,
    ) -> tuple[int, int, set[str] | None]:
        """Return (past_days, forecast_days, dates_filter) for Open-Meteo."""
        if not dates:
            return 0, forecast_days, None

        dates_filter = set(dates)
        parsed = sorted(date.fromisoformat(d) for d in dates)
        today = OpenMeteoClient._city_today(city)
        min_day, max_day = parsed[0], parsed[-1]

        past_days = max(0, (today - min_day).days)
        if max_day >= today:
            # Open-Meteo needs >=2 days to include "today" in some timezones (e.g. Asia/Kolkata).
            forecast_days = max(2, (max_day - today).days + 2)
        else:
            forecast_days = 1

        return past_days, forecast_days, dates_filter

    @staticmethod
    def _history_date_range(
        city: CityConfig,
        dates_filter: set[str],
        *,
        max_past_days: int | None,
    ) -> tuple[str, str] | None:
        """Use start_date/end_date when every requested day is strictly in the past."""
        if not dates_filter:
            return None
        parsed = sorted(date.fromisoformat(day) for day in dates_filter)
        today = OpenMeteoClient._city_today(city)
        if parsed[-1] >= today:
            return None
        start = parsed[0]
        end = parsed[-1]
        if max_past_days is not None:
            oldest = today - timedelta(days=max_past_days)
            if end < oldest:
                return None
            if start < oldest:
                start = oldest
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _round_temp(value: float | None, unit: str) -> float | None:
        if value is None:
            return None
        return round(value, 1) if unit.upper() == "C" else round(value)

    @staticmethod
    def _data_to_day_map(
        data: dict[str, Any],
        daily_vars: tuple[str, ...] = DEFAULT_DAILY_VARS,
    ) -> dict[str, tuple[float | None, float | None]]:
        daily = data.get("daily") or {}
        times: list[str] = daily.get("time") or []
        max_key = "temperature_2m_max" if "temperature_2m_max" in daily_vars else None
        min_key = "temperature_2m_min" if "temperature_2m_min" in daily_vars else None
        max_vals: list[float | None] = daily.get(max_key) or [] if max_key else []
        min_vals: list[float | None] = daily.get(min_key) or [] if min_key else []
        return {
            day: (
                max_vals[idx] if max_key and idx < len(max_vals) else None,
                min_vals[idx] if min_key and idx < len(min_vals) else None,
            )
            for idx, day in enumerate(times)
        }

    @staticmethod
    def _day_map_has_temperatures(day_map: dict[str, tuple[float | None, float | None]]) -> bool:
        return any(mx is not None or mn is not None for mx, mn in day_map.values())

    @staticmethod
    def _missing_dates(
        day_map: dict[str, tuple[float | None, float | None]],
        dates_filter: set[str],
    ) -> list[str]:
        missing: list[str] = []
        for day in sorted(dates_filter):
            mx, mn = day_map.get(day, (None, None))
            if mx is None and mn is None:
                missing.append(day)
        return missing

    @staticmethod
    def _merge_day_maps(
        base: dict[str, tuple[float | None, float | None]],
        extra: dict[str, tuple[float | None, float | None]],
    ) -> dict[str, tuple[float | None, float | None]]:
        merged = dict(base)
        for day, (mx, mn) in extra.items():
            cur_mx, cur_mn = merged.get(day, (None, None))
            if cur_mx is None and mx is not None:
                cur_mx = mx
            if cur_mn is None and mn is not None:
                cur_mn = mn
            if cur_mx is not None or cur_mn is not None:
                merged[day] = (cur_mx, cur_mn)
        return merged

    def _fetch_forecast_model(
        self,
        city: CityConfig,
        *,
        model: str,
        past_days: int,
        forecast_days: int,
    ) -> dict[str, tuple[float | None, float | None]]:
        params = self.build_params(
            city,
            forecast_days=forecast_days,
            past_days=past_days,
            model=model,
        )
        data = self._request(self.base_url, params)
        return self._data_to_day_map(data, city.daily)

    def _fetch_forecast_model_range(
        self,
        city: CityConfig,
        *,
        model: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, tuple[float | None, float | None]]:
        params = self.build_params(
            city,
            start_date=start_date,
            end_date=end_date,
            past_days=0,
            model=model,
        )
        data = self._request(self.base_url, params)
        return self._data_to_day_map(data, city.daily)

    def _fetch_primary_day_map(
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
                return self._fetch_forecast_model_range(
                    city,
                    model=model,
                    start_date=start_date,
                    end_date=end_date,
                )
        if past_days_cap is not None:
            past_days = min(past_days, past_days_cap)
        return self._fetch_forecast_model(
            city,
            model=model,
            past_days=past_days,
            forecast_days=forecast_days,
        )

    def _fetch_archive(
        self,
        city: CityConfig,
        dates: list[str],
    ) -> dict[str, tuple[float | None, float | None]]:
        if not dates:
            return {}
        sorted_dates = sorted(dates)
        params = {
            "latitude": city.lat,
            "longitude": city.lon,
            "daily": ",".join(city.daily),
            "timezone": city.tz,
            "temperature_unit": "celsius" if city.unit.upper() == "C" else "fahrenheit",
            "start_date": sorted_dates[0],
            "end_date": sorted_dates[-1],
        }
        data = self._request(self.archive_base_url, params)
        return self._data_to_day_map(data, city.daily)

    def _build_forecast_from_map(
        self,
        city: CityConfig,
        day_map: dict[str, tuple[float | None, float | None]],
        *,
        dates_filter: set[str] | None,
        forecast_days: int,
        include_raw: bool,
        model: str,
        requested_model: str,
        model_fallback: bool,
        raw: dict[str, Any] | None = None,
    ) -> DailyTemperatureForecast:
        target_dates = sorted(dates_filter) if dates_filter else sorted(day_map.keys())
        days: list[DailyTemperaturePoint] = []
        for day in target_dates:
            mx, mn = day_map.get(day, (None, None))
            days.append(
                DailyTemperaturePoint(
                    date=day,
                    temp_max_c=self._round_temp(mx, city.unit),
                    temp_min_c=self._round_temp(mn, city.unit),
                )
            )

        return DailyTemperatureForecast(
            city_slug=city.slug,
            city_name=city.name,
            model=model,
            requested_model=requested_model,
            model_fallback=model_fallback,
            unit=city.unit,
            timezone=city.tz,
            latitude=city.lat,
            longitude=city.lon,
            icao=city.icao,
            fetched_at=datetime.now(timezone.utc),
            forecast_days=forecast_days,
            days=days,
            raw=raw if include_raw else None,
        )

    def fetch_archive_daily_temperature(
        self,
        city: CityConfig,
        dates: list[str],
        *,
        include_raw: bool = False,
    ) -> DailyTemperatureForecast:
        """Fetch past temperatures from Open-Meteo archive (one HTTP request)."""
        if not dates:
            raise OpenMeteoError("archive fetch requires at least one date")
        archive_map = self._fetch_archive(city, sorted(dates))
        return self._build_forecast_from_map(
            city,
            archive_map,
            dates_filter=set(dates),
            forecast_days=1,
            include_raw=include_raw,
            model="archive",
            requested_model=city.models,
            model_fallback=True,
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
    ) -> DailyTemperatureForecast:
        """
        Fetch daily max/min temperature for one city using its configured model.

        Uses past_days when event dates include the past. Falls back to
        ``fallback_models`` and Open-Meteo archive for gaps (e.g. BOM/KMA/CMA outages).
        """
        past_days, effective_forecast_days, dates_filter = self._compute_time_window(
            city, dates, forecast_days
        )

        day_map = self._fetch_primary_day_map(
            city,
            model=city.models,
            dates_filter=dates_filter,
            past_days=past_days,
            forecast_days=effective_forecast_days,
            past_days_cap=past_days_cap,
        )
        model_used = city.models
        model_fallback = False

        needs_fallback = not self._day_map_has_temperatures(day_map)
        if dates_filter:
            needs_fallback = needs_fallback or bool(self._missing_dates(day_map, dates_filter))

        if needs_fallback and city.fallback_models:
            logger.warning(
                "Open-Meteo model %s incomplete for %s; trying fallback %s",
                city.models,
                city.slug,
                city.fallback_models,
            )
            fallback_map = self._fetch_primary_day_map(
                city,
                model=city.fallback_models,
                dates_filter=dates_filter,
                past_days=past_days,
                forecast_days=effective_forecast_days,
                past_days_cap=past_days_cap,
            )
            day_map = self._merge_day_maps(day_map, fallback_map)
            if self._day_map_has_temperatures(fallback_map):
                model_used = city.fallback_models
                model_fallback = True

        if dates_filter and allow_archive_fallback:
            today = self._city_today(city)
            still_missing = self._missing_dates(day_map, dates_filter)
            archive_dates = [d for d in still_missing if date.fromisoformat(d) < today]
            if archive_dates:
                logger.info(
                    "Fetching archive temperatures for %s: %s",
                    city.slug,
                    ", ".join(archive_dates),
                )
                archive_map = self._fetch_archive(city, archive_dates)
                day_map = self._merge_day_maps(day_map, archive_map)
                if self._day_map_has_temperatures(archive_map):
                    model_used = f"{model_used}+archive" if model_fallback else "archive"
                    model_fallback = True

        return self._build_forecast_from_map(
            city,
            day_map,
            dates_filter=dates_filter,
            forecast_days=effective_forecast_days,
            include_raw=include_raw,
            model=model_used,
            requested_model=city.models,
            model_fallback=model_fallback,
        )

    def fetch_daily_temperature_by_slug(
        self,
        slug: str,
        *,
        forecast_days: int = 7,
        dates: list[str] | None = None,
        include_raw: bool = False,
    ) -> DailyTemperatureForecast | None:
        """Resolve city from config/cities.yaml and fetch forecast."""
        city = get_city(slug)
        if city is None:
            logger.warning("Unknown city slug for Open-Meteo: %s", slug)
            return None
        return self.fetch_daily_temperature(
            city,
            forecast_days=forecast_days,
            dates=dates,
            include_raw=include_raw,
        )
