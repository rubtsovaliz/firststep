"""Heuristic filters for weather-related Polymarket events and markets."""

from __future__ import annotations

import re
from typing import Any

WEATHER_KEYWORDS = frozenset(
    {
        "weather",
        "climate",
        "temperature",
        "rain",
        "rainfall",
        "snow",
        "snowfall",
        "wind",
        "forecast",
        "precipitation",
        "hottest",
        "coldest",
    }
)

TITLE_KEYWORDS = frozenset(
    {
        "highest temperature",
        "temperature in",
        "high temperature",
        "low temperature",
        "hottest city",
        "hottest",
        "coldest",
        "rain",
        "rainfall",
        "snowfall",
        "wind",
        "weather",
        "precipitation",
    }
)


def _normalize_text(*parts: str | None) -> str:
    return " ".join(p for p in parts if p).lower()


def _tag_strings(tags: Any) -> list[str]:
    if not tags:
        return []
    result: list[str] = []
    for tag in tags:
        if isinstance(tag, str):
            result.append(tag.lower())
        elif isinstance(tag, dict):
            for key in ("slug", "label", "name"):
                val = tag.get(key)
                if val:
                    result.append(str(val).lower())
    return result


def text_has_weather_keyword(text: str) -> bool:
    """Check if text contains weather-related keywords."""
    lowered = text.lower()
    if any(kw in lowered for kw in WEATHER_KEYWORDS):
        return True
    return any(kw in lowered for kw in TITLE_KEYWORDS)


def is_weather_event(event: dict[str, Any]) -> bool:
    """Return True if event looks weather-related."""
    title = event.get("title") or ""
    description = event.get("description") or ""
    category = (event.get("category") or "").lower()
    combined = _normalize_text(title, description, category)

    if category and any(kw in category for kw in WEATHER_KEYWORDS):
        return True

    tag_text = " ".join(_tag_strings(event.get("tags")))
    if tag_text and any(kw in tag_text for kw in WEATHER_KEYWORDS | {"weather"}):
        return True

    if text_has_weather_keyword(combined):
        return True

    # Slug pattern from matule95 bot: highest-temperature-in-{city}-on-...
    slug = (event.get("slug") or "").lower()
    if re.search(
        r"highest-temperature|lowest-temperature|temperature-in-|rainfall|snowfall",
        slug,
    ):
        return True

    return False


def is_weather_market(market: dict[str, Any], event: dict[str, Any] | None = None) -> bool:
    """Return True if individual market looks weather-related."""
    question = market.get("question") or ""
    category = (market.get("category") or "").lower()
    combined = _normalize_text(question, category)

    if text_has_weather_keyword(combined):
        return True

    if event and is_weather_event(event):
        # Temperature bucket questions inside weather events
        if re.search(r"°[fc]|temperature|rain|snow|wind|precipitation", question, re.I):
            return True

    return False
