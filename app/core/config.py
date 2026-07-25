from pydantic_settings import BaseSettings, SettingsConfigDict
from decimal import Decimal

class Settings(BaseSettings):
    app_name: str = "Amazon Bot"
    environment: str = "local"
    database_url: str
    app_api_key: str
    amazon_min_discount_percent: Decimal = Decimal("20")
    
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_max_output_tokens: int = 300
    
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )
    
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 600
    scheduler_delivery_limit: int = 5
  
settings = Settings()