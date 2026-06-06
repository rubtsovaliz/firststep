#!/usr/bin/env python3
"""
Find city+date pairs in Gamma raw dump where both highest and lowest exist.
Reports old-key collisions (one file) vs new keys (high/low suffix).
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors.polymarket.market_normalizer import (  # noqa: E402
    event_storage_key,
    extract_city_slug,
    extract_event_date,
    normalize_weather_event,
)
from connectors.polymarket.weather_market_filter import is_weather_event  # noqa: E402

RAW = ROOT / "data" / "raw" / "gamma_events_raw.json"
ACTIVE = ROOT / "data" / "snapshots" / "active_weather_events.json"

HIGHEST = re.compile(r"highest-temperature", re.I)
LOWEST = re.compile(r"lowest-temperature", re.I)


def legacy_key(city: str, date: str) -> str:
    return f"{city}_{date}"


def main() -> None:
    if not RAW.exists():
        raise SystemExit(f"Missing {RAW} — run discovery refresh first")

    data = json.loads(RAW.read_text(encoding="utf-8"))
    events = data.get("events", [])

    by_legacy: dict[str, list[dict]] = defaultdict(list)
    normalized_keys: dict[str, dict] = {}
    skipped_normalize = 0

    for ev in events:
        if not isinstance(ev, dict) or not is_weather_event(ev):
            continue
        slug = (ev.get("slug") or "").lower()
        if not (HIGHEST.search(slug) or LOWEST.search(slug)):
            continue
        title = ev.get("title") or ""
        city = extract_city_slug(title)
        date = extract_event_date(title, ev)
        by_legacy[legacy_key(city, date)].append(
            {"slug": slug, "title": title, "kind": "high" if HIGHEST.search(slug) else "low"}
        )
        norm = normalize_weather_event(ev)
        if norm is None:
            skipped_normalize += 1
            continue
        normalized_keys[norm.storage_key] = {
            "slug": norm.event_slug,
            "market_type": norm.market_type,
            "metric": norm.temperature_metric,
        }

    collisions = {k: v for k, v in by_legacy.items() if len(v) >= 2}
    dup_keys = {k: v for k, v in normalized_keys.items() if list(normalized_keys).count(k) > 1}

    print(f"Temperature events in raw (highest/lowest slugs): {sum(len(v) for v in by_legacy.values())}")
    print(f"Legacy key collisions (city+date with 2+ events): {len(collisions)}")
    print(f"Normalized storage keys: {len(normalized_keys)}")
    print(f"Skipped by normalize_weather_event: {skipped_normalize}")

    key_set = set(normalized_keys)
    still_colliding = 0
    for leg, items in sorted(collisions.items()):
        new_keys = set()
        for item in items:
            # Re-find normalized key by slug
            for sk, meta in normalized_keys.items():
                if meta["slug"] == item["slug"]:
                    new_keys.add(sk)
        if len(new_keys) < len(items):
            still_colliding += 1
            print(f"\nSTILL COLLIDING legacy={leg}:")
            for item in items:
                print(f"  - {item['kind']}: {item['slug']}")
            print(f"  new_keys={new_keys}")

    if still_colliding:
        raise SystemExit(f"FAIL: {still_colliding} legacy groups still map to fewer storage keys")

    print("\nSample fixed pairs (first 8 legacy collisions):")
    for leg in sorted(collisions)[:8]:
        keys = sorted(sk for sk in normalized_keys if sk.startswith(leg + "_"))
        print(f"  {leg} -> {keys}")

    if ACTIVE.exists():
        active = json.loads(ACTIVE.read_text(encoding="utf-8"))
        active_list = active.get("events", [])
        old_style = [
            e.get("storage_key")
            for e in active_list
            if e.get("storage_key")
            and not e["storage_key"].endswith("_high")
            and not e["storage_key"].endswith("_low")
        ]
        print(f"\nActive snapshot events: {len(active_list)}")
        print(f"Keys without _high/_low suffix: {len(old_style)}")
        if old_style and len(old_style) <= 20:
            for k in old_style[:20]:
                print(f"  - {k}")
        elif old_style:
            print(f"  (first 10) {old_style[:10]}")
        missing_high = 0
        for leg in collisions:
            high_key = f"{leg}_high"
            low_key = f"{leg}_low"
            has_high = any(e.get("storage_key") == high_key for e in active_list)
            has_low = any(e.get("storage_key") == low_key for e in active_list)
            if not has_high or not has_low:
                missing_high += 1
        if missing_high:
            print(
                f"\nWARN: {missing_high} collision groups missing _high or _low in active snapshot "
                "(run Refresh discovery to regenerate)"
            )
        else:
            print("\nActive snapshot covers high+low for all raw collision groups (if refresh was run).")

    print("\nAudit OK: new storage keys separate highest/lowest for all colliding city+date pairs.")


if __name__ == "__main__":
    main()
