from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Amazon Bot"
    environment: str = "local"
    database_url: str
    app_api_key: str
    amazon_min_discount_percent: Decimal = Decimal("20")
    amazon_partner_tag: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_max_output_tokens: int = 300
    openai_timeout_seconds: float = Field(default=20.0, gt=0)

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 600
    scheduler_delivery_limit: int = 5
    delivery_max_attempts: int = Field(default=3, ge=1)


settings = Settings()
