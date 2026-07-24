"""G27 spike + G29 — unit coverage with the LLM mocked (no live calls).

Proves the extractor parses into the schema, that the go/no-go metric math is
correct, and that the G29 assumption tier wires correctly into middleware.
The actual faithfulness numbers come from the live harness
(`eval.assumptions_eval`), which is spend-gated and run separately.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.pipeline import assumptions
from app.pipeline.assumptions import AssumptionResult
from eval.assumptions_eval import QueryOutcome, summarize


async def test_extract_parses_into_schema():
    payload = {
        "premises": ["the stack is appropriate for the task"],
        "questionable": ["that this stack is necessary for a simple to-do list"],
        "reasoning": "the query presupposes a heavy stack for a trivial task",
        "reposed_query": "What's the simplest way to build a to-do list?",
    }
    with patch("app.llm.chat_json", AsyncMock(return_value=payload)):
        result = await assumptions.extract("How do I use React+Redux+Mongo for a to-do list?")
    assert isinstance(result, AssumptionResult)
    assert result.questionable == payload["questionable"]
    assert result.premises == payload["premises"]


async def test_extract_faithful_empty_questionable():
    # A clean query: premises may exist, but questionable must be allowed to be empty.
    payload = {"premises": ["HTTPS is in use"], "questionable": [], "reasoning": "well-posed",
               "reposed_query": None}
    with patch("app.llm.chat_json", AsyncMock(return_value=payload)):
        result = await assumptions.extract("How does HTTPS keep data secure in transit?")
    assert result.questionable == []


# G29 — combined detection + repose in one call
async def test_extract_returns_reposed_query_when_loaded():
    payload = {
        "premises": ["indexing is the fix"],
        "questionable": ["assumes indexing is the right solution"],
        "reasoning": "other causes (N+1, schema) may be the actual bottleneck",
        "reposed_query": "How do I speed up my slow database?",
    }
    with patch("app.llm.chat_json", AsyncMock(return_value=payload)) as mock_json:
        result = await assumptions.extract("How do I add more indexes to speed up my slow database?")
    assert result.reposed_query == "How do I speed up my slow database?"
    assert mock_json.call_count == 1  # one round-trip: detect + repose together


async def test_extract_reposed_query_none_when_clean():
    payload = {"premises": [], "questionable": [], "reasoning": "well-posed", "reposed_query": None}
    with patch("app.llm.chat_json", AsyncMock(return_value=payload)):
        result = await assumptions.extract("What are the tradeoffs between REST and GraphQL?")
    assert result.reposed_query is None


def _outcome(fired: bool, group: str = "framing") -> QueryOutcome:
    r = AssumptionResult(
        premises=["p"], questionable=["q"] if fired else [], reasoning="r"
    )
    return QueryOutcome("query", r, group)


def test_summarize_rates():
    # 3/4 loaded fired -> 0.75 recall; 1/4 clean fired -> 0.25 false-positive
    loaded = [_outcome(True), _outcome(True), _outcome(True), _outcome(False)]
    clean = [_outcome(False, "neutral"), _outcome(False, "neutral"),
             _outcome(False, "near_miss"), _outcome(True, "near_miss")]
    s = summarize(loaded, clean)
    assert s["detection_rate"] == 0.75
    assert s["false_positive_rate"] == 0.25
    assert s["detected"] == 3
    assert s["false_positives"] == 1


# G29 — middleware wiring
async def test_middleware_answers_reposed_query_when_loaded():
    """Loaded query: middleware sends the reposed_query (not the original) to the model."""
    from contextlib import ExitStack
    from app.middleware import process
    from app.models import Message, MessagesRequest
    from app.config import settings

    chat_received: list[list[dict]] = []

    async def fake_chat(messages, **kwargs):
        chat_received.append(messages)
        return "model response"

    reposed = "What is the simplest way to build a to-do list?"
    original = "How do I use React+Redux+Mongo for a to-do list?"

    with ExitStack() as stack:
        stack.enter_context(patch.object(settings, "tier_counterfactual", False))
        stack.enter_context(patch.object(settings, "tier_precommitment", False))
        stack.enter_context(patch.object(settings, "tier_disagreement", False))
        stack.enter_context(patch.object(settings, "tier_temporal", False))
        stack.enter_context(patch("app.llm.chat", AsyncMock(side_effect=fake_chat)))
        stack.enter_context(patch("app.llm.chat_json", AsyncMock(
            return_value={"normalized": original, "signals_removed": [], "was_modified": False}
        )))
        stack.enter_context(patch("app.pipeline.assumptions.extract", AsyncMock(
            return_value=AssumptionResult(
                premises=["React+Redux+Mongo is required"],
                questionable=["unnecessary stack for a trivial task"],
                reasoning="over-engineered framing",
                reposed_query=reposed,
            )
        )))
        request = MessagesRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user", content=original)],
        )
        await process(request, "sess-g29-loaded")

    assert chat_received, "llm.chat was never called"
    user_msg = next(m["content"] for m in chat_received[-1] if m["role"] == "user")
    assert user_msg == reposed


async def test_middleware_passes_original_when_clean():
    """Clean query (reposed_query=None): model receives the original unchanged."""
    from contextlib import ExitStack
    from app.middleware import process
    from app.models import Message, MessagesRequest
    from app.config import settings

    chat_received: list[list[dict]] = []

    async def fake_chat(messages, **kwargs):
        chat_received.append(messages)
        return "model response"

    original = "What are the tradeoffs between REST and GraphQL?"

    with ExitStack() as stack:
        stack.enter_context(patch.object(settings, "tier_counterfactual", False))
        stack.enter_context(patch.object(settings, "tier_precommitment", False))
        stack.enter_context(patch.object(settings, "tier_disagreement", False))
        stack.enter_context(patch.object(settings, "tier_temporal", False))
        stack.enter_context(patch("app.llm.chat", AsyncMock(side_effect=fake_chat)))
        stack.enter_context(patch("app.llm.chat_json", AsyncMock(
            return_value={"normalized": original, "signals_removed": [], "was_modified": False}
        )))
        stack.enter_context(patch("app.pipeline.assumptions.extract", AsyncMock(
            return_value=AssumptionResult(
                premises=[], questionable=[], reasoning="well-posed", reposed_query=None
            )
        )))
        request = MessagesRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user", content=original)],
        )
        await process(request, "sess-g29-clean")

    assert chat_received, "llm.chat was never called"
    user_msg = next(m["content"] for m in chat_received[-1] if m["role"] == "user")
    assert user_msg == original


async def test_middleware_assumption_tier_fires_without_opinion_signal():
    """Assumption tier fires unconditionally — no opinion signal required."""
    from contextlib import ExitStack
    from app.middleware import process
    from app.models import Message, MessagesRequest
    from app.config import settings

    extract_calls: list[str] = []

    async def fake_extract(query, **kwargs):
        extract_calls.append(query)
        return AssumptionResult(premises=[], questionable=[], reasoning="well-posed", reposed_query=None)

    query = "How does the TCP handshake work?"

    with ExitStack() as stack:
        stack.enter_context(patch.object(settings, "tier_counterfactual", False))
        stack.enter_context(patch.object(settings, "tier_precommitment", False))
        stack.enter_context(patch.object(settings, "tier_disagreement", False))
        stack.enter_context(patch.object(settings, "tier_temporal", False))
        stack.enter_context(patch("app.llm.chat", AsyncMock(return_value="model response")))
        stack.enter_context(patch("app.llm.chat_json", AsyncMock(
            return_value={"normalized": query, "signals_removed": [], "was_modified": False}
        )))
        stack.enter_context(patch("app.pipeline.assumptions.extract", AsyncMock(side_effect=fake_extract)))
        request = MessagesRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user", content=query)],
        )
        await process(request, "sess-g29-signal")

    assert extract_calls == [query]


def test_summarize_breaks_out_by_group():
    # detection split by category; false-positives split by kind
    loaded = [_outcome(True, "factual"), _outcome(False, "factual"),
              _outcome(True, "framing"), _outcome(True, "framing")]
    clean = [_outcome(True, "near_miss"), _outcome(False, "neutral")]
    s = summarize(loaded, clean)
    assert s["detection_by_category"]["factual"]["rate"] == 0.5
    assert s["detection_by_category"]["framing"]["rate"] == 1.0
    assert s["false_positive_by_kind"]["near_miss"]["rate"] == 1.0
    assert s["false_positive_by_kind"]["neutral"]["rate"] == 0.0
