"""
Configuration management — no hardcoded values in the agent's own code.
Reads from environment variables / a .env file in the agent's working
directory. See .env.example for every supported key.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backend_url: str = "http://localhost:8000"
    device_id_file: str = str(Path.home() / ".cyberrisk_agent" / "device_id")
    request_timeout_seconds: float = 10.0
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "text"


settings = AgentSettings()
