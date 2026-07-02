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
    # Optional cheaper model for the bull/bear debaters; the judge always
    # uses llm_model. Unset -> debaters use llm_model too.
    llm_model_debate: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Safety -- deliberately conservative defaults.
    trading_mode: str = "paper"  # paper | live
    require_human_approval: bool = True
    # Single-user token auth. Unset (default) -> auth disabled for local
    # dev. Set API_TOKEN -> every endpoint except /health and / requires
    # "Authorization: Bearer <token>" (WS: ?token=<token>).
    api_token: str | None = None
    # Alert->research loop: max automatic agent runs per rolling hour across
    # all alerts. Proposals only -- the human approval gate is untouched.
    alert_auto_research_per_hour: int = 4


settings = Settings()
