from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RELIABILITY_LAB_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = (
        "postgresql://reliability:local-development-only@localhost:5434/reliability"
    )
    cache_url: str = "redis://localhost:6381/0"
    pool_min_size: int = Field(default=2, ge=1, le=50)
    pool_max_size: int = Field(default=10, ge=1, le=100)
    pool_timeout_seconds: float = Field(default=2, ge=0.1, le=30)
    query_timeout_ms: int = Field(default=2000, ge=100, le=60000)
    cache_ttl_seconds: int = Field(default=30, ge=1, le=3600)
    stale_if_error_seconds: int = Field(default=300, ge=1, le=86400)
    cache_failure_threshold: int = Field(default=3, ge=1, le=100)
    cache_recovery_seconds: int = Field(default=10, ge=1, le=3600)
    idle_transaction_seconds: int = Field(default=30, ge=5, le=86400)
    remediation_max_terminations: int = Field(default=2, ge=1, le=20)
    remediation_interval_seconds: int = Field(default=5, ge=1, le=3600)
    fault_application_prefix: str = "reliability-lab-fault-"


@lru_cache
def get_settings() -> Settings:
    return Settings()
