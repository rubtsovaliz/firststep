"""Weather forecast connectors (Open-Meteo, etc.)."""

from connectors.forecast.city_config import CityConfig, cities_by_slug, get_city, load_cities
from connectors.forecast.open_meteo_client import OpenMeteoClient, OpenMeteoError
from connectors.forecast.open_meteo_ensemble_client import OpenMeteoEnsembleClient
from connectors.forecast.schemas import DailyTemperatureForecast, DailyTemperaturePoint

__all__ = [
    "CityConfig",
    "DailyTemperatureForecast",
    "DailyTemperaturePoint",
    "OpenMeteoClient",
    "OpenMeteoEnsembleClient",
    "OpenMeteoError",
    "cities_by_slug",
    "get_city",
    "load_cities",
]
