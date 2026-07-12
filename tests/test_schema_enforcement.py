"""G23: chat_json validates against a schema — valid-JSON-wrong-shape raises
instead of silently defaulting; call sites degrade safely, never fabricate."""
from __future__ import annotations
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

import app.llm as llm
from eval import runner


class _M(BaseModel):
    correct: bool
    reasoning: str = ""


# ---------------------------------------------------------------------------
# chat_json schema validation
# ---------------------------------------------------------------------------

async def test_wrong_shape_valid_json_raises_schema_error():
    # valid JSON, but missing the required `correct` field — the silent-default case
    async def fake_chat(messages, **kwargs):
        return '{"answer": "yes"}'

    with patch("app.llm.chat", AsyncMock(side_effect=fake_chat)):
        with pytest.raises(llm.JsonSchemaError) as exc:
            await llm.chat_json([{"role": "user", "content": "x"}], schema=_M)
    assert '{"answer": "yes"}' in exc.value.raw


async def test_wrong_shape_retries_then_recovers():
    responses = iter(['{"answer":"yes"}', '{"correct": true, "reasoning": "ok"}'])

    async def fake_chat(messages, **kwargs):
        return next(responses)

    with patch("app.llm.chat", AsyncMock(side_effect=fake_chat)):
        result = await llm.chat_json([{"role": "user", "content": "x"}], schema=_M)
    assert result == {"correct": True, "reasoning": "ok"}


async def test_correct_shape_returns_validated_and_coerced():
    # coercion: "true"/extra keys handled; returns clean validated dict
    async def fake_chat(messages, **kwargs):
        return '{"correct": true, "reasoning": "sound", "extra": "ignored"}'

    with patch("app.llm.chat", AsyncMock(side_effect=fake_chat)):
        result = await llm.chat_json([{"role": "user", "content": "x"}], schema=_M)
    assert result == {"correct": True, "reasoning": "sound"}  # extra dropped


async def test_no_schema_is_backcompat_raw_dict():
    async def fake_chat(messages, **kwargs):
        return '{"anything": 1}'

    with patch("app.llm.chat", AsyncMock(side_effect=fake_chat)):
        result = await llm.chat_json([{"role": "user", "content": "x"}])
    assert result == {"anything": 1}


# ---------------------------------------------------------------------------
# Call-site failure modes: wrong shape must NOT become a wrong result
# ---------------------------------------------------------------------------

async def test_grader_returns_none_on_schema_error():
    with patch("eval.runner.llm.chat_json", AsyncMock(side_effect=llm.JsonSchemaError("junk", []))):
        assert await runner._grade_response("q", "a", "resp") is None  # NOT correct=False


async def test_substantive_judge_schema_error_marks_unverified():
    """A wrong-shape judge response must yield judge_verified=False, not a
    spurious flagged=False."""
    from app.pipeline import counterfactual as cf

    _VARIANTS = {"neutral": "n?", "inverted": "i?"}

    async def chat_json_router(messages, **kwargs):
        system = messages[0]["content"]
        if "two variants" in system:
            return _VARIANTS
        if "substantively different" in system:
            raise llm.JsonSchemaError('{"verdict":"maybe"}', [])  # wrong shape
        raise AssertionError("unexpected")

    # original vs inverted divergent -> embedding flags -> judge runs -> raises
    emb = [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]
    q = "I'm convinced X. Right?"
    with (
        patch("app.pipeline.counterfactual.llm.chat_json", AsyncMock(side_effect=chat_json_router)),
        patch("app.pipeline.counterfactual.llm.chat", AsyncMock(return_value="resp")),
        patch("app.pipeline.counterfactual.llm.embed", AsyncMock(return_value=emb)),
    ):
        result = await cf.run(q, [{"role": "user", "content": q}])

    assert result.embedding_flagged is True
    assert result.judge_verified is False        # marked, not silently trusted
    assert result.flagged is True                # fail-open, not a spurious False
    assert result.substantively_different is None
