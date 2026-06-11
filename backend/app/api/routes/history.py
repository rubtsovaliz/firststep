"""History API — resolved weather events."""

from fastapi import APIRouter, Depends, Query

from backend.app.api.dependencies import get_history_forecast_service, get_history_service
from backend.app.models.api_models import (
    HistoryCitiesResponse,
    HistoryForecastsFetchRequest,
    HistoryForecastsFetchResponse,
    HistoryListResponse,
)
from backend.app.services.history_forecast_service import HistoryForecastService
from backend.app.services.history_service import HistoryService

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/cities", response_model=HistoryCitiesResponse)
def list_history_cities(
    search: str | None = Query(None),
    history: HistoryService = Depends(get_history_service),
) -> HistoryCitiesResponse:
    cities = history.list_cities(search=search)
    return HistoryCitiesResponse(count=len(cities), cities=cities)


@router.get("", response_model=HistoryListResponse)
def list_history(
    search: str | None = Query(None),
    city_slug: str | None = Query(None),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    history: HistoryService = Depends(get_history_service),
) -> HistoryListResponse:
    page, total = history.list_history(
        search=search,
        city_slug=city_slug,
        limit=limit,
        offset=offset,
    )
    return HistoryListResponse(count=total, events=page)


@router.post("/forecasts/fetch", response_model=HistoryForecastsFetchResponse)
def fetch_history_forecasts(
    body: HistoryForecastsFetchRequest,
    forecasts: HistoryForecastService = Depends(get_history_forecast_service),
) -> HistoryForecastsFetchResponse:
    """Fetch missing Open-Meteo temps for history rows and persist to event JSON."""
    events = forecasts.fetch_and_persist(body.storage_keys)
    return HistoryForecastsFetchResponse(events=events)
