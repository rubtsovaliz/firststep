"""FastAPI dependency injection."""

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.services.discovery_service import DiscoveryService
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
