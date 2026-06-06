"""Storage key must not collapse highest/lowest events for same city+date."""

import unittest

from connectors.polymarket.market_normalizer import event_storage_key, normalize_weather_event


class TestEventStorageKey(unittest.TestCase):
    def test_high_and_low_suffixes_differ(self) -> None:
        high = event_storage_key("seoul", "2026-06-05", temperature_metric="high")
        low = event_storage_key("seoul", "2026-06-05", temperature_metric="low")
        self.assertEqual(high, "seoul_2026-06-05_high")
        self.assertEqual(low, "seoul_2026-06-05_low")
        self.assertNotEqual(high, low)

    def test_slug_fallback_when_metric_missing(self) -> None:
        high = event_storage_key(
            "seoul",
            "2026-06-05",
            event_slug="highest-temperature-in-seoul-on-june-5-2026",
        )
        low = event_storage_key(
            "seoul",
            "2026-06-05",
            event_slug="lowest-temperature-in-seoul-on-june-5-2026",
        )
        self.assertEqual(high, "seoul_2026-06-05_high")
        self.assertEqual(low, "seoul_2026-06-05_low")

    def test_event_id_fallback_for_non_temp_same_date(self) -> None:
        a = event_storage_key("seoul", "2026-06-05", "111")
        b = event_storage_key("seoul", "2026-06-05", "222")
        self.assertNotEqual(a, b)

    def test_normalize_highest_and_lowest_seoul_june_5(self) -> None:
        def minimal_event(slug: str, title: str, question: str) -> dict:
            return {
                "id": f"id-{slug}",
                "slug": slug,
                "title": title,
                "active": True,
                "closed": False,
                "endDate": "2026-06-05T12:00:00Z",
                "tags": ["Weather"],
                "markets": [
                    {
                        "id": "m1",
                        "question": question,
                        "outcomePrices": "[0.1,0.9]",
                        "active": True,
                        "closed": False,
                    }
                ],
            }

        highest = normalize_weather_event(
            minimal_event(
                "highest-temperature-in-seoul-on-june-5-2026",
                "Highest temperature in Seoul on June 5?",
                "Will the highest temperature in Seoul be 26°C on June 5?",
            )
        )
        lowest = normalize_weather_event(
            minimal_event(
                "lowest-temperature-in-seoul-on-june-5-2026",
                "Lowest temperature in Seoul on June 5?",
                "Will the lowest temperature in Seoul be 13°C on June 5?",
            )
        )
        self.assertIsNotNone(highest)
        self.assertIsNotNone(lowest)
        assert highest is not None and lowest is not None
        self.assertEqual(highest.storage_key, "seoul_2026-06-05_high")
        self.assertEqual(lowest.storage_key, "seoul_2026-06-05_low")
        self.assertEqual(highest.market_type, "max_temperature")
        self.assertEqual(lowest.market_type, "min_temperature")


if __name__ == "__main__":
    unittest.main()
