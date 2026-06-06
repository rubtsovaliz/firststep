"""Normalize Gamma weather events into canonical WeatherEvent records."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from connectors.polymarket.temperature_type import (
    MarketType,
    TemperatureMetric,
    build_type_normalization_input,
    normalize_market_type,
)
from connectors.polymarket.settlement_time import (
    compute_settle_at,
    hours_until_settle,
)

MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

CITY_MAP = {
    "new york": "nyc",
    "nyc": "nyc",
    "london": "london",
    "paris": "paris",
    "tokyo": "tokyo",
    "buenos aires": "buenos-aires",
    "ankara": "ankara",
    "seoul": "seoul",
    "dallas": "dallas",
    "chicago": "chicago",
    "miami": "miami",
    "atlanta": "atlanta",
    "seattle": "seattle",
    "munich": "munich",
    "toronto": "toronto",
    "shanghai": "shanghai",
    "singapore": "singapore",
    "tel aviv": "tel-aviv",
    "sao paulo": "sao-paulo",
    "wellington": "wellington",
    "lucknow": "lucknow",
}


def parse_temp_range(question: str | None) -> tuple[float, float] | None:
    """
    Parse temperature bucket bounds from a market question.

    Supports:
    - "X or below"  -> (-999, X)
    - "X or higher" -> (X, 999)
    - "between A-B" -> (A, B)
    - exact "be 27°C on" -> (27, 27)
    """
    if not question:
        return None

    num = r"(-?\d+(?:\.\d+)?)"

    if re.search(r"or below", question, re.IGNORECASE):
        match = re.search(num + r"[°]?[FC]\s*or\s*below", question, re.IGNORECASE)
        if match:
            return (-999.0, float(match.group(1)))

    if re.search(r"or higher|or above|or more", question, re.IGNORECASE):
        match = re.search(num + r"[°]?[FC]\s*or\s*(?:higher|above|more)", question, re.IGNORECASE)
        if match:
            return (float(match.group(1)), 999.0)

    match = re.search(
        r"between\s+" + num + r"\s*[-–]\s*" + num + r"[°]?[FC]",
        question,
        re.IGNORECASE,
    )
    if match:
        return (float(match.group(1)), float(match.group(2)))

    match = re.search(r"(?:between\s+)?" + num + r"\s*[-–]\s*" + num + r"[°]?[FC]", question, re.IGNORECASE)
    if match:
        return (float(match.group(1)), float(match.group(2)))

    match = re.search(r"be\s+" + num + r"[°]?[FC]\s+on", question, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        return (value, value)

    match = re.search(num + r"[°]?[FC]\s+on", question, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        return (value, value)

    return None


def detect_unit(question: str) -> str:
    if "°c" in question.lower() or "celsius" in question.lower():
        return "C"
    if "°f" in question.lower() or "fahrenheit" in question.lower():
        return "F"
    return "F"


def extract_city_slug(title: str) -> str:
    lowered = title.lower()
    for pattern, slug in CITY_MAP.items():
        if pattern in lowered:
            return slug
    match = re.search(r"in\s+(.+?)\s+on\s", title, re.IGNORECASE)
    if match:
        raw = match.group(1).strip().lower()
        return re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or "unknown"
    return "unknown"


def extract_event_date(title: str, event: dict[str, Any]) -> str:
    for month_name, month_num in MONTHS.items():
        match = re.search(rf"{month_name}\s+(\d{{1,2}})", title, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            end_date = event.get("endDate") or ""
            year = end_date[:4] if len(end_date) >= 4 else str(datetime.now(timezone.utc).year)
            return f"{year}-{month_num}-{day:02d}"

    end_date = event.get("endDate") or ""
    if len(end_date) >= 10:
        return end_date[:10]

    slug = event.get("slug") or ""
    match = re.search(r"on-(\w+)-(\d+)-(\d{4})", slug)
    if match:
        month_name, day, year = match.group(1), int(match.group(2)), match.group(3)
        month_num = MONTHS.get(month_name.lower())
        if month_num:
            return f"{year}-{month_num}-{day:02d}"

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def event_storage_key(
    city_slug: str,
    date: str,
    event_id: str | int | None = None,
    *,
    temperature_metric: TemperatureMetric | None = None,
    market_type: MarketType | None = None,
    event_slug: str | None = None,
) -> str:
    """
    One stored file per Polymarket *event* (not just city+date).

    Same city+date can have separate highest/lowest Gamma events; suffix high/low
    prevents the second from being dropped during discovery dedupe.
    """
    base = f"{city_slug}_{date}"
    metric = temperature_metric
    if metric is None and market_type == "max_temperature":
        metric = "high"
    if metric is None and market_type == "min_temperature":
        metric = "low"
    if metric is None and event_slug:
        slug = event_slug.lower()
        if "highest-temperature" in slug:
            metric = "high"
        elif "lowest-temperature" in slug:
            metric = "low"
    if metric in ("high", "low"):
        return f"{base}_{metric}"
    if event_id is not None:
        return f"{base}_{event_id}"
    if city_slug == "unknown" and event_slug:
        safe = re.sub(r"[^a-z0-9]+", "-", event_slug.lower()).strip("-")[:48]
        return f"{base}_{safe or 'event'}"
    return base


def _parse_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    raw = value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(raw, list):
        return None
    result: list[float] = []
    for item in raw:
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            continue
    return result or None


def _parse_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def _tag_labels(tags: Any) -> list[str]:
    labels: list[str] = []
    if not tags:
        return labels
    for tag in tags:
        if isinstance(tag, str):
            labels.append(tag)
        elif isinstance(tag, dict):
            for key in ("label", "slug", "name"):
                if tag.get(key):
                    labels.append(str(tag[key]))
                    break
    return labels


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_clob_token(market: dict[str, Any]) -> str | None:
    raw = market.get("clobTokenIds")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, list) and raw:
        return str(raw[0])
    return None


class MarketSnapshotSummary(BaseModel):
    """Append-only event-level market summary (from discovery refresh)."""

    ts: str
    active: bool = True
    closed: bool = False
    end_date: str | None = None
    liquidity: float | None = None
    volume: float | None = None
    outcomes_count: int = 0
    top_bucket: str | None = None
    top_price: float | None = None
    event_title: str | None = None


class WeatherOutcome(BaseModel):
    """Single temperature/outcome bucket within a weather event."""

    market_id: str | int | None = None
    question: str
    bucket_low: float
    bucket_high: float
    unit: str | None = None
    yes_price: float | None = None
    no_price: float | None = None
    volume: float | None = None
    liquidity: float | None = None
    token_id: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[float] | None = None
    active: bool = True
    closed: bool = False
    raw_source: dict[str, Any] = Field(default_factory=dict)


class WeatherEvent(BaseModel):
    """Canonical weather event: one city + date + all buckets."""

    storage_key: str
    event_id: str | int | None = None
    event_slug: str | None = None
    event_title: str
    city_slug: str
    city_name: str | None = None
    date: str
    unit: str | None = None
    station: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    closed: bool = False
    end_date: str | None = None
    event_end_date: str | None = None
    liquidity: float | None = None
    volume: float | None = None
    # Temperature-only (see temperature_type.py). None for rain/wind/etc. until extended.
    market_type: MarketType | None = None
    temperature_metric: TemperatureMetric | None = None
    all_outcomes: list[WeatherOutcome] = Field(default_factory=list)
    market_snapshots: list[MarketSnapshotSummary] = Field(default_factory=list)
    settle_at: str | None = None
    hours_to_settle: float | None = None
    raw_source: dict[str, Any] = Field(default_factory=dict)


# Backward-compatible alias for API code still importing WeatherMarket
WeatherMarket = WeatherEvent


def normalize_outcome(event: dict[str, Any], market: dict[str, Any]) -> WeatherOutcome | None:
    """Normalize one nested market bucket."""
    question = market.get("question") or ""
    parsed = parse_temp_range(question)
    if parsed is None:
        return None

    bucket_low, bucket_high = parsed
    prices = _parse_float_list(market.get("outcomePrices")) or []
    yes_price = prices[0] if prices else None
    no_price = prices[1] if len(prices) > 1 else None

    return WeatherOutcome(
        market_id=market.get("id"),
        question=question,
        bucket_low=bucket_low,
        bucket_high=bucket_high,
        unit=detect_unit(question),
        yes_price=yes_price,
        no_price=no_price,
        volume=_to_float(market.get("volume")),
        liquidity=_to_float(market.get("liquidity")),
        token_id=_first_clob_token(market),
        outcomes=_parse_str_list(market.get("outcomes")),
        outcome_prices=prices or None,
        active=bool(market.get("active", event.get("active", True))),
        closed=bool(market.get("closed", event.get("closed", False))),
        raw_source={
            "market_slug": market.get("slug"),
            "condition_id": market.get("conditionId"),
        },
    )


def normalize_weather_event(event: dict[str, Any]) -> WeatherEvent | None:
    """Normalize a Gamma event with all temperature buckets."""
    from connectors.polymarket.weather_market_filter import is_weather_market

    event_title = event.get("title") or ""
    if not event_title and not event.get("markets"):
        return None

    outcomes: list[WeatherOutcome] = []
    for raw_market in event.get("markets", []):
        if not isinstance(raw_market, dict):
            continue
        if not is_weather_market(raw_market, event):
            continue
        outcome = normalize_outcome(event, raw_market)
        if outcome:
            outcomes.append(outcome)

    if not outcomes:
        return None

    outcomes.sort(key=lambda o: o.bucket_low)
    city_slug = extract_city_slug(event_title)
    date = extract_event_date(event_title, event)
    event_id = event.get("id")
    unit = outcomes[0].unit
    tags = _tag_labels(event.get("tags"))
    type_payload = normalize_market_type(
        build_type_normalization_input(
            market_type=event.get("market_type"),
            event_slug=event.get("slug"),
            slug=event.get("slug"),
            event_title=event_title,
            title=event_title,
            tags=tags,
            markets=event.get("markets", []),
        )
    )
    storage_key = event_storage_key(
        city_slug,
        date,
        event_id,
        temperature_metric=type_payload["temperature_metric"],
        market_type=type_payload["market_type"],
        event_slug=event.get("slug"),
    )

    markets_raw = event.get("markets", [])
    game_start_time = None
    if markets_raw and isinstance(markets_raw[0], dict):
        game_start_time = markets_raw[0].get("gameStartTime")
    settle_dt = compute_settle_at(
        market_date=date,
        city_slug=city_slug,
        game_start_time=str(game_start_time) if game_start_time else None,
    )
    settle_at = settle_dt.isoformat() if settle_dt else None
    hours_to_settle = hours_until_settle(settle_dt)

    return WeatherEvent(
        storage_key=storage_key,
        event_id=event_id,
        event_slug=event.get("slug"),
        event_title=event_title,
        city_slug=city_slug,
        city_name=city_slug.replace("-", " ").title(),
        date=date,
        unit=unit,
        category=event.get("category"),
        tags=tags,
        active=bool(event.get("active", True)),
        closed=bool(event.get("closed", False)),
        end_date=event.get("endDate"),
        event_end_date=event.get("endDate"),
        liquidity=_to_float(event.get("liquidity")),
        volume=_to_float(event.get("volume")),
        market_type=type_payload["market_type"],
        temperature_metric=type_payload["temperature_metric"],
        all_outcomes=outcomes,
        settle_at=settle_at,
        hours_to_settle=hours_to_settle,
        raw_source={
            "event_slug": event.get("slug"),
            "event_id": event_id,
            "markets_count": len(event.get("markets", [])),
            "game_start_time": game_start_time,
        },
    )


def merge_gamma_events(*batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate events by id/slug and merge nested markets."""
    merged: dict[str, dict[str, Any]] = {}

    for batch in batches:
        for event in batch:
            if not isinstance(event, dict):
                continue
            key = str(event.get("id") or event.get("slug") or "")
            if not key:
                continue
            if key not in merged:
                merged[key] = event
                continue
            existing = merged[key]
            existing_ids = {
                str(m.get("id"))
                for m in existing.get("markets", [])
                if isinstance(m, dict) and m.get("id") is not None
            }
            for market in event.get("markets", []):
                if not isinstance(market, dict):
                    continue
                mid = str(market.get("id", ""))
                if mid and mid not in existing_ids:
                    existing.setdefault("markets", []).append(market)
                    existing_ids.add(mid)

    return list(merged.values())
