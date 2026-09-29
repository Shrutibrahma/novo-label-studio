"""Runtime configuration (spec section 4, environment variables)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "1.0.0"
API_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+asyncpg://label:label@localhost:5432/label"
    asset_dir: Path = Path("/data/assets")
    session_ttl_hours: int = 12
    public_base_url: str = "https://localhost:8443"
    font_dir: Path = API_DIR / "fonts"
    # Background loops (lease check, import expiry, session cleanup). Tests switch them off.
    run_scheduler: bool = True
    cookie_secure: bool = True
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
