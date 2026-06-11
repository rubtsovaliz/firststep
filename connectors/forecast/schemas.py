"""Pydantic schemas for Open-Meteo forecast responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EnsembleModelReading(BaseModel):
    """Temperature from one ensemble model for a single day."""

    model: str
    temp_max_c: float | None = None
    temp_min_c: float | None = None


class DailyTemperaturePoint(BaseModel):
    """One calendar day of model temperature forecast."""

    date: str
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    by_ensemble_model: list[EnsembleModelReading] = Field(default_factory=list)


class DailyTemperatureForecast(BaseModel):
    """Normalized daily temperature forecast for a single city + model."""

    city_slug: str
    city_name: str
    model: str
    requested_model: str | None = None
    model_fallback: bool = False
    unit: str = "C"
    timezone: str
    latitude: float
    longitude: float
    icao: str | None = None
    fetched_at: datetime
    forecast_days: int
    days: list[DailyTemperaturePoint] = Field(default_factory=list)
    source: str = "open-meteo"
    raw: dict[str, Any] | None = Field(default=None, repr=False)

    def by_date(self) -> dict[str, DailyTemperaturePoint]:
        return {d.date: d for d in self.days}

    def temp_max_for(self, date: str) -> float | None:
        point = self.by_date().get(date)
        return point.temp_max_c if point else None

    def temp_min_for(self, date: str) -> float | None:
        point = self.by_date().get(date)
        return point.temp_min_c if point else None
