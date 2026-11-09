import logging
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Every source app.sources.registry can build.
SourceName = Literal["mock", "shopee", "aliexpress"]


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
    app_name: str = "Promotion Bot"
    environment: str = "local"
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # --- database ---
    database_url: str

    # --- api auth ---
    app_api_key: str

    # --- collection ---
    # NoDecode: read as "mock,shopee" rather than as a JSON list.
    promotion_sources: Annotated[list[SourceName], NoDecode] = Field(
        default_factory=lambda: ["mock"]
    )
    min_discount_percent: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    dedup_window_hours: int = Field(default=24, gt=0)

    # --- amazon ---
    amazon_partner_tag: str = ""

    # --- shopee ---
    shopee_app_id: str = ""
    shopee_secret: str = ""
    shopee_keywords: Annotated[list[str], NoDecode] = Field(default_factory=list)
    shopee_items_per_keyword: int = Field(default=10, ge=1, le=50)

    # --- aliexpress ---
    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    aliexpress_tracking_id: str = ""
    aliexpress_keywords: Annotated[list[str], NoDecode] = Field(default_factory=list)
    aliexpress_items_per_keyword: int = Field(default=10, ge=1, le=50)

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

    @field_validator("promotion_sources", mode="before")
    @classmethod
    def _split_sources(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [name.lower() for name in _split_list(value)]
        return value

    @field_validator("shopee_keywords", "aliexpress_keywords", mode="before")
    @classmethod
    def _split_keywords(cls, value: Any) -> Any:
        return _split_list(value) if isinstance(value, str) else value

    @field_validator("promotion_sources")
    @classmethod
    def _no_repeated_sources(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("a promotion source is listed more than once")
        return value

    @model_validator(mode="after")
    def _enabled_sources_are_configured(self) -> Self:
        required = {
            "shopee": {
                "SHOPEE_APP_ID": self.shopee_app_id,
                "SHOPEE_SECRET": self.shopee_secret,
                "SHOPEE_KEYWORDS": self.shopee_keywords,
            },
            "aliexpress": {
                "ALIEXPRESS_APP_KEY": self.aliexpress_app_key,
                "ALIEXPRESS_APP_SECRET": self.aliexpress_app_secret,
                "ALIEXPRESS_TRACKING_ID": self.aliexpress_tracking_id,
                "ALIEXPRESS_KEYWORDS": self.aliexpress_keywords,
            },
        }
        for source, values in required.items():
            missing = [name for name, value in values.items() if not value]
            if source in self.promotion_sources and missing:
                raise ValueError(
                    f"PROMOTION_SOURCES includes {source} but "
                    f"{', '.join(missing)} is not set"
                )
        return self

    @model_validator(mode="after")
    def _scheduler_never_posts_mock_products(self) -> Self:
        if self.scheduler_enabled and "mock" in self.promotion_sources:
            raise ValueError(
                "SCHEDULER_ENABLED=true with the mock source would post "
                "fictitious products; remove mock from PROMOTION_SOURCES"
            )
        return self

    @field_validator("scheduler_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown timezone: {value!r}") from error
        return value


def _split_list(value: str) -> list[str]:
    """ "a, b ,," -> ["a", "b"]: how list settings are written in .env."""
    return [item.strip() for item in value.split(",") if item.strip()]


settings = Settings()
