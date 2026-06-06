"""True weather market settlement time (not Gamma endDate placeholder)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# IANA timezones for Polymarket weather cities (city_slug → tz).
CITY_TIMEZONES: dict[str, str] = {
    "amsterdam": "Europe/Amsterdam",
    "ankara": "Europe/Istanbul",
    "atlanta": "America/New_York",
    "austin": "America/Chicago",
    "beijing": "Asia/Shanghai",
    "buenos-aires": "America/Argentina/Buenos_Aires",
    "busan": "Asia/Seoul",
    "cape-town": "Africa/Johannesburg",
    "chengdu": "Asia/Shanghai",
    "chicago": "America/Chicago",
    "chongqing": "Asia/Shanghai",
    "dallas": "America/Chicago",
    "denver": "America/Denver",
    "guangzhou": "Asia/Shanghai",
    "helsinki": "Europe/Helsinki",
    "hong-kong": "Asia/Hong_Kong",
    "houston": "America/Chicago",
    "istanbul": "Europe/Istanbul",
    "jeddah": "Asia/Riyadh",
    "jinan": "Asia/Shanghai",
    "karachi": "Asia/Karachi",
    "kuala-lumpur": "Asia/Kuala_Lumpur",
    "london": "Europe/London",
    "los-angeles": "America/Los_Angeles",
    "lucknow": "Asia/Kolkata",
    "madrid": "Europe/Madrid",
    "manila": "Asia/Manila",
    "mexico-city": "America/Mexico_City",
    "miami": "America/New_York",
    "milan": "Europe/Rome",
    "moscow": "Europe/Moscow",
    "munich": "Europe/Berlin",
    "nyc": "America/New_York",
    "new-york": "America/New_York",
    "panama-city": "America/Panama",
    "paris": "Europe/Paris",
    "qingdao": "Asia/Shanghai",
    "san-francisco": "America/Los_Angeles",
    "sao-paulo": "America/Sao_Paulo",
    "seattle": "America/Los_Angeles",
    "seoul": "Asia/Seoul",
    "shanghai": "Asia/Shanghai",
    "shenzhen": "Asia/Shanghai",
    "singapore": "Asia/Singapore",
    "taipei": "Asia/Taipei",
    "tel-aviv": "Asia/Jerusalem",
    "tokyo": "Asia/Tokyo",
    "toronto": "America/Toronto",
    "warsaw": "Europe/Warsaw",
    "wellington": "Pacific/Auckland",
    "wuhan": "Asia/Shanghai",
    "zhengzhou": "Asia/Shanghai",
}


def city_timezone(city_slug: str | None) -> str | None:
    if not city_slug:
        return None
    return CITY_TIMEZONES.get(city_slug.strip().lower())


def _parse_market_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except ValueError:
        return None


def _parse_game_start_time(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    elif s.endswith("+00"):
        s = s + ":00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def compute_settle_at(
    *,
    market_date: str | None,
    city_slug: str | None,
    game_start_time: str | None = None,
) -> datetime | None:
    """
    End of the market's local calendar day in UTC.

    Gamma ``endDate`` (often 12:00 UTC) is a placeholder — not the settle moment.
    """
    city_tz = city_timezone(city_slug)
    if not city_tz:
        return None
    try:
        tz = ZoneInfo(city_tz)
    except ZoneInfoNotFoundError:
        return None

    settle_date: date | None = None
    gst_dt = _parse_game_start_time(game_start_time)
    if gst_dt is not None:
        settle_date = gst_dt.astimezone(tz).date()

    if settle_date is None:
        settle_date = _parse_market_date(market_date)
    if settle_date is None:
        return None

    local_next_midnight = datetime.combine(
        settle_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=tz,
    )
    return local_next_midnight.astimezone(timezone.utc)


def hours_until_settle(
    settle_at: datetime | None,
    *,
    now: datetime | None = None,
) -> float | None:
    if settle_at is None:
        return None
    current = now or datetime.now(timezone.utc)
    if settle_at.tzinfo is None:
        settle_at = settle_at.replace(tzinfo=timezone.utc)
    return round((settle_at - current).total_seconds() / 3600, 1)


def enrich_settlement_fields(
    data: dict,
    *,
    markets: list[dict] | None = None,
) -> dict:
    """Add settle_at + hours_to_settle to an event dict (mutates copy)."""
    game_start = data.get("game_start_time")
    if not game_start and markets:
        first = markets[0] if markets else {}
        if isinstance(first, dict):
            game_start = first.get("gameStartTime")
    if not game_start:
        raw = data.get("raw_source") or {}
        if isinstance(raw, dict):
            game_start = raw.get("game_start_time")

    settle_at = compute_settle_at(
        market_date=data.get("date"),
        city_slug=data.get("city_slug"),
        game_start_time=game_start,
    )
    if settle_at is not None:
        data["settle_at"] = settle_at.isoformat()
        data["hours_to_settle"] = hours_until_settle(settle_at)
    else:
        data.setdefault("settle_at", None)
        data.setdefault("hours_to_settle", None)
    return data
