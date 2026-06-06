"""Tests for temperature market type normalization."""

import json
import unittest
from pathlib import Path

from connectors.polymarket.stored_event_type import normalize_market_type_from_stored_event
from connectors.polymarket.temperature_type import normalize_market_type

EVENTS_DIR = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "events"


class TestNormalizeMarketType(unittest.TestCase):
    def test_highest_from_title(self) -> None:
        result = normalize_market_type(
            {"event_title": "Highest temperature in Beijing on June 5?"}
        )
        self.assertEqual(result["market_type"], "max_temperature")
        self.assertEqual(result["temperature_metric"], "high")

    def test_highest_from_slug(self) -> None:
        result = normalize_market_type(
            {"event_slug": "highest-temperature-in-beijing-on-june-5-2026"}
        )
        self.assertEqual(result["market_type"], "max_temperature")
        self.assertEqual(result["temperature_metric"], "high")

    def test_highest_from_tags(self) -> None:
        result = normalize_market_type(
            {
                "tags": ["Weather", "Highest temperature"],
                "event_title": "Weather market",
            }
        )
        self.assertEqual(result["market_type"], "max_temperature")
        self.assertEqual(result["temperature_metric"], "high")

    def test_lowest_from_title(self) -> None:
        result = normalize_market_type(
            {"event_title": "Lowest temperature in Austin on June 5?"}
        )
        self.assertEqual(result["market_type"], "min_temperature")
        self.assertEqual(result["temperature_metric"], "low")

    def test_lowest_from_slug(self) -> None:
        result = normalize_market_type(
            {"event_slug": "lowest-temperature-in-austin-on-june-5-2026"}
        )
        self.assertEqual(result["market_type"], "min_temperature")
        self.assertEqual(result["temperature_metric"], "low")

    def test_unknown_weather_event(self) -> None:
        result = normalize_market_type(
            {
                "event_title": "How many inches of rain in Miami on June 5?",
                "tags": ["Weather"],
            }
        )
        self.assertIsNone(result["market_type"])
        self.assertIsNone(result["temperature_metric"])

    def test_existing_valid_market_type_wins(self) -> None:
        result = normalize_market_type(
            {
                "market_type": "min_temperature",
                "event_title": "Highest temperature in Beijing on June 5?",
            }
        )
        self.assertEqual(result["market_type"], "min_temperature")
        self.assertEqual(result["temperature_metric"], "low")

    def test_invalid_existing_market_type_falls_through(self) -> None:
        result = normalize_market_type(
            {
                "market_type": "weather",
                "event_slug": "highest-temperature-in-paris-on-june-1-2026",
            }
        )
        self.assertEqual(result["market_type"], "max_temperature")
        self.assertEqual(result["temperature_metric"], "high")

    def test_slug_priority_over_tags(self) -> None:
        result = normalize_market_type(
            {
                "event_slug": "lowest-temperature-in-denver-on-june-2-2026",
                "tags": ["Highest temperature"],
            }
        )
        self.assertEqual(result["market_type"], "min_temperature")
        self.assertEqual(result["temperature_metric"], "low")

    def test_question_fallback(self) -> None:
        result = normalize_market_type(
            {
                "event_title": "Daily weather market",
                "markets": [
                    {
                        "question": "Will the highest temperature in Denver be 80°F on June 2?",
                    }
                ],
            }
        )
        self.assertEqual(result["market_type"], "max_temperature")
        self.assertEqual(result["temperature_metric"], "high")

    def test_non_temperature_weather_returns_null(self) -> None:
        """Rain/wind markets must not get a temperature market_type."""
        for title in (
            "How many inches of rain in Miami on June 5?",
            "Wind speed in Chicago on June 5?",
            "Total precipitation in Seattle on June 5?",
        ):
            with self.subTest(title=title):
                result = normalize_market_type(
                    {"event_title": title, "tags": ["Weather"]}
                )
                self.assertIsNone(result["market_type"])
                self.assertIsNone(result["temperature_metric"])

    def test_all_outcomes_question_fallback(self) -> None:
        result = normalize_market_type_from_stored_event(
            {
                "event_title": "Daily weather",
                "all_outcomes": [
                    {
                        "question": "Will the lowest temperature in Paris be 8°C on June 4?",
                        "raw_source": {"market_slug": "lowest-temperature-in-paris-8c"},
                    }
                ],
            }
        )
        self.assertEqual(result["market_type"], "min_temperature")
        self.assertEqual(result["temperature_metric"], "low")

    def test_market_slug_fallback_only(self) -> None:
        result = normalize_market_type_from_stored_event(
            {
                "event_title": "Weather market",
                "tags": ["Weather"],
                "all_outcomes": [
                    {
                        "question": "Threshold market",
                        "raw_source": {
                            "market_slug": "highest-temperature-in-beijing-on-june-4-2026-25c"
                        },
                    }
                ],
            }
        )
        self.assertEqual(result["market_type"], "max_temperature")

    def test_real_beijing_stored_event(self) -> None:
        path = EVENTS_DIR / "beijing_2026-06-04.json"
        if not path.exists():
            self.skipTest("beijing snapshot not present")
        record = json.loads(path.read_text(encoding="utf-8"))
        result = normalize_market_type_from_stored_event(record)
        self.assertEqual(result["market_type"], "max_temperature")
        self.assertEqual(result["temperature_metric"], "high")

    def test_real_london_lowest_stored_event(self) -> None:
        path = EVENTS_DIR / "london_2026-06-04.json"
        if not path.exists():
            self.skipTest("london snapshot not present")
        record = json.loads(path.read_text(encoding="utf-8"))
        result = normalize_market_type_from_stored_event(record)
        self.assertEqual(result["market_type"], "min_temperature")
        self.assertEqual(result["temperature_metric"], "low")


if __name__ == "__main__":
    unittest.main()
