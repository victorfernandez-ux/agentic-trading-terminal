"""LLM client — OpenRouter via the OpenAI-compatible API.

OpenRouter exposes an OpenAI-compatible endpoint, so we use the official
`openai` async client with a custom base_url. Swapping models is just a
config change (settings.llm_model), e.g. deepseek/deepseek-v4-flash.
"""

from __future__ import annotations

import contextlib
import json
from contextvars import ContextVar
from functools import lru_cache

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from app.config import settings


class LLMNotConfigured(RuntimeError):
    """Raised when no API key is available for the selected provider."""


class LLMResponseError(RuntimeError):
    """Model returned empty/unparseable output even after the retry (G2).
    Callers surface this through the standard error envelope instead of
    silently proceeding on garbage."""


# ── Per-run usage tracking (roadmap G1) ─────────────────────────────────
# A ContextVar collector: the run wrapper opens track_usage(), every
# complete_json inside that context appends its token usage, and the run
# summarizes without any caller signature changing. Child asyncio tasks
# inherit the context copy, which carries the SAME list object — appends
# from graph nodes are visible to the run.

_usage_collector: ContextVar[list | None] = ContextVar("llm_usage", default=None)

# Approximate $ per 1M tokens (input, output), longest-prefix match.
# A static table by design (the field-review lesson: provider-reported
# tokens with no price estimate leave you multiplying by hand) — update
# alongside model changes; unknown models report tokens with cost None.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-v4-flash": (0.07, 0.28),
    "deepseek/": (0.27, 1.10),
    "anthropic/": (3.00, 15.00),
    "openai/gpt-4": (2.50, 10.00),
    "openai/": (0.50, 1.50),
    "google/": (0.30, 1.20),
    "meta-llama/": (0.20, 0.60),
    "qwen/": (0.20, 0.60),
}


@contextlib.contextmanager
def track_usage():
    """Collect usage for every complete_json call made inside the block."""
    entries: list[dict] = []
    token = _usage_collector.set(entries)
    try:
        yield entries
    finally:
        _usage_collector.reset(token)


def _price_for(model: str) -> tuple[float, float] | None:
    best = None
    for prefix, price in PRICES_PER_MTOK.items():
        if model.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, price)
    return best[1] if best else None


def summarize_usage(entries: list[dict]) -> dict:
    """Aggregate collected usage into tokens + estimated cost per model."""
    by_model: dict[str, dict] = {}
    for e in entries:
        m = by_model.setdefault(e["model"], {"calls": 0, "prompt_tokens": 0,
                                             "completion_tokens": 0})
        m["calls"] += 1
        m["prompt_tokens"] += e.get("prompt_tokens") or 0
        m["completion_tokens"] += e.get("completion_tokens") or 0
    total_cost, any_unknown = 0.0, False
    for model, m in by_model.items():
        price = _price_for(model)
        if price is None:
            m["est_cost_usd"] = None
            any_unknown = True
        else:
            cost = (m["prompt_tokens"] * price[0]
                    + m["completion_tokens"] * price[1]) / 1_000_000
            m["est_cost_usd"] = round(cost, 6)
            total_cost += cost
    return {
        "calls": sum(m["calls"] for m in by_model.values()),
        "prompt_tokens": sum(m["prompt_tokens"] for m in by_model.values()),
        "completion_tokens": sum(m["completion_tokens"] for m in by_model.values()),
        # None whenever ANY model is unpriced — a partial total reads as
        # "the whole run cost this", which is worse than unknown.
        "est_cost_usd": None if any_unknown else round(total_cost, 6),
        "by_model": by_model,
    }


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    """Build the async client for the configured provider.

    Defaults to OpenRouter. Anthropic/OpenAI direct or a local Ollama
    endpoint can be selected via settings.llm_provider.
    """
    provider = settings.llm_provider
    # Deadline + transient retry on every client (H1a): a hung provider
    # connection must fail the call, not the whole agent run. The SDK
    # retries connect errors / 429 / 5xx itself up to llm_max_retries.
    opts = {"timeout": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries}
    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise LLMNotConfigured("OPENROUTER_API_KEY is not set")
        return AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            **opts,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise LLMNotConfigured("OPENAI_API_KEY is not set")
        return AsyncOpenAI(api_key=settings.openai_api_key, **opts)
    if provider == "ollama":
        return AsyncOpenAI(api_key="ollama", base_url="http://localhost:11434/v1",
                           **opts)
    raise LLMNotConfigured(f"Unsupported provider: {provider}")


def is_configured() -> bool:
    try:
        get_client()
        return True
    except LLMNotConfigured:
        return False


def _parse_json_object(content: str) -> dict | None:
    """Parse a JSON object, tolerating prose/fence wrapping. None = failed."""
    try:
        out = json.loads(content)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            try:
                out = json.loads(content[start:end + 1])
                return out if isinstance(out, dict) else None
            except json.JSONDecodeError:
                return None
        return None


async def complete_json(system: str, user: str, *, temperature: float = 0.2,
                        model: str | None = None) -> dict:
    """Call the model and parse a JSON object from the response.

    We instruct the model to return JSON and request response_format json
    when supported; we still defensively parse in case a model ignores it.
    `model` overrides settings.llm_model per call (e.g. cheap debaters).

    Robustness (roadmap G2): an empty or unparseable reply gets exactly
    ONE retry with the failure described in the prompt; a second failure
    raises LLMResponseError — loud beats garbage.
    """
    client = get_client()
    used_model = model or settings.llm_model
    user_payload = user
    failure = ""
    for attempt in range(2):
        try:
            resp = await client.chat.completions.create(
                model=used_model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_payload},
                ],
                response_format={"type": "json_object"},
            )
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            # The SDK already retried transient failures (H1a); surface the
            # final failure as the same typed error the content path uses,
            # so every caller hits one error envelope — and never a hang.
            raise LLMResponseError(
                f"model {used_model} unreachable: {type(e).__name__}") from e
        except APIStatusError as e:
            raise LLMResponseError(
                f"model {used_model} provider error {e.status_code}") from e
        # Usage capture (G1): provider-reported tokens into the ambient
        # collector, if a run is tracking. Retries are paid calls — count
        # every attempt. Never breaks the call.
        entries = _usage_collector.get()
        usage = getattr(resp, "usage", None)
        if entries is not None and usage is not None:
            entries.append({"model": used_model,
                            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0})
        content = (resp.choices[0].message.content or "").strip()
        if content:
            parsed = _parse_json_object(content)
            if parsed is not None:
                return parsed
            failure = "your reply was not a parseable JSON object"
        else:
            failure = "your reply was empty"
        if attempt == 0:
            user_payload = (
                user + "\n\nIMPORTANT: your previous reply failed ({f}). "
                "Respond again with ONLY a single valid JSON object — no "
                "prose, no code fences.".format(f=failure)
            )
    raise LLMResponseError(
        "model {m} failed twice: {f}".format(m=used_model, f=failure))
