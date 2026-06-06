"""
Temperature-only market type normalization.

Scope (phase 1.5):
  - Only resolves max/min *temperature* markets:
    market_type in {"max_temperature", "min_temperature"} | None
    temperature_metric in {"high", "low"} | None
  - Non-temperature weather (rain, wind, precipitation, snow, etc.) intentionally
    resolve to (None, None). Extend later with separate types, e.g. market_type="rain".

Trading/strategy code should use market_type + temperature_metric, not tag/title text.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

# Temperature-only literals. Future: RainMarketType, WindMarketType, etc.
MarketType = Literal["max_temperature", "min_temperature"]
TemperatureMetric = Literal["high", "low"]

VALID_MARKET_TYPES: frozenset[str] = frozenset({"max_temperature", "min_temperature"})

_METRIC_BY_TYPE: dict[MarketType, TemperatureMetric] = {
    "max_temperature": "high",
    "min_temperature": "low",
}


class MarketTypeNormalization(TypedDict):
    market_type: MarketType | None
    temperature_metric: TemperatureMetric | None


def _metric_for_type(market_type: MarketType) -> TemperatureMetric:
    return _METRIC_BY_TYPE[market_type]


def _slugify_for_match(text: str) -> str:
    """Lowercase and unify separators for pattern matching."""
    return re.sub(r"[\s_]+", "-", text.strip().lower())


def _infer_from_text(text: str) -> MarketTypeNormalization:
    """Infer max/min temperature type from free text (case-insensitive)."""
    if not text or not str(text).strip():
        return {"market_type": None, "temperature_metric": None}

    lowered = str(text).lower()
    compact = _slugify_for_match(text)

    is_max = bool(
        re.search(r"\bhighest[\s-]+temperature\b", lowered)
        or re.search(r"\bhigh[\s-]+temperature\b", lowered)
        or "highest-temperature" in compact
        or "high-temperature" in compact
    )
    is_min = bool(
        re.search(r"\blowest[\s-]+temperature\b", lowered)
        or re.search(r"\blow[\s-]+temperature\b", lowered)
        or "lowest-temperature" in compact
        or "low-temperature" in compact
    )

    if is_max and not is_min:
        mt: MarketType = "max_temperature"
        return {"market_type": mt, "temperature_metric": _metric_for_type(mt)}
    if is_min and not is_max:
        mt = "min_temperature"
        return {"market_type": mt, "temperature_metric": _metric_for_type(mt)}

    # Rain/wind/precipitation strings deliberately do not map here.
    return {"market_type": None, "temperature_metric": None}


def _tag_text(tags: Any) -> str:
    if not tags:
        return ""
    parts: list[str] = []
    for tag in tags:
        if isinstance(tag, str):
            parts.append(tag)
        elif isinstance(tag, dict):
            for key in ("label", "slug", "name"):
                if tag.get(key):
                    parts.append(str(tag[key]))
                    break
    return " ".join(parts)


def _event_slug_sources(event: dict[str, Any]) -> str:
    """event_slug, slug, and raw_source.event_slug (stored JSON shape)."""
    raw = event.get("raw_source") if isinstance(event.get("raw_source"), dict) else {}
    parts = [
        event.get("event_slug"),
        event.get("slug"),
        raw.get("event_slug"),
    ]
    return " ".join(str(p) for p in parts if p)


def _gamma_market_questions(event: dict[str, Any]) -> str:
    questions: list[str] = []
    for market in event.get("markets", []):
        if isinstance(market, dict):
            q = market.get("question")
            if q:
                questions.append(str(q))
    return " ".join(questions)


def _all_outcome_questions(event: dict[str, Any]) -> str:
    """Stored snapshot shape: all_outcomes[*].question."""
    questions: list[str] = []
    for outcome in event.get("all_outcomes", []):
        if isinstance(outcome, dict):
            q = outcome.get("question")
            if q:
                questions.append(str(q))
    return " ".join(questions)


def _outcome_market_slugs(event: dict[str, Any]) -> str:
    """Stored snapshot: all_outcomes[*].raw_source.market_slug."""
    slugs: list[str] = []
    for outcome in event.get("all_outcomes", []):
        if not isinstance(outcome, dict):
            continue
        raw = outcome.get("raw_source")
        if isinstance(raw, dict) and raw.get("market_slug"):
            slugs.append(str(raw["market_slug"]))
    return " ".join(slugs)


def build_type_normalization_input(
    *,
    market_type: Any = None,
    event_slug: str | None = None,
    slug: str | None = None,
    event_title: str | None = None,
    title: str | None = None,
    tags: Any = None,
    markets: list[Any] | None = None,
    all_outcomes: list[Any] | None = None,
    raw_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a dict compatible with normalize_market_type from Gamma or stored event."""
    payload: dict[str, Any] = {}
    if market_type is not None:
        payload["market_type"] = market_type
    if event_slug:
        payload["event_slug"] = event_slug
    if slug:
        payload["slug"] = slug
    if event_title:
        payload["event_title"] = event_title
    if title:
        payload["title"] = title
    if tags is not None:
        payload["tags"] = tags
    if markets is not None:
        payload["markets"] = markets
    if all_outcomes is not None:
        payload["all_outcomes"] = all_outcomes
    if raw_source is not None:
        payload["raw_source"] = raw_source
    return payload


def normalize_market_type(event: dict[str, Any]) -> MarketTypeNormalization:
    """
    Resolve temperature-only market_type and temperature_metric.

    Priority:
    1) existing valid market_type on event
    2) event_slug / slug / raw_source.event_slug
    3) event_title / title
    4) tags
    5) questions: Gamma markets[*].question, then all_outcomes[*].question
    6) all_outcomes[*].raw_source.market_slug

    Non-temperature weather → (None, None) without error.
    """
    existing = event.get("market_type")
    if isinstance(existing, str):
        normalized_existing = existing.strip().lower()
        if normalized_existing in VALID_MARKET_TYPES:
            mt = normalized_existing  # type: ignore[assignment]
            return {
                "market_type": mt,
                "temperature_metric": _metric_for_type(mt),
            }

    slug_sources = _event_slug_sources(event)
    title = str(event.get("event_title") or event.get("title") or "")
    tags = _tag_text(event.get("tags"))
    questions = " ".join(
        part for part in (_gamma_market_questions(event), _all_outcome_questions(event)) if part
    )
    market_slugs = _outcome_market_slugs(event)

    for source in (slug_sources, title, tags, questions, market_slugs):
        if not source:
            continue
        inferred = _infer_from_text(str(source))
        if inferred["market_type"] is not None:
            return inferred

    return {"market_type": None, "temperature_metric": None}
