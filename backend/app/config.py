"""Configuration management for the backend — no hardcoded values."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'cyberrisk.db'}"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = "json"
    model_dir: str = str(REPO_ROOT / "data")


settings = BackendSettings()
