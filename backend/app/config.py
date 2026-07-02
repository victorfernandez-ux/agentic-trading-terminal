"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    # Datastores
    database_url: str = "postgresql+psycopg://trader:trader@localhost:5432/terminal"
    redis_url: str = "redis://localhost:6379/0"

    # Market data
    polygon_api_key: str | None = None
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_paper: bool = True

    # LLM -- OpenRouter by default (OpenAI-compatible; swap models freely).
    llm_provider: str = "openrouter"  # openrouter | anthropic | openai | ollama
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "deepseek/deepseek-v4-flash"
    # Optional per-role overrides for the bull/bear debate. Default (None) =>
    # fall back to llm_model. Pattern from TradingAgents: cheap debaters, a
    # stronger judge that must commit to a directional call.
    llm_debater_model: str | None = None
    llm_judge_model: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Safety -- deliberately conservative defaults.
    trading_mode: str = "paper"  # paper | live
    require_human_approval: bool = True

    # Single-user API token. When unset (default), auth is DISABLED so local
    # dev and tests work unchanged. Set it to require a Bearer / X-API-Token
    # header on the action routes (orders, alerts, agents).
    api_token: str | None = None


settings = Settings()
