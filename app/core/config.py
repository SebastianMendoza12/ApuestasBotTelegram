from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Aplicación
    app_name: str = "Bot de Apuestas Telegram"
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    # Base de Datos
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/bot_apuestas",
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT")

    # Telegram Bot
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_url: str | None = Field(default=None, alias="TELEGRAM_WEBHOOK_URL")
    telegram_webhook_secret: str | None = Field(default=None, alias="TELEGRAM_WEBHOOK_SECRET")
    telegram_allowed_updates: list[str] = Field(
        default=["message", "callback_query", "inline_query"],
        alias="TELEGRAM_ALLOWED_UPDATES",
    )

    # Redis (para caché/sesiones)
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Seguridad
    secret_key: str = Field(..., alias="SECRET_KEY", min_length=32)
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # APIs externas (datos deportivos, cuotas)
    odds_api_key: str | None = Field(default=None, alias="ODDS_API_KEY")
    odds_api_base_url: str = Field(default="https://api.the-odds-api.com", alias="ODDS_API_BASE_URL")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


settings = Settings()