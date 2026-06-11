"""FastAPI application entrypoint."""

import sys
from pathlib import Path

# Allow imports from repo root (connectors + backend)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import discovery, forecasts, health, history, legacy_dashboard, markets
from backend.app.core.config import get_settings
from backend.app.core.http_cache import ApiNoStoreMiddleware
from backend.app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title="Weather Polymarket Bot",
    description="Read-only weather market discovery and snapshot API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiNoStoreMiddleware)

app.include_router(health.router)
app.include_router(discovery.router)
app.include_router(markets.router)
app.include_router(history.router)
app.include_router(forecasts.router)
app.include_router(legacy_dashboard.router)


@app.get("/api")
def api_root() -> dict[str, str]:
    return {"service": "weather-polymarket-bot", "status": "ok", "legacy_ui": "/markets"}
