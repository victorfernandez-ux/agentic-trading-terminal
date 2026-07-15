"""LLM call robustness (roadmap G2): one bounded retry on empty or
unparseable output, then a typed failure. Stubbed client, no network."""

from types import SimpleNamespace

import pytest

from app.agents import llm


def _client(replies):
    """Stub whose create() pops scripted reply strings; records prompts."""
    calls = []

    class _Completions:
        async def create(self, **kw):
            calls.append(kw)
            content = replies.pop(0)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    stub = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    return stub, calls


async def test_valid_first_reply_single_call(monkeypatch):
    stub, calls = _client(['{"ok": true}'])
    monkeypatch.setattr(llm, "get_client", lambda: stub)
    assert await llm.complete_json(system="s", user="u") == {"ok": True}
    assert len(calls) == 1


async def test_empty_reply_retried_with_error_in_prompt(monkeypatch):
    stub, calls = _client(["", '{"ok": true}'])
    monkeypatch.setattr(llm, "get_client", lambda: stub)
    out = await llm.complete_json(system="s", user="question?")
    assert out == {"ok": True}
    assert len(calls) == 2
    retry_user = calls[1]["messages"][1]["content"]
    assert "question?" in retry_user and "reply was empty" in retry_user


async def test_prose_reply_retried_then_parsed(monkeypatch):
    stub, calls = _client(["I think probably yes!", 'fine: {"d": 1} done'])
    monkeypatch.setattr(llm, "get_client", lambda: stub)
    out = await llm.complete_json(system="s", user="u")
    assert out == {"d": 1}  # brace extraction still tolerated
    assert "not a parseable JSON object" in calls[1]["messages"][1]["content"]


async def test_double_failure_raises_typed_error(monkeypatch):
    stub, calls = _client(["", "  "])
    monkeypatch.setattr(llm, "get_client", lambda: stub)
    with pytest.raises(llm.LLMResponseError, match="failed twice"):
        await llm.complete_json(system="s", user="u")
    assert len(calls) == 2  # exactly one retry, never more


async def test_retry_attempts_both_count_toward_usage(monkeypatch):
    stub, _ = _client(["", '{"ok": true}'])
    monkeypatch.setattr(llm, "get_client", lambda: stub)
    with llm.track_usage() as entries:
        await llm.complete_json(system="s", user="u")
    assert len(entries) == 2  # retries are paid calls


async def test_non_dict_json_treated_as_failure(monkeypatch):
    stub, calls = _client(['[1, 2, 3]', '{"ok": true}'])
    monkeypatch.setattr(llm, "get_client", lambda: stub)
    assert await llm.complete_json(system="s", user="u") == {"ok": True}
    assert len(calls) == 2
