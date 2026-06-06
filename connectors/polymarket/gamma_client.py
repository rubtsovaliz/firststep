"""Low-level HTTP client for Polymarket Gamma API."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from connectors.polymarket.schemas import GammaEvent

logger = logging.getLogger(__name__)


class GammaClient:
    """Read-only Gamma API client with pagination and safe retries."""

    def __init__(
        self,
        base_url: str = "https://gamma-api.polymarket.com",
        timeout_seconds: float = 30.0,
        page_limit: int = 100,
        max_pages: int = 50,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.page_limit = page_limit
        self.max_pages = max_pages
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(url, params=params or {})
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(
                    "Gamma request failed (attempt %s/%s): %s %s",
                    attempt + 1,
                    self.max_retries,
                    url,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))

        raise RuntimeError(f"Gamma API request failed: {url}") from last_error

    def fetch_events_page(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        active: bool = True,
        closed: bool = False,
        tag_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a single page of events from /events."""
        params: dict[str, Any] = {
            "limit": limit or self.page_limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": "id",
            "ascending": "false",
        }
        if tag_slug:
            params["tag_slug"] = tag_slug

        data = self._request("/events", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items = data.get("data") or data.get("events") or []
            return items if isinstance(items, list) else []
        return []

    def fetch_active_events(
        self,
        *,
        tag_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        """Paginate through active open events."""
        all_events: list[dict[str, Any]] = []

        for page in range(self.max_pages):
            offset = page * self.page_limit
            batch = self.fetch_events_page(offset=offset, tag_slug=tag_slug)
            if not batch:
                break
            all_events.extend(batch)
            if len(batch) < self.page_limit:
                break

        logger.info("Fetched %s events from Gamma API", len(all_events))
        return all_events

    def fetch_event_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Fetch a single event by slug (used by legacy bots)."""
        data = self._request("/events", params={"slug": slug})
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return None

    def fetch_market(self, market_id: str | int) -> dict[str, Any]:
        """Fetch a single market by id."""
        return self._request(f"/markets/{market_id}")

    def parse_events(self, raw_events: list[dict[str, Any]]) -> list[GammaEvent]:
        """Best-effort parse raw events into GammaEvent models."""
        parsed: list[GammaEvent] = []
        for item in raw_events:
            try:
                parsed.append(GammaEvent.model_validate(item))
            except Exception as exc:
                logger.debug("Skipping unparsable event: %s", exc)
        return parsed
