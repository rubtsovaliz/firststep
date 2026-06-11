"""Forecast API routes (Open-Meteo single model per city)."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.api.dependencies import get_ensemble_forecast_service, get_forecast_service
from backend.app.services.ensemble_forecast_service import EnsembleForecastService
from backend.app.services.forecast_service import ForecastLookupKey, ForecastService

router = APIRouter(prefix="/api/forecasts", tags=["forecasts"])


class ForecastBatchItem(BaseModel):
    city_slug: str
    date: str
    metric: Literal["high", "low"] = "high"


class ForecastBatchRequest(BaseModel):
    items: list[ForecastBatchItem] = Field(default_factory=list, max_length=5000)


class EnsembleModelTempResult(BaseModel):
    model: str
    temp: float | None = None
    error: str | None = None


class ForecastBatchResult(BaseModel):
    city_slug: str
    date: str
    metric: Literal["high", "low"]
    model: str | None = None
    requested_model: str | None = None
    model_fallback: bool = False
    unit: str | None = None
    temp: float | None = None
    error: str | None = None
    models_temps: list[EnsembleModelTempResult] | None = None


class ForecastBatchResponse(BaseModel):
    results: list[ForecastBatchResult]


@router.post("/batch", response_model=ForecastBatchResponse)
def fetch_forecasts_batch(
    body: ForecastBatchRequest,
    forecasts: ForecastService = Depends(get_forecast_service),
) -> ForecastBatchResponse:
    keys = [
        ForecastLookupKey(
            city_slug=item.city_slug.strip().lower(),
            date=item.date,
            metric=item.metric,
        )
        for item in body.items
    ]
    resolved = forecasts.resolve_batch(keys)
    return ForecastBatchResponse(
        results=[
            ForecastBatchResult(
                city_slug=r.city_slug,
                date=r.date,
                metric=r.metric,
                model=r.model,
                requested_model=r.requested_model,
                model_fallback=r.model_fallback,
                unit=r.unit,
                temp=r.temp,
                error=r.error,
            )
            for r in resolved
        ]
    )


@router.post("/ensemble/batch", response_model=ForecastBatchResponse)
def fetch_ensemble_forecasts_batch(
    body: ForecastBatchRequest,
    forecasts: EnsembleForecastService = Depends(get_ensemble_forecast_service),
) -> ForecastBatchResponse:
    keys = [
        ForecastLookupKey(
            city_slug=item.city_slug.strip().lower(),
            date=item.date,
            metric=item.metric,
        )
        for item in body.items
    ]
    resolved = forecasts.resolve_batch(keys)
    return ForecastBatchResponse(
        results=[
            ForecastBatchResult(
                city_slug=r.city_slug,
                date=r.date,
                metric=r.metric,
                model=r.model,
                requested_model=r.requested_model,
                model_fallback=r.model_fallback,
                unit=r.unit,
                temp=r.temp,
                error=r.error,
                models_temps=[
                    EnsembleModelTempResult(
                        model=entry.model,
                        temp=entry.temp,
                        error=entry.error,
                    )
                    for entry in (r.models_temps or [])
                ]
                or None,
            )
            for r in resolved
        ]
    )
