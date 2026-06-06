from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_discovery_service, get_snapshot_service
from backend.app.models.api_models import DiscoveryRefreshResponse, DiscoveryStatusResponse
from backend.app.services.discovery_service import DiscoveryService
from backend.app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.post("/refresh", response_model=DiscoveryRefreshResponse)
def refresh_discovery(
    discovery: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryRefreshResponse:
    return discovery.refresh()


@router.get("/status", response_model=DiscoveryStatusResponse)
def discovery_status(
    snapshots: SnapshotService = Depends(get_snapshot_service),
) -> DiscoveryStatusResponse:
    return snapshots.load_discovery_status()
