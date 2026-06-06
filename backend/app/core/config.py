"""Application configuration from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for backend and snapshot paths."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    gamma_page_limit: int = 100
    gamma_max_pages: int = 50
    request_timeout_seconds: float = 30.0
    snapshot_dir: Path = Path("data/snapshots")
    raw_dir: Path = Path("data/raw")
    events_snapshot_dir: Path = Path("data/snapshots/events")
    markets_snapshot_dir: Path = Path("data/snapshots/events")
    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"

    @property
    def raw_events_path(self) -> Path:
        return self.raw_dir / "gamma_events_raw.json"

    @property
    def active_events_path(self) -> Path:
        return self.snapshot_dir / "active_weather_events.json"

    @property
    def active_markets_path(self) -> Path:
        """Legacy path alias."""
        return self.active_events_path

    @property
    def discovery_status_path(self) -> Path:
        return self.snapshot_dir / "discovery_status.json"


def get_settings() -> Settings:
    return Settings()
