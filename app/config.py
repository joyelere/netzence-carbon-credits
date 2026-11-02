"""App settings, read from environment / .env (like Laravel's config/*.php + .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://netzence:netzence@localhost:5432/netzence"
    app_name: str = "Netzence Carbon Credits"


settings = Settings()
