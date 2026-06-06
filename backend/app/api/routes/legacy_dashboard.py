"""Serve copied WeatherBot Jinja dashboard (legacy_web/) via FastAPI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[4]
TEMPLATES_DIR = ROOT / "legacy_web" / "templates"

router = APIRouter(tags=["legacy-dashboard"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ctx(active_page: str) -> dict:
    return {"active_page": active_page, "mode": "dry"}


@router.get("/", response_class=HTMLResponse)
def legacy_dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            **_ctx("dashboard"),
            "exposure": 0.0,
            "max_exposure": 0.0,
            "realized": 0.0,
            "unrealized": 0.0,
            "active_events": 0,
            "trends": {},
            "forecasts": {},
            "daily_maxes": {},
            "positions": [],
            "signals": [],
            "cities_with_positions": 0,
            "strategy_summary": [],
            "strat_realized": {},
            "strat_meta": {},
            "daily_loss_remaining": 0.0,
            "daily_loss_limit": 0.0,
            "decision_log": [],
            "price_source": "gamma",
        },
    )


@router.get("/markets", response_class=HTMLResponse)
def legacy_markets(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "markets.html",
        {**_ctx("markets"), "events": [], "next_scan_minutes": "-"},
    )


@router.get("/positions", response_class=HTMLResponse)
def legacy_positions(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "positions.html",
        {
            **_ctx("positions"),
            "positions": [],
            "closed_positions": [],
            "total_exposure": 0.0,
            "global_limit": 0.0,
            "cities": {},
            "city_limit": 0.0,
            "strategies": {},
            "strat_pnl": {},
            "strat_realized": {},
            "strat_exposure": {},
            "strategy_summary": [],
            "strat_meta": {},
            "snapshot_meta": None,
            "pending_redemptions": [],
            "drift_rows": [],
        },
    )


@router.get("/trades", response_class=HTMLResponse)
def legacy_trades(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "trades.html",
        {
            **_ctx("trades"),
            "timeline": [],
            "closed_entry_count": 0,
            "strat_pnl": {},
            "strat_exposure": {},
            "strat_counts": {},
            "strat_meta": {},
        },
    )


@router.get("/temperatures", response_class=HTMLResponse)
def legacy_temperatures(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "temperatures.html",
        {
            **_ctx("temperatures"),
            "cities": [],
            "observation_series": {},
            "forecasts": {},
            "daily_maxes": {},
            "trends": {},
            "city_timezones": {},
            "error_dists": {},
        },
    )


@router.get("/analytics", response_class=HTMLResponse)
def legacy_analytics(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "analytics.html",
        {
            **_ctx("analytics"),
            "edge_summary": {},
            "edge_history": [],
            "decision_log": [],
        },
    )


@router.get("/history", response_class=HTMLResponse)
def legacy_history(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            **_ctx("history"),
            "pnl_history": [],
            "settlements": [],
            "strat_meta": {},
        },
    )


@router.get("/config", response_class=HTMLResponse)
def legacy_config(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            **_ctx("config"),
            "strategy": type("S", (), {"__dict__": {}})(),
            "scheduling": type("Sch", (), {"rebalance_interval_minutes": 0})(),
            "cities": [],
            "variants": {},
            "strat_meta": {},
            "trim_ratios": [],
            "calibrator_rows": [],
        },
    )
