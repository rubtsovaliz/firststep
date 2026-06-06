"""Settlement time must not use Gamma endDate placeholder."""

import unittest
from datetime import datetime, timezone

from connectors.polymarket.settlement_time import compute_settle_at, hours_until_settle


class TestSettlementTime(unittest.TestCase):
    def test_london_june_5_uses_local_midnight_not_end_date(self) -> None:
        settle = compute_settle_at(
            market_date="2026-06-05",
            city_slug="london",
            game_start_time="2026-06-04 23:00:00+00",
        )
        self.assertIsNotNone(settle)
        assert settle is not None
        self.assertEqual(settle, datetime(2026, 6, 5, 23, 0, tzinfo=timezone.utc))

        now = datetime(2026, 6, 5, 19, 0, tzinfo=timezone.utc)
        hrs = hours_until_settle(settle, now=now)
        self.assertAlmostEqual(hrs, 4.0, places=1)

    def test_end_date_noon_utc_is_not_used(self) -> None:
        """12:00Z endDate at 19:00Z would wrongly show -7h."""
        wrong_end = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
        now = datetime(2026, 6, 5, 19, 0, tzinfo=timezone.utc)
        wrong_hrs = (wrong_end - now).total_seconds() / 3600
        self.assertAlmostEqual(wrong_hrs, -7.0, places=1)

        settle = compute_settle_at(market_date="2026-06-05", city_slug="london")
        hrs = hours_until_settle(settle, now=now)
        self.assertAlmostEqual(hrs, 4.0, places=1)


if __name__ == "__main__":
    unittest.main()
