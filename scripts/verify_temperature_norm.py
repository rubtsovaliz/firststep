#!/usr/bin/env python3
"""Print normalization results for real stored event JSON samples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors.polymarket.stored_event_type import normalize_market_type_from_stored_event
from connectors.polymarket.temperature_type import normalize_market_type

EVENTS = ROOT / "data" / "snapshots" / "events"


def _load(name: str) -> dict:
    return json.loads((EVENTS / name).read_text(encoding="utf-8"))


def _print_case(label: str, result: dict) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(result, indent=2))


def main() -> None:
    # 1 highest title (real)
    beijing = _load("beijing_2026-06-04.json")
    _print_case("1) highest title (beijing_2026-06-04.json)", normalize_market_type_from_stored_event(beijing))

    # 2 highest slug only
    _print_case(
        "2) highest slug only",
        normalize_market_type({"event_slug": "highest-temperature-in-beijing-on-june-5-2026"}),
    )

    # 3 highest tags only (strip title/slug signals)
    _print_case(
        "3) highest tags only",
        normalize_market_type(
            {
                "event_title": "Weather market",
                "tags": ["Weather", "Highest temperature"],
            }
        ),
    )

    # 4 lowest slug (real london)
    london = _load("london_2026-06-04.json")
    _print_case("4) lowest slug (london_2026-06-04.json)", normalize_market_type_from_stored_event(london))

    # 5 unknown weather (synthetic non-temperature)
    _print_case(
        "5) unknown weather (rain)",
        normalize_market_type(
            {
                "event_title": "How many inches of rain in Miami on June 5?",
                "tags": ["Weather"],
                "all_outcomes": [
                    {"question": "Will Miami receive more than 2 inches of rain on June 5?"}
                ],
            }
        ),
    )

    # Fallback demo: title stripped, only all_outcomes question
    paris = _load("paris_2026-06-04.json")
    stripped = {
        "event_title": "Weather",
        "event_slug": "",
        "tags": ["Weather"],
        "all_outcomes": paris.get("all_outcomes", [])[:2],
    }
    _print_case("Bonus) fallback via all_outcomes only (paris buckets)", normalize_market_type_from_stored_event(stripped))


if __name__ == "__main__":
    main()
