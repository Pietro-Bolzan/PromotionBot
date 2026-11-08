import logging
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration read from the environment and from .env.

    Grouped in the same order as .env.example, which documents every field.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # .env is shared with docker-compose.yml (POSTGRES_*), so keys that are
        # not fields here are ignored rather than rejected. Required fields still
        # fail loudly when missing.
        extra="ignore",
    )

    # --- application ---
    app_name: str = "Amazon Bot"
    environment: str = "local"
    log_level: str = "INFO"

    # --- database ---
    database_url: str

    # --- api auth ---
    app_api_key: str

    # --- amazon ---
    amazon_min_discount_percent: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    amazon_partner_tag: str = ""

    # --- openai ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_max_output_tokens: int = Field(default=300, gt=0)
    openai_timeout_seconds: float = Field(default=20.0, gt=0)

    # --- telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- scheduler ---
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = Field(default=600, gt=0)
    scheduler_delivery_limit: int = Field(default=5, ge=1)
    scheduler_timezone: str = "America/Sao_Paulo"

    # --- delivery ---
    delivery_max_attempts: int = Field(default=3, ge=1)

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError(f"unknown log level: {value!r}")
        return level

    @field_validator("scheduler_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown timezone: {value!r}") from error
        return value


settings = Settings()
