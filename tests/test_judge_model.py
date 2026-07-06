"""G11: scoring judges route to judge_model; generators stay on the target model."""
from __future__ import annotations
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models import Message, MessagesRequest
from app.middleware import process


# System-prompt fragments that identify each chat_json call site.
JUDGE_MARKERS = {
    "substantively different",   # counterfactual substantive-difference judge
    "evaluation criteria",       # precommitment consistency judge
    "capitulated",               # disagreement pushback judge
    "drifted across a conversation",  # temporal arc judge
}
GENERATOR_MARKERS = {
    "query preprocessor",        # normalizer
    "two variants",              # counterfactual variant generator
    "Extract every factual claim",  # temporal claim extraction
}


def _classify(system: str) -> str:
    for m in JUDGE_MARKERS:
        if m in system:
            return "judge"
    for m in GENERATOR_MARKERS:
        if m in system:
            return "generator"
    return "other"


async def _chat_json_router(messages, **kwargs):
    system = messages[0]["content"]
    if "query preprocessor" in system:
        return {"normalized": messages[-1]["content"], "signals_removed": [], "was_modified": False}
    if "two variants" in system:
        return {"neutral": "Is it effective?", "inverted": "I doubt it. Is it effective?"}
    if "substantively different" in system:
        return {"substantively_different": True, "key_differences": ["x"]}
    if "capitulated" in system:
        return {"classification": "HOLDS", "reasoning": "held"}
    if "Extract every factual claim" in system:
        return {"claims": []}
    if "evaluation criteria" in system:
        return {"consistent": True, "dropped_standards": [], "score": 1.0, "reasoning": "ok"}
    raise AssertionError(f"unrouted chat_json: {system[:60]}")


async def _drive_full_pipeline():
    """Opinion-primed medical query → counterfactual + precommitment +
    disagreement all fire (temporal extraction runs in background)."""
    chat_json_calls: list[dict] = []

    async def tracking_chat_json(messages, **kwargs):
        chat_json_calls.append({"system": messages[0]["content"], "model": kwargs.get("model")})
        return await _chat_json_router(messages, **kwargs)

    divergent = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    with ExitStack() as stack:
        stack.enter_context(patch("app.llm.chat", AsyncMock(return_value="a response")))
        stack.enter_context(patch("app.llm.chat_json", AsyncMock(side_effect=tracking_chat_json)))
        stack.enter_context(patch("app.llm.embed", AsyncMock(return_value=divergent)))
        stack.enter_context(patch("app.store.get_json", AsyncMock(return_value=None)))
        stack.enter_context(patch("app.store.set_json", AsyncMock()))
        stack.enter_context(patch("app.store.rpush_json", AsyncMock()))
        stack.enter_context(patch("app.store.lrange_json", AsyncMock(return_value=[])))
        request = MessagesRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user",
                              content="I'm convinced this supplement cures inflammation. Is it effective?")],
        )
        await process(request, "sess-judge-test")
        import asyncio
        await asyncio.sleep(0.01)  # drain background extraction inside patch scope
    return chat_json_calls


async def test_judges_use_judge_model_generators_use_target(monkeypatch):
    monkeypatch.setattr(settings, "judge_model", "openai/gpt-4o")
    calls = await _drive_full_pipeline()

    seen = {"judge": 0, "generator": 0}
    for c in calls:
        kind = _classify(c["system"])
        if kind == "judge":
            seen["judge"] += 1
            assert c["model"] == "openai/gpt-4o", f"judge did not route to judge_model: {c['system'][:50]}"
        elif kind == "generator":
            seen["generator"] += 1
            assert c["model"] != "openai/gpt-4o", f"generator wrongly routed to judge_model: {c['system'][:50]}"

    # Sanity: the medical primed query actually exercised judges and generators
    assert seen["judge"] >= 3   # counterfactual + precommitment + disagreement
    assert seen["generator"] >= 2  # normalizer + variant generator


async def test_judge_model_none_uses_target(monkeypatch):
    monkeypatch.setattr(settings, "judge_model", None)
    calls = await _drive_full_pipeline()
    for c in calls:
        if _classify(c["system"]) == "judge":
            # None -> effective_judge_model returns litellm_model
            assert c["model"] == settings.litellm_model


def test_effective_judge_model_property(monkeypatch):
    monkeypatch.setattr(settings, "judge_model", None)
    assert settings.effective_judge_model == settings.litellm_model
    monkeypatch.setattr(settings, "judge_model", "anthropic/claude-haiku-4-5")
    assert settings.effective_judge_model == "anthropic/claude-haiku-4-5"
