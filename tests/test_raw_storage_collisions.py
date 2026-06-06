"""Integration: all highest+lowest pairs in raw Gamma get distinct storage keys."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from connectors.polymarket.market_normalizer import normalize_weather_event
from connectors.polymarket.weather_market_filter import is_weather_event

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "gamma_events_raw.json"

HIGHEST = re.compile(r"highest-temperature", re.I)
LOWEST = re.compile(r"lowest-temperature", re.I)


@unittest.skipUnless(RAW.exists(), "gamma_events_raw.json missing — run discovery first")
class TestRawStorageCollisions(unittest.TestCase):
    def test_no_legacy_key_collisions_after_normalize(self) -> None:
        data = json.loads(RAW.read_text(encoding="utf-8"))
        by_slug: dict[str, str] = {}
        legacy_groups: dict[str, list[str]] = {}

        for ev in data.get("events", []):
            if not isinstance(ev, dict) or not is_weather_event(ev):
                continue
            slug = (ev.get("slug") or "").lower()
            if not (HIGHEST.search(slug) or LOWEST.search(slug)):
                continue
            norm = normalize_weather_event(ev)
            self.assertIsNotNone(norm, msg=f"failed normalize: {slug}")
            assert norm is not None
            if norm.event_slug in by_slug:
                self.fail(f"duplicate event_slug storage: {norm.event_slug}")
            by_slug[norm.event_slug or ""] = norm.storage_key

            # legacy key = city_date without suffix
            legacy = norm.storage_key
            for suffix in ("_high", "_low"):
                if legacy.endswith(suffix):
                    legacy = legacy[: -len(suffix)]
                    break
            legacy_groups.setdefault(legacy, []).append(norm.storage_key)

        multi = {k: v for k, v in legacy_groups.items() if len(v) >= 2}
        for leg, keys in multi.items():
            self.assertGreaterEqual(
                len(set(keys)),
                2,
                msg=f"legacy {leg} collapsed to {keys}",
            )
            self.assertTrue(
                any(k.endswith("_high") for k in keys) or any(k.endswith("_low") for k in keys),
                msg=f"legacy {leg} missing high/low suffix: {keys}",
            )


if __name__ == "__main__":
    unittest.main()
