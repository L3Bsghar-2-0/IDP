"""Application settings, loaded from .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # MQTT
    mqtt_host: str = Field(default="localhost", alias="MQTT_HOST")
    mqtt_port: int = Field(default=8883, alias="MQTT_PORT")
    mqtt_username: str = Field(default="python-server", alias="MQTT_USERNAME")
    mqtt_password: str = Field(default="", alias="MQTT_PASSWORD")
    mqtt_client_id: str = Field(default="reteqfusion-server-01", alias="MQTT_CLIENT_ID")
    mqtt_tls: bool = Field(default=True, alias="MQTT_TLS")
    mqtt_keepalive: int = Field(default=60, alias="MQTT_KEEPALIVE")

    # Database
    postgres_host: str = Field(default="timescaledb", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="reteqfusion", alias="POSTGRES_DB")
    postgres_user: str = Field(default="reteq", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    database_url: str = Field(
        default="postgresql://reteq:reteq_secret_2025@timescaledb:5432/reteqfusion",
        alias="DATABASE_URL",
    )

    # Grafana
    grafana_admin_password: str = Field(
        default="admin", alias="GRAFANA_ADMIN_PASSWORD"
    )

    # App
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_port: int = Field(default=8000, alias="API_PORT")

    # MQ-2 thresholds (ppm)
    mq2_smoke_alarm_ppm: int = Field(default=1000, alias="MQ2_SMOKE_ALARM_PPM")
    mq2_hazard_ppm: int = Field(default=3000, alias="MQ2_HAZARD_PPM")

    # Default tenant/site for server-published alerts
    alert_tenant: str = Field(default="demo", alias="ALERT_TENANT")
    alert_site: str = Field(default="lab", alias="ALERT_SITE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()
