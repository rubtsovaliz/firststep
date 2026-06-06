from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.api.dependencies import get_market_service
from backend.app.models.api_models import MarketDetailResponse, MarketsListResponse
from backend.app.services.market_service import MarketService

router = APIRouter(prefix="/api/markets", tags=["markets"])


@router.get("", response_model=MarketsListResponse)
def list_markets(
    search: str | None = Query(None),
    active_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    markets: MarketService = Depends(get_market_service),
) -> MarketsListResponse:
    page, total = markets.list_events(
        search=search,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return MarketsListResponse(count=total, events=page, markets=page)


@router.get("/{storage_key}", response_model=MarketDetailResponse)
def get_market(
    storage_key: str,
    markets: MarketService = Depends(get_market_service),
) -> MarketDetailResponse:
    record = markets.get_event_detail(storage_key)
    if record is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return MarketDetailResponse(market=record)
