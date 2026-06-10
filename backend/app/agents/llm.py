"""LLM client — OpenRouter via the OpenAI-compatible API.

OpenRouter exposes an OpenAI-compatible endpoint, so we use the official
`openai` async client with a custom base_url. Swapping models is just a
config change (settings.llm_model), e.g. deepseek/deepseek-v4-flash.
"""

from __future__ import annotations

import json
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


class LLMNotConfigured(RuntimeError):
    """Raised when no API key is available for the selected provider."""


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    """Build the async client for the configured provider.

    Defaults to OpenRouter. Anthropic/OpenAI direct or a local Ollama
    endpoint can be selected via settings.llm_provider.
    """
    provider = settings.llm_provider
    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise LLMNotConfigured("OPENROUTER_API_KEY is not set")
        return AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise LLMNotConfigured("OPENAI_API_KEY is not set")
        return AsyncOpenAI(api_key=settings.openai_api_key)
    if provider == "ollama":
        return AsyncOpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
    raise LLMNotConfigured(f"Unsupported provider: {provider}")


def is_configured() -> bool:
    try:
        get_client()
        return True
    except LLMNotConfigured:
        return False


async def complete_json(system: str, user: str, *, temperature: float = 0.2) -> dict:
    """Call the model and parse a JSON object from the response.

    We instruct the model to return JSON and request response_format json
    when supported; we still defensively parse in case a model ignores it.
    """
    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Some models wrap JSON in prose or fences; extract the first object.
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(content[start : end + 1])
        return {"raw": content}
