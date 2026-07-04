"""Orchestrator tests: response selection and call economy in `process()`."""
from __future__ import annotations
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from app.middleware import process
from app.models import Message, MessagesRequest


def _is_criteria_call(messages: list[dict]) -> bool:
    return "Before I ask my question" in messages[-1]["content"]


async def test_pc_only_path_makes_one_target_call_and_returns_judged_response():
    """Medical query without opinion signal: precommitment runs, counterfactual
    doesn't. Exactly one target-model call, and the response the judge saw is
    the response the user gets."""
    chat_calls: list[list[dict]] = []
    judge_saw: dict[str, str] = {}

    async def fake_chat(messages, **kwargs):
        chat_calls.append(messages)
        if _is_criteria_call(messages):
            return "Criteria: RCT evidence, replication, no conflicts of interest."
        return f"TARGET_RESPONSE_{len(chat_calls)}"

    async def fake_chat_json(messages, **kwargs):
        system = messages[0]["content"]
        if "query preprocessor" in system:
            return {"normalized": messages[-1]["content"],
                    "signals_removed": [], "was_modified": False}
        if "Extract every factual claim" in system:
            return {"claims": []}
        if "evaluation criteria" in system:
            judge_saw["payload"] = messages[-1]["content"]
            return {"consistent": True, "dropped_standards": [],
                    "score": 1.0, "reasoning": "ok"}
        raise AssertionError(f"Unrouted chat_json system prompt: {system[:60]}")

    with ExitStack() as stack:
        stack.enter_context(patch("app.llm.chat", AsyncMock(side_effect=fake_chat)))
        stack.enter_context(patch("app.llm.chat_json", AsyncMock(side_effect=fake_chat_json)))
        stack.enter_context(patch("app.store.get_json", AsyncMock(return_value=None)))
        stack.enter_context(patch("app.store.set_json", AsyncMock()))
        stack.enter_context(patch("app.store.rpush_json", AsyncMock()))
        stack.enter_context(patch("app.store.lrange_json", AsyncMock(return_value=[])))

        request = MessagesRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user", content="Should I take ibuprofen for a fever?")],
        )
        response = await process(request, "sess-g2-test")

    # Exactly one target-model call (criteria extraction is pipeline-internal)
    target_calls = [c for c in chat_calls if not _is_criteria_call(c)]
    assert len(target_calls) == 1, (
        f"expected exactly 1 target-model call in pc-only path, got {len(target_calls)}"
    )

    # The response the judge evaluated is the response the user received
    returned_text = response.content[0].text
    assert returned_text.startswith("TARGET_RESPONSE")
    assert returned_text in judge_saw["payload"], (
        "judge evaluated a different response than the one returned to the user"
    )

    # And the precommitment flag is present on the response
    assert any(f.type == "precommitment_inconsistency" for f in response.meta.sycophancy_flags)
