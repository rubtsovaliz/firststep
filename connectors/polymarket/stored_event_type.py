"""Re-apply temperature type normalization on stored event JSON files."""

from __future__ import annotations

from typing import Any

from connectors.polymarket.temperature_type import (
    MarketTypeNormalization,
    build_type_normalization_input,
    normalize_market_type,
)


def normalize_market_type_from_stored_event(record: dict[str, Any]) -> MarketTypeNormalization:
    """
    Normalize using our persisted event file shape (post-discovery).

    Uses: event_slug, event_title, tags, all_outcomes[*].question,
    all_outcomes[*].raw_source.market_slug, raw_source.event_slug.
    """
    return normalize_market_type(
        build_type_normalization_input(
            market_type=record.get("market_type"),
            event_slug=record.get("event_slug"),
            slug=record.get("event_slug"),
            event_title=record.get("event_title"),
            title=record.get("event_title"),
            tags=record.get("tags"),
            all_outcomes=record.get("all_outcomes"),
            raw_source=record.get("raw_source"),
        )
    )
