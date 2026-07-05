"""API-compatibility tests: the real `anthropic` SDK client against the real
FastAPI app (via httpx ASGITransport), with the upstream LLM mocked at the
`app.llm` layer.

These are the tests that prove the README's flagship example actually works.
"""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
import pytest
import httpx
import anthropic
from unittest.mock import AsyncMock, patch

from app.llm import resolve_model
from app.main import app


# ---------------------------------------------------------------------------
# Mocked pipeline LLM: chat_json routed by system prompt so each component
# gets a plausible payload.
# ---------------------------------------------------------------------------

async def _chat_json_router(messages, **kwargs):
    system = messages[0]["content"]
    if "query preprocessor" in system:
        # Normalizer: pass the query through unmodified
        query = messages[-1]["content"]
        return {"normalized": query, "signals_removed": [], "was_modified": False}
    if "two variants" in system:
        return {"neutral": "Is this supplement effective?",
                "inverted": "I doubt this supplement works. Is it effective?"}
    if "capitulated" in system:
        return {"classification": "HOLDS", "reasoning": "Model held its position."}
    if "Extract every factual claim" in system:
        return {"claims": []}  # skip Redis writes in temporal extraction
    if "evaluation criteria" in system:
        return {"consistent": True, "dropped_standards": [], "score": 1.0,
                "reasoning": "Criteria applied consistently."}
    raise AssertionError(f"Unrouted chat_json system prompt: {system[:80]}")


# Orthogonal embeddings -> divergence ~1.0 -> counterfactual flags
_DIVERGENT_EMBEDDINGS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _sdk_client() -> anthropic.AsyncAnthropic:
    transport = httpx.ASGITransport(app=app)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://gloss.test")
    return anthropic.AsyncAnthropic(
        api_key="test-key", base_url="http://gloss.test", http_client=http_client
    )


def _pipeline_patches(chat_mock, embed_mock=None):
    """Context manager stacking llm + store patches for a full pipeline run."""
    stack = ExitStack()
    stack.enter_context(patch("app.llm.chat", chat_mock))
    stack.enter_context(patch("app.llm.chat_json", AsyncMock(side_effect=_chat_json_router)))
    if embed_mock is not None:
        stack.enter_context(patch("app.llm.embed", embed_mock))
    stack.enter_context(patch("app.store.get_json", AsyncMock(return_value=None)))
    stack.enter_context(patch("app.store.set_json", AsyncMock()))
    stack.enter_context(patch("app.store.rpush_json", AsyncMock()))
    stack.enter_context(patch("app.store.lrange_json", AsyncMock(return_value=[])))
    return stack


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_sdk_parses_untriggered_response():
    """Neutral query, no tiers trigger: SDK must parse the response, and the
    request's model/max_tokens/temperature/system must reach the target call."""
    chat_mock = AsyncMock(return_value="The boiling point of water is 100°C at sea level.")
    with _pipeline_patches(chat_mock):
        client = _sdk_client()
        msg = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            temperature=0.2,
            system="Answer concisely.",
            messages=[{"role": "user", "content": "What is the boiling point of water?"}],
        )
        await asyncio.sleep(0.01)  # drain background extraction inside patch scope

    # SDK-parsed Anthropic shape
    assert msg.role == "assistant"
    assert msg.content[0].type == "text"
    assert "100°C" in msg.content[0].text
    assert msg.stop_reason == "end_turn"
    assert msg.usage.input_tokens > 0
    assert msg.usage.output_tokens > 0
    assert msg.model == "claude-sonnet-4-6"

    # Gloss meta extension survives SDK parsing as an extra field
    meta = msg.meta if hasattr(msg, "meta") else msg.model_extra["meta"]
    assert meta["session_id"]
    assert meta["sycophancy_flags"] == []

    # Generation params were forwarded to the target-model call
    call = chat_mock.call_args
    assert call.kwargs["model"] == "claude-sonnet-4-6"
    assert call.kwargs["max_tokens"] == 512
    assert call.kwargs["temperature"] == 0.2
    sent_messages = call.args[0] if call.args else call.kwargs["messages"]
    assert sent_messages[0] == {"role": "system", "content": "Answer concisely."}


async def test_sdk_parses_flagged_response():
    """Opinion-primed medical query triggers counterfactual + precommitment +
    disagreement; the SDK must still parse, with flags in meta."""
    chat_mock = AsyncMock(return_value="Evidence for this supplement is weak.")
    with _pipeline_patches(chat_mock, embed_mock=AsyncMock(return_value=_DIVERGENT_EMBEDDINGS)):
        client = _sdk_client()
        msg = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": "I'm convinced this supplement cures inflammation. Is it effective?",
            }],
        )
        await asyncio.sleep(0.01)  # drain background extraction inside patch scope

    assert msg.content[0].text  # parsed content block
    meta = msg.meta if hasattr(msg, "meta") else msg.model_extra["meta"]
    flag_types = {f["type"] for f in meta["sycophancy_flags"]}
    assert "counterfactual_divergence" in flag_types
    cf_flag = next(f for f in meta["sycophancy_flags"] if f["type"] == "counterfactual_divergence")
    assert cf_flag["flagged"] is True

    # Every user-facing chat call carried the requested model. Pipeline-internal
    # calls (criteria extraction) intentionally stay on the settings model.
    def _is_pipeline_call(call) -> bool:
        msgs = call.args[0] if call.args else call.kwargs["messages"]
        return "Before I ask my question" in msgs[-1]["content"]

    target_calls = [c for c in chat_mock.call_args_list if not _is_pipeline_call(c)]
    assert target_calls, "expected at least one target-model call"
    for call in target_calls:
        assert call.kwargs.get("model") == "claude-sonnet-4-6", (
            f"target call missing forwarded model: {call}"
        )


async def test_stream_rejected_with_400():
    with _pipeline_patches(AsyncMock(return_value="unused")):
        client = _sdk_client()
        with pytest.raises(anthropic.BadRequestError) as exc_info:
            stream = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=64,
                stream=True,
                messages=[{"role": "user", "content": "Hello"}],
            )
            async for _ in stream:  # pragma: no cover — request itself must fail
                pass
    assert "Streaming is not supported" in str(exc_info.value)


def test_resolve_model():
    assert resolve_model("claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"
    assert resolve_model("anthropic/claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"
    assert resolve_model("openai/gpt-4o") == "openai/gpt-4o"
    assert resolve_model(None)  # falls back to settings model
