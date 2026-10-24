"""Application configuration settings."""

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "stockwise.db"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STOCKWISE_",
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    env: str = Field(default="development")
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=True)
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    database_url: str = Field(
        default=f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    )
    simulator_seed: int = Field(default=42)
    num_products: int = Field(default=16)
    num_warehouses: int = Field(default=4)
    num_destinations: int = Field(default=50)
    demand_history_days: int = Field(default=120)

settings = Settings()
