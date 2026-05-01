"""
src/config/settings.py

Loads platform configuration from environment variables / .env file.
This module is the single source of truth for all configuration in the platform.
"""

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration loaded from .env or environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenRouter
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )

    # Saleor
    saleor_url: AnyHttpUrl = Field(
        default="http://localhost:8000",
        description="Base URL for the Saleor instance",
    )
    saleor_graphql_url: AnyHttpUrl = Field(
        default="http://localhost:8000/graphql/",
        description="Saleor GraphQL endpoint URL",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Python logging level")


def get_settings() -> Settings:
    """Return a fully validated Settings instance loaded from the environment."""
    return Settings()
