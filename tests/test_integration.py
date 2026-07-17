"""G14 (1): end-to-end response selection through the full pipeline.

Distinct mock texts per call let us assert WHICH response the client receives —
the property single-text mocks structurally cannot test.
"""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from app.middleware import process
from app.models import Message, MessagesRequest

ORIGINAL_Q = "I'm convinced Rome fell in 476 AD. Right?"  # opinion signal, general domain
NEUTRAL_Q = "When did Rome fall?"
INVERTED_Q = "I doubt Rome fell in 476 AD. Did it?"


async def _fake_chat(messages, **kwargs):
    """Route by the message that determines the response — distinct text per call."""
    content = messages[-1]["content"]
    if content == ORIGINAL_Q:
        return "ORIG_RESP"
    if content == NEUTRAL_Q:
        return "NEUT_RESP"
    if content == INVERTED_Q:
        return "INV_RESP"
    if "credible sources that strongly disagree" in content:
        return "PUSH_RESP"  # disagreement pushback probe
    raise AssertionError(f"unrouted chat call: {content[:60]}")


def _chat_json_router(verdict: dict):
    async def _router(messages, **kwargs):
        system = messages[0]["content"]
        if "query preprocessor" in system:
            # Normalizer passes the query through (no pressure removed)
            return {"normalized": messages[-1]["content"],
                    "signals_removed": [], "was_modified": False}
        if "two variants" in system:
            return {"neutral": NEUTRAL_Q, "inverted": INVERTED_Q}
        if "substantively different" in system:      # the counterfactual flip judge
            return verdict
        if "capitulated" in system:
            return {"classification": "HOLDS", "reasoning": "held"}
        if "Extract every factual claim" in system:
            return {"claims": []}
        raise AssertionError(f"unrouted chat_json: {system[:60]}")
    return _router


# high embedding divergence — but G25 no longer gates on it; the judge decides
_EMBEDDINGS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.9, 0.1, 0.0]]


async def _run_pipeline(verdict: dict):
    with ExitStack() as stack:
        stack.enter_context(patch("app.llm.chat", AsyncMock(side_effect=_fake_chat)))
        stack.enter_context(patch("app.llm.chat_json",
                                  AsyncMock(side_effect=_chat_json_router(verdict))))
        stack.enter_context(patch("app.llm.embed", AsyncMock(return_value=_EMBEDDINGS)))
        stack.enter_context(patch("app.store.get_json", AsyncMock(return_value=None)))
        stack.enter_context(patch("app.store.set_json", AsyncMock()))
        stack.enter_context(patch("app.store.rpush_json", AsyncMock()))
        stack.enter_context(patch("app.store.lrange_json", AsyncMock(return_value=[])))
        request = MessagesRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user", content=ORIGINAL_Q)],
        )
        response = await process(request, "sess-integration")
        await asyncio.sleep(0.01)  # drain background extraction inside patch scope
    return response


async def test_flagged_request_returns_neutral_variant_response():
    response = await _run_pipeline({"flipped": True, "key_differences": ["dates disagree"]})

    assert response.content[0].text == "NEUT_RESP", (
        "flagged request must return the neutral-variant response, "
        f"got {response.content[0].text!r}"
    )
    cf = next(f for f in response.meta.sycophancy_flags
              if f.type == "counterfactual_divergence")
    assert cf.flagged is True
    assert cf.detail["judged_pair"] == "neutral_vs_inverted"


async def test_judge_stable_request_returns_original_response():
    # High embedding divergence, but the judge says no flip / no shift -> not flagged
    response = await _run_pipeline({"flipped": False, "substantively_different": False})

    assert response.content[0].text == "ORIG_RESP", (
        "unflagged request must return the ORIGINAL response, "
        f"got {response.content[0].text!r}"
    )
    cf = next(f for f in response.meta.sycophancy_flags
              if f.type == "counterfactual_divergence")
    assert cf.flagged is False
    assert cf.detail["embedding_flagged"] is True  # cheap signal over-fired (telemetry)
