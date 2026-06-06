"""Defensive Pydantic models for Gamma API responses."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GammaTag(BaseModel):
    """Tag attached to a Gamma event."""

    model_config = ConfigDict(extra="allow")

    id: str | int | None = None
    slug: str | None = None
    label: str | None = None


class GammaMarket(BaseModel):
    """Single market nested under a Gamma event.

    Note: Gamma API uses camelCase (e.g. outcomePrices). Normalizer maps to
    snake_case yes_price / no_price on WeatherOutcome for storage and UI.
    """

    model_config = ConfigDict(extra="allow")

    id: str | int | None = None
    slug: str | None = None
    question: str | None = None
    description: str | None = None
    active: bool | None = None
    closed: bool | None = None
    endDate: str | None = None
    volume: float | str | None = None
    liquidity: float | str | None = None
    category: str | None = None
    outcomes: list[str] | str | None = None
    outcomePrices: list[float] | str | None = None
    clobTokenIds: list[str] | str | None = None
    conditionId: str | None = None
    resolutionSource: str | None = None

    @field_validator("outcomes", "outcomePrices", "clobTokenIds", mode="before")
    @classmethod
    def parse_json_string_lists(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value


class GammaEvent(BaseModel):
    """Gamma event containing nested markets."""

    model_config = ConfigDict(extra="allow")

    id: str | int | None = None
    slug: str | None = None
    title: str | None = None
    description: str | None = None
    active: bool | None = None
    closed: bool | None = None
    endDate: str | None = None
    volume: float | str | None = None
    liquidity: float | str | None = None
    category: str | None = None
    tags: list[GammaTag | dict[str, Any] | str] | None = None
    markets: list[GammaMarket | dict[str, Any]] | None = None
