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
    # Client-side deadline per LLM API call (H1a). Without it a hung
    # provider connection stalls an agent run indefinitely.
    llm_timeout_seconds: float = 60.0
    # SDK-level retries for transient failures (connect errors, 429, 5xx).
    llm_max_retries: int = 1

    # Safety -- deliberately conservative defaults.
    trading_mode: str = "paper"  # paper | live
    require_human_approval: bool = True
    # Single-user token auth. Unset (default) -> auth disabled for local
    # dev. Set API_TOKEN -> every endpoint except /health and / requires
    # "Authorization: Bearer <token>"; ?token=<token> is accepted too for
    # clients that can't set headers (WS, SSE EventSource).
    api_token: str | None = None
    # Comma-separated browser origins allowed by CORS and by the CSRF
    # write guard. Both loopback spellings are included — a browser on
    # 127.0.0.1:3000 sends that exact Origin, and treating it as foreign
    # would 403 every UI write (found in live verification).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Alert->research loop: max automatic agent runs per rolling hour across
    # all alerts. Proposals only -- the human approval gate is untouched.
    alert_auto_research_per_hour: int = 4
    # Manual agent-run cost cap (H-2, from the security audit): max
    # human-triggered /agents/research|propose runs per rolling hour. Each
    # run is several paid LLM calls; the automated loops were already
    # capped, this closes the manual path. 0 disables the cap.
    manual_research_per_hour: int = 30
    # Reflection memory: how many past-round-trip lessons per symbol are
    # injected into the debate evidence. 0 disables injection.
    reflections_limit: int = 5
    # Scan->research loop: screener top hit feeds run_propose. The hourly
    # cap is counted from the audit trail (crash-safe); the background
    # schedule is opt-in — on-demand POST /research/scan/run always works.
    scan_auto_research_per_hour: int = 2
    scan_auto_research_enabled: bool = False
    scan_interval_minutes: int = 60
    scan_screen: str = "composite_bullish"
    scan_universe: str = "sp100"
    # Backtest run cards (roadmap B1): artifact directory, gitignored.
    runs_dir: str = ".private/runs"
    # Audit write-ahead fallback (H5b): where events land if the DB write
    # fails. None -> "<runs_dir>/audit-wal.jsonl".
    audit_wal_file: str | None = None
    # Kill switch (roadmap F3): if this file exists, every broker
    # submission raises TradingHalted. `touch` it to halt, delete to resume.
    kill_switch_file: str = ".private/KILL_SWITCH"
    # Telegram notifications (roadmap E2): off unless BOTH are set.
    # Informational only — approval always happens in the app.
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    # Link target used in notification messages (the PWA/terminal URL).
    public_base_url: str = "http://localhost:3000"


settings = Settings()
