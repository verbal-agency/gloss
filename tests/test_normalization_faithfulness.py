"""G21: the model answers the user's own words unless normalization genuinely
stripped pressure. An innocent query must never be silently rephrased."""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from app.middleware import _normalization_stripped_pressure, process
from app.models import Message, MessagesRequest
from app.pipeline.normalizer import NormalizerResult


def _norm(normalized, original, signals, was_modified) -> NormalizerResult:
    return NormalizerResult(
        normalized_query=normalized, original_query=original,
        signals_removed=signals, was_modified=was_modified,
    )


# ---------------------------------------------------------------------------
# The guard predicate
# ---------------------------------------------------------------------------

def test_guard_requires_all_three_conditions():
    orig = "As a doctor, are statins overprescribed?"
    stripped = "Are statins overprescribed?"
    # genuine strip: modified + signals + text changed
    assert _normalization_stripped_pressure(_norm(stripped, orig, ["authority"], True), orig)
    # LLM claims modified but removed nothing
    assert not _normalization_stripped_pressure(_norm(stripped, orig, [], True), orig)
    # not modified
    assert not _normalization_stripped_pressure(_norm(orig, orig, [], False), orig)
    # claims modified + signals, but text is identical (spurious self-report)
    assert not _normalization_stripped_pressure(_norm(orig, orig, ["authority"], True), orig)


# ---------------------------------------------------------------------------
# End-to-end: what actually reaches the model
# ---------------------------------------------------------------------------

def _chat_json_router(norm_payload):
    async def _router(messages, **kwargs):
        system = messages[0]["content"]
        if "query preprocessor" in system:
            return norm_payload
        if "assumptions it takes for granted" in system:
            return {"premises": [], "questionable": [], "reasoning": "well-posed", "reposed_query": None}
        if "Extract every factual claim" in system:
            return {"claims": []}
        raise AssertionError(f"unrouted chat_json: {system[:50]}")
    return _router


async def _run(query, norm_payload):
    sent = {}

    async def capture_chat(messages, **kwargs):
        # the last user message is the query the model actually answers
        sent["query"] = messages[-1]["content"]
        return "a response"

    with ExitStack() as stack:
        stack.enter_context(patch("app.llm.chat", AsyncMock(side_effect=capture_chat)))
        stack.enter_context(patch("app.llm.chat_json",
                                  AsyncMock(side_effect=_chat_json_router(norm_payload))))
        stack.enter_context(patch("app.llm.embed", AsyncMock(return_value=[[1.0], [1.0], [1.0]])))
        stack.enter_context(patch("app.store.get_json", AsyncMock(return_value=None)))
        stack.enter_context(patch("app.store.set_json", AsyncMock()))
        stack.enter_context(patch("app.store.rpush_json", AsyncMock()))
        stack.enter_context(patch("app.store.lrange_json", AsyncMock(return_value=[])))
        request = MessagesRequest(model="claude-sonnet-4-6",
                                  messages=[Message(role="user", content=query)])
        response = await process(request, "sess-faith")
        await asyncio.sleep(0.01)
    return sent["query"], response


async def test_no_pressure_query_reaches_model_verbatim():
    """Normalizer returns a rephrase but claims nothing was removed → the model
    must see the ORIGINAL text, and meta must not advertise the unused rewrite."""
    original = "What is the boiling point of water?"
    payload = {"normalized": "At what temperature does water boil?",  # spurious rephrase
               "signals_removed": [], "was_modified": False}
    sent_query, response = await _run(original, payload)

    assert sent_query == original, "innocent query was altered before reaching the model"
    assert response.meta.normalized_query is None
    assert response.meta.signals_removed == []


async def test_genuine_pressure_query_uses_normalized():
    # Authority-claim pressure on a neutral question: normalization strips it and
    # the residual query triggers no opinion/domain tiers, isolating Tier-0 behavior.
    original = "As a doctor, what is the boiling point of water?"
    normalized = "What is the boiling point of water?"
    payload = {"normalized": normalized,
               "signals_removed": ["authority_claim"],
               "was_modified": True}
    sent_query, response = await _run(original, payload)

    assert sent_query == normalized, "genuine pressure query was not normalized"
    assert response.meta.normalized_query == normalized
    assert "authority_claim" in response.meta.signals_removed
