"""Load city registry from config/cities.yaml for Open-Meteo forecast lookups."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CITIES_PATH = ROOT / "config" / "cities.yaml"
DEFAULT_DAILY_VARS = ("temperature_2m_max", "temperature_2m_min")


@dataclass(frozen=True)
class CityConfig:
    slug: str
    name: str
    icao: str
    lat: float
    lon: float
    tz: str
    unit: str
    models: str
    daily: tuple[str, ...] = DEFAULT_DAILY_VARS
    ensemble_models: tuple[str, ...] = ("ecmwf_ifs025_ensemble",)
    fallback_models: str | None = None


def _parse_daily_vars(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return DEFAULT_DAILY_VARS
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple)):
        vars_ = tuple(str(var) for var in raw if var)
        return vars_ if vars_ else DEFAULT_DAILY_VARS
    return (str(raw),)


def _parse_ensemble_models(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ("ecmwf_ifs025_ensemble",)
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple)):
        models = tuple(str(model) for model in raw if model)
        return models if models else ("ecmwf_ifs025_ensemble",)
    return (str(raw),)


def _parse_city(raw: dict[str, Any]) -> CityConfig:
    fallback = raw.get("fallback_models")
    ensemble = _parse_ensemble_models(raw.get("ensemble_models"))
    return CityConfig(
        slug=str(raw["slug"]),
        name=str(raw["name"]),
        icao=str(raw["icao"]),
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        tz=str(raw["tz"]),
        unit=str(raw["unit"]),
        models=str(raw["models"]),
        daily=_parse_daily_vars(raw.get("daily")),
        ensemble_models=ensemble,
        fallback_models=str(fallback) if fallback else None,
    )


@lru_cache
def load_cities(path: Path | None = None) -> tuple[CityConfig, ...]:
    cfg_path = path or CITIES_PATH
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return tuple(_parse_city(c) for c in data.get("cities", []))


@lru_cache
def cities_by_slug(path: Path | None = None) -> dict[str, CityConfig]:
    return {c.slug: c for c in load_cities(path)}


def get_city(slug: str, path: Path | None = None) -> CityConfig | None:
    return cities_by_slug(path).get(slug.strip().lower())
