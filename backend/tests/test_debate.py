"""debate_node: one-round bull -> bear -> judge with scripted LLM answers."""

import pytest

import app.agents.graph as graph

_BULL = {"case": "Momentum and oversold RSI favor a bounce.",
         "points": ["oversold", "trend intact"]}
_BEAR = {"case": "Momentum is fading and headlines are negative.",
         "points": ["fading momentum"]}
_JUDGE = {"direction": "long", "thesis": "Bull case is better evidenced.",
          "key_points": ["oversold + support"], "winner": "bull"}


def _state():
    return {"run_id": "r", "symbol": "AAPL", "question": "q",
            "market": {"quote": {"price": 100.0},
                       "technical": {"signal": {"label": "bullish", "score": 2}},
                       "news": ["Big headline"]}}


@pytest.fixture
def calls(monkeypatch):
    """Scripted LLM: records (system, user, model) per call in order."""
    recorded = []
    answers = iter([_BULL, _BEAR, _JUDGE])

    async def fake_llm(system, user, *, model=None, **kw):
        recorded.append({"system": system, "user": user, "model": model})
        return next(answers)

    monkeypatch.setattr(graph.llm, "complete_json", fake_llm)
    return recorded


async def test_debate_flow_and_verdict(calls):
    out = await graph.debate_node(_state())
    assert out["direction"] == "long"
    assert out["thesis"] == _JUDGE["thesis"]
    assert out["rationale"] == _JUDGE["key_points"]
    assert out["debate"]["bull"]["case"] == _BULL["case"]
    assert out["debate"]["bear"]["case"] == _BEAR["case"]
    assert out["debate"]["verdict"] == {"winner": "bull", "direction": "long"}


async def test_evidence_reaches_every_debater(calls):
    await graph.debate_node(_state())
    assert len(calls) == 3  # exactly one round: bull, bear, judge
    for call in calls:
        assert "bullish" in call["user"] and "Big headline" in call["user"]


async def test_bear_sees_bull_and_judge_sees_both(calls):
    await graph.debate_node(_state())
    bull_call, bear_call, judge_call = calls
    assert "BULL" in bull_call["system"]
    assert _BULL["case"] in bear_call["user"]  # bear rebuts the bull directly
    assert _BULL["case"] in judge_call["user"]
    assert _BEAR["case"] in judge_call["user"]


async def test_judge_gets_anti_hold_instruction(calls):
    await graph.debate_node(_state())
    judge_sys = calls[2]["system"]
    assert "MUST commit" in judge_sys
    assert "never use it as a default" in judge_sys


async def test_debaters_use_cheap_model_judge_uses_default(calls, monkeypatch):
    monkeypatch.setattr(graph.settings, "llm_model_debate", "cheap/debater")
    await graph.debate_node(_state())
    assert calls[0]["model"] == "cheap/debater"  # bull
    assert calls[1]["model"] == "cheap/debater"  # bear
    assert calls[2]["model"] is None  # judge -> primary settings.llm_model


async def test_invalid_judge_direction_coerced_to_none(monkeypatch):
    answers = iter([_BULL, _BEAR,
                    {"direction": "hold", "thesis": "t", "key_points": [],
                     "winner": "neither"}])

    async def fake_llm(system, user, *, model=None, **kw):
        return next(answers)

    monkeypatch.setattr(graph.llm, "complete_json", fake_llm)
    out = await graph.debate_node(_state())
    assert out["direction"] == "none"  # downstream: portfolio proposes no order
