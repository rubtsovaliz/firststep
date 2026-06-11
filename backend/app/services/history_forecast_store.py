"""Persist Open-Meteo history forecasts in per-event JSON files."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.services.forecast_service import ForecastLookupResult
from backend.app.services.snapshot_service import SnapshotService

HISTORY_FORECASTS_EXT_KEY = "history_forecasts"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lookup_result_to_dict(result: ForecastLookupResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "city_slug": result.city_slug,
        "date": result.date,
        "metric": result.metric,
        "model": result.model,
        "requested_model": result.requested_model,
        "model_fallback": result.model_fallback,
        "unit": result.unit,
        "temp": result.temp,
        "error": result.error,
    }
    if result.models_temps:
        payload["models_temps"] = [
            {
                "model": entry.model,
                "temp": entry.temp,
                "error": entry.error,
            }
            for entry in result.models_temps
        ]
    return payload


def read_history_forecasts(record: dict[str, Any]) -> dict[str, Any] | None:
    extensions = record.get("extensions") or {}
    stored = extensions.get(HISTORY_FORECASTS_EXT_KEY)
    if not isinstance(stored, dict):
        return None
    if "single" not in stored or "ensemble" not in stored:
        return None
    return stored


def is_forecasts_cached(record: dict[str, Any]) -> bool:
    return read_history_forecasts(record) is not None


def ensemble_has_temperature(ensemble: dict[str, Any]) -> bool:
    if ensemble.get("temp") is not None:
        return True
    for entry in ensemble.get("models_temps") or []:
        if isinstance(entry, dict) and entry.get("temp") is not None:
            return True
    return False


def needs_ensemble_refetch(record: dict[str, Any], stored: dict[str, Any]) -> bool:
    """Retry ensemble when a prior in-window fetch failed (e.g. Open-Meteo 429)."""
    from backend.app.services.ensemble_forecast_service import (
        HISTORY_ENSEMBLE_PAST_DAYS,
        EnsembleForecastService,
    )

    city_slug = str(record.get("city_slug") or "").strip().lower()
    event_date = str(record.get("date") or "")
    if not city_slug or not event_date:
        return False
    if not EnsembleForecastService._is_within_past_days(
        city_slug,
        event_date,
        max_days=HISTORY_ENSEMBLE_PAST_DAYS,
    ):
        return False

    ensemble = stored.get("ensemble")
    if not isinstance(ensemble, dict):
        return True
    if ensemble_has_temperature(ensemble):
        return False
    error = ensemble.get("error")
    if error == "outside_ensemble_window":
        return True
    return error in (None, "forecast_unavailable")


def needs_single_refetch(stored: dict[str, Any]) -> bool:
    single = stored.get("single")
    if not isinstance(single, dict):
        return True
    return single.get("temp") is None


def needs_history_forecast_fetch(record: dict[str, Any]) -> bool:
    stored = read_history_forecasts(record)
    if stored is None:
        return True
    if needs_single_refetch(stored):
        return True
    return needs_ensemble_refetch(record, stored)


def persist_history_forecasts(
    snapshots: SnapshotService,
    storage_key: str,
    *,
    single: ForecastLookupResult,
    ensemble: ForecastLookupResult,
) -> dict[str, Any] | None:
    record = snapshots.load_event(storage_key)
    if not record:
        return None

    extensions = record.setdefault("extensions", {})
    extensions[HISTORY_FORECASTS_EXT_KEY] = {
        "saved_at": _utc_now(),
        "single": lookup_result_to_dict(single),
        "ensemble": lookup_result_to_dict(ensemble),
    }
    record["updated_at"] = _utc_now()
    snapshots.save_event(record)
    return extensions[HISTORY_FORECASTS_EXT_KEY]
