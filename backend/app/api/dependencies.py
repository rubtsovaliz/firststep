"""FastAPI dependency injection."""

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.services.discovery_service import DiscoveryService
from backend.app.services.ensemble_forecast_service import EnsembleForecastService
from backend.app.services.forecast_service import ForecastService
from backend.app.services.history_forecast_service import HistoryForecastService
from backend.app.services.history_service import HistoryService
from backend.app.services.market_service import MarketService
from backend.app.services.snapshot_service import SnapshotService


@lru_cache
def get_cached_settings() -> Settings:
    return get_settings()


def get_snapshot_service() -> SnapshotService:
    return SnapshotService(get_cached_settings())


def get_discovery_service() -> DiscoveryService:
    settings = get_cached_settings()
    snapshots = SnapshotService(settings)
    return DiscoveryService(settings, snapshots)


def get_market_service() -> MarketService:
    return MarketService(SnapshotService(get_cached_settings()))


@lru_cache
def get_history_forecast_service() -> HistoryForecastService:
    settings = get_cached_settings()
    snapshots = SnapshotService(settings)
    return HistoryForecastService(
        snapshots,
        get_forecast_service(),
        get_ensemble_forecast_service(),
    )


def get_history_service() -> HistoryService:
    return HistoryService(
        SnapshotService(get_cached_settings()),
        forecast_enricher=get_history_forecast_service(),
    )


@lru_cache
def get_forecast_service() -> ForecastService:
    return ForecastService()


@lru_cache
def get_ensemble_forecast_service() -> EnsembleForecastService:
    return EnsembleForecastService()
