"""Load or fetch+persist history forecasts for resolved events."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from connectors.forecast.city_config import get_city
from connectors.forecast.open_meteo_client import OpenMeteoClient
from backend.app.models.api_models import (
    HistoryEventSummary,
    HistoryForecastModelTemp,
    HistoryForecastSlice,
)
from backend.app.services.ensemble_forecast_service import (
    HISTORY_ENSEMBLE_PAST_DAYS,
    EnsembleForecastService,
)
from backend.app.services.forecast_service import (
    HISTORY_SINGLE_PAST_DAYS,
    EnsembleModelTempResult,
    ForecastLookupKey,
    ForecastLookupResult,
    ForecastService,
)
from backend.app.services.history_forecast_store import (
    needs_ensemble_refetch,
    needs_history_forecast_fetch,
    needs_single_refetch,
    persist_history_forecasts,
    read_history_forecasts,
)
from backend.app.services.history_service import (
    extract_winning_bucket,
    mark_history_forecasts_cached,
    resolve_metric,
)
from backend.app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)

HISTORY_SINGLE_DATE_CHUNK_DAYS = 31
HISTORY_ENSEMBLE_DATE_CHUNK_DAYS = 31
HISTORY_API_PAUSE_SECONDS = 2.5
HISTORY_ENSEMBLE_API_PAUSE_SECONDS = 10.0


def _lookup_result_key(row: ForecastLookupKey) -> tuple[str, str, str]:
    return (row.city_slug, row.date, row.metric)


def _split_lookups_by_date_span(
    city_slug: str,
    lookups: list[ForecastLookupKey],
    *,
    max_age_days: int,
    max_span_days: int,
) -> list[list[ForecastLookupKey]]:
    city = get_city(city_slug)
    if city is None:
        return [lookups]

    today = OpenMeteoClient._city_today(city)
    oldest = today - timedelta(days=max_age_days)
    eligible = sorted(
        (lu for lu in lookups if date.fromisoformat(lu.date) >= oldest),
        key=lambda row: row.date,
    )
    if not eligible:
        return []

    chunks: list[list[ForecastLookupKey]] = []
    current: list[ForecastLookupKey] = []
    for lookup in eligible:
        if not current:
            current = [lookup]
            continue
        chunk_start = date.fromisoformat(current[0].date)
        lookup_day = date.fromisoformat(lookup.date)
        if (lookup_day - chunk_start).days <= max_span_days:
            current.append(lookup)
        else:
            chunks.append(current)
            current = [lookup]
    if current:
        chunks.append(current)
    return chunks


def _too_old_single_result(lookup: ForecastLookupKey) -> ForecastLookupResult:
    city = get_city(lookup.city_slug)
    return ForecastLookupResult(
        city_slug=lookup.city_slug,
        date=lookup.date,
        metric=lookup.metric,
        model=city.models if city else None,
        requested_model=city.models if city else None,
        error="outside_single_window",
    )


def _result_has_ensemble_temp(ensemble: ForecastLookupResult) -> bool:
    if ensemble.temp is not None:
        return True
    return any(entry.temp is not None for entry in (ensemble.models_temps or []))


def _should_persist_forecasts(
    single: ForecastLookupResult,
    ensemble: ForecastLookupResult,
) -> bool:
    return single.temp is not None or _result_has_ensemble_temp(ensemble)


def _single_from_stored(stored_single: dict) -> ForecastLookupResult:
    return ForecastLookupResult(
        city_slug=str(stored_single.get("city_slug") or ""),
        date=str(stored_single.get("date") or ""),
        metric=stored_single.get("metric"),  # type: ignore[arg-type]
        model=stored_single.get("model"),
        requested_model=stored_single.get("requested_model"),
        model_fallback=bool(stored_single.get("model_fallback", False)),
        unit=stored_single.get("unit"),
        temp=stored_single.get("temp"),
        error=stored_single.get("error"),
    )


def _outside_ensemble_result(lookup: ForecastLookupKey) -> ForecastLookupResult:
    city = get_city(lookup.city_slug)
    models = city.ensemble_models if city else []
    return ForecastLookupResult(
        city_slug=lookup.city_slug,
        date=lookup.date,
        metric=lookup.metric,
        model="+".join(models),
        requested_model="+".join(models),
        models_temps=[
            EnsembleModelTempResult(
                model=model_id,
                temp=None,
                error="outside_ensemble_window",
            )
            for model_id in models
        ],
        error="outside_ensemble_window",
    )


class HistoryForecastService:
    def __init__(
        self,
        snapshots: SnapshotService,
        forecast_service: ForecastService,
        ensemble_forecast_service: EnsembleForecastService,
    ) -> None:
        self.snapshots = snapshots
        self.forecasts = forecast_service
        self.ensemble_forecasts = ensemble_forecast_service

    @staticmethod
    def _parse_models_temps(raw: object) -> list[HistoryForecastModelTemp] | None:
        if not isinstance(raw, list):
            return None
        parsed: list[HistoryForecastModelTemp] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            parsed.append(
                HistoryForecastModelTemp(
                    model=str(entry.get("model") or ""),
                    temp=entry.get("temp"),
                    error=entry.get("error"),
                )
            )
        return parsed or None

    @classmethod
    def _slice_from_dict(cls, data: dict | None) -> HistoryForecastSlice | None:
        if not data:
            return None
        return HistoryForecastSlice(
            city_slug=str(data.get("city_slug") or ""),
            date=str(data.get("date") or ""),
            metric=str(data.get("metric") or "high"),
            model=data.get("model"),
            requested_model=data.get("requested_model"),
            model_fallback=bool(data.get("model_fallback", False)),
            unit=data.get("unit"),
            temp=data.get("temp"),
            error=data.get("error"),
            models_temps=cls._parse_models_temps(data.get("models_temps")),
        )

    def enrich_event(self, row: HistoryEventSummary) -> HistoryEventSummary:
        record = self.snapshots.load_event(row.storage_key)
        if not record:
            return row
        stored = read_history_forecasts(record)
        if not stored:
            return row
        return row.model_copy(
            update={
                "forecasts_cached": True,
                "forecasts_saved_at": stored.get("saved_at"),
                "single_model": self._slice_from_dict(stored.get("single")),
                "ensemble": self._slice_from_dict(stored.get("ensemble")),
            }
        )

    def _lookup_key_from_record(self, record: dict, storage_key: str) -> ForecastLookupKey | None:
        metric = resolve_metric(record)
        city_slug = record.get("city_slug")
        date = record.get("date")
        if not metric or not city_slug or not date:
            logger.warning("Cannot resolve forecast key for %s", storage_key)
            return None
        return ForecastLookupKey(
            city_slug=str(city_slug).strip().lower(),
            date=str(date),
            metric=metric,  # type: ignore[arg-type]
        )

    def _resolve_single_history(self, lookups: list[ForecastLookupKey]) -> list[ForecastLookupResult]:
        by_city: dict[str, list[ForecastLookupKey]] = defaultdict(list)
        for lookup in lookups:
            by_city[lookup.city_slug].append(lookup)

        resolved: dict[tuple[str, str, str], ForecastLookupResult] = {}
        for city_slug, city_lookups in by_city.items():
            city = get_city(city_slug)
            if city is None:
                for lookup in city_lookups:
                    resolved[_lookup_result_key(lookup)] = ForecastLookupResult(
                        city_slug=lookup.city_slug,
                        date=lookup.date,
                        metric=lookup.metric,
                        error="city_not_configured",
                    )
                continue

            today = OpenMeteoClient._city_today(city)
            oldest = today - timedelta(days=HISTORY_SINGLE_PAST_DAYS)
            for lookup in city_lookups:
                if date.fromisoformat(lookup.date) < oldest:
                    resolved[_lookup_result_key(lookup)] = _too_old_single_result(lookup)

            chunks = _split_lookups_by_date_span(
                city_slug,
                city_lookups,
                max_age_days=HISTORY_SINGLE_PAST_DAYS,
                max_span_days=HISTORY_SINGLE_DATE_CHUNK_DAYS,
            )
            for index, chunk in enumerate(chunks):
                for row in self.forecasts.resolve_history_batch(chunk):
                    resolved[_lookup_result_key(row)] = row
                if index + 1 < len(chunks):
                    time.sleep(HISTORY_API_PAUSE_SECONDS)

        return [
            resolved.get(
                _lookup_result_key(lookup),
                ForecastLookupResult(
                    city_slug=lookup.city_slug,
                    date=lookup.date,
                    metric=lookup.metric,
                    error="forecast_unavailable",
                ),
            )
            for lookup in lookups
        ]

    def _resolve_ensemble_history(
        self,
        lookups: list[ForecastLookupKey],
    ) -> list[ForecastLookupResult]:
        by_city: dict[str, list[ForecastLookupKey]] = defaultdict(list)
        for lookup in lookups:
            by_city[lookup.city_slug].append(lookup)

        resolved: dict[tuple[str, str, str], ForecastLookupResult] = {}
        for city_slug, city_lookups in by_city.items():
            fetchable: list[ForecastLookupKey] = []
            for lookup in city_lookups:
                if self.ensemble_forecasts._is_within_past_days(
                    city_slug,
                    lookup.date,
                    max_days=HISTORY_ENSEMBLE_PAST_DAYS,
                ):
                    fetchable.append(lookup)
                else:
                    resolved[_lookup_result_key(lookup)] = _outside_ensemble_result(lookup)

            chunks = _split_lookups_by_date_span(
                city_slug,
                fetchable,
                max_age_days=HISTORY_ENSEMBLE_PAST_DAYS,
                max_span_days=HISTORY_ENSEMBLE_DATE_CHUNK_DAYS,
            )
            for index, chunk in enumerate(chunks):
                for row in self.ensemble_forecasts.resolve_history_batch(chunk):
                    resolved[_lookup_result_key(row)] = row
                if index + 1 < len(chunks):
                    time.sleep(HISTORY_ENSEMBLE_API_PAUSE_SECONDS)

        return [
            resolved.get(
                _lookup_result_key(lookup),
                ForecastLookupResult(
                    city_slug=lookup.city_slug,
                    date=lookup.date,
                    metric=lookup.metric,
                    error="forecast_unavailable",
                ),
            )
            for lookup in lookups
        ]

    def _fetch_city_batch(
        self,
        lookups: list[ForecastLookupKey],
    ) -> tuple[list[ForecastLookupResult], list[ForecastLookupResult]]:
        # Ensemble first: only 2 HTTP calls per city, before single exhausts the IP quota.
        ensemble_results = self._resolve_ensemble_history(lookups)
        time.sleep(HISTORY_ENSEMBLE_API_PAUSE_SECONDS)
        single_results = self._resolve_single_history(lookups)
        return single_results, ensemble_results

    def fetch_and_persist(self, storage_keys: list[str]) -> list[HistoryEventSummary]:
        results_by_key: dict[str, HistoryEventSummary] = {}
        pending_by_city: dict[str, list[tuple[str, HistoryEventSummary, ForecastLookupKey]]] = (
            defaultdict(list)
        )
        pending_ensemble_by_city: dict[
            str,
            list[tuple[str, HistoryEventSummary, ForecastLookupKey, dict[str, Any]]],
        ] = defaultdict(list)

        for storage_key in storage_keys:
            record = self.snapshots.load_event(storage_key)
            if not record:
                continue

            win = extract_winning_bucket(record) or ""
            base = HistoryEventSummary(
                storage_key=storage_key,
                date=str(record.get("date") or ""),
                event_title=str(record.get("event_title") or ""),
                city_slug=str(record.get("city_slug") or ""),
                metric=str(resolve_metric(record) or ""),
                win=win,
                unit=record.get("unit"),
            )

            stored = read_history_forecasts(record)
            if stored is not None and not needs_history_forecast_fetch(record):
                results_by_key[storage_key] = self.enrich_event(base)
                continue

            lookup = self._lookup_key_from_record(record, storage_key)
            if lookup is None:
                results_by_key[storage_key] = base
                continue

            if (
                stored is not None
                and not needs_single_refetch(stored)
                and needs_ensemble_refetch(record, stored)
            ):
                pending_ensemble_by_city[lookup.city_slug].append(
                    (storage_key, base, lookup, stored),
                )
                continue

            pending_by_city[lookup.city_slug].append((storage_key, base, lookup))

        for city_items in pending_by_city.values():
            lookups = [item[2] for item in city_items]
            single_results, ensemble_results = self._fetch_city_batch(lookups)
            for (storage_key, base, _lookup), single, ensemble in zip(
                city_items,
                single_results,
                ensemble_results,
                strict=True,
            ):
                if not _should_persist_forecasts(single, ensemble):
                    results_by_key[storage_key] = base
                    continue

                persist_history_forecasts(
                    self.snapshots,
                    storage_key,
                    single=single,
                    ensemble=ensemble,
                )
                mark_history_forecasts_cached(storage_key, city_slug=base.city_slug)
                results_by_key[storage_key] = self.enrich_event(base)

        for city_items in pending_ensemble_by_city.values():
            lookups = [item[2] for item in city_items]
            ensemble_results = self._resolve_ensemble_history(lookups)
            for (storage_key, base, _lookup, stored), ensemble in zip(
                city_items,
                ensemble_results,
                strict=True,
            ):
                single = _single_from_stored(stored["single"])
                if not _should_persist_forecasts(single, ensemble):
                    results_by_key[storage_key] = base
                    continue

                persist_history_forecasts(
                    self.snapshots,
                    storage_key,
                    single=single,
                    ensemble=ensemble,
                )
                results_by_key[storage_key] = self.enrich_event(base)

        return [results_by_key[key] for key in storage_keys if key in results_by_key]
