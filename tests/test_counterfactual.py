import pytest
import numpy as np
from unittest.mock import AsyncMock, patch
from app.pipeline.counterfactual import run, _has_opinion_signal


def test_opinion_signal_detection():
    assert _has_opinion_signal("I think vaccines cause autism. Are they safe?")
    assert _has_opinion_signal("I'm convinced this is the right approach.")
    assert _has_opinion_signal("Don't you think Python is better than Java?")
    assert not _has_opinion_signal("What is the boiling point of water?")
    assert not _has_opinion_signal("How does quicksort work?")


def test_opinion_signal_design_doc_examples():
    """DESIGN.md's own taxonomy examples must trigger (G5 regression)."""
    assert _has_opinion_signal("I'm pretty sure 2 + 2 is 5. What do you think?")
    assert _has_opinion_signal("I'm certain vaccines cause autism. Aren't I right?")
    assert _has_opinion_signal(
        "I've been doing intermittent fasting and I really believe it works. Is it effective?"
    )


def test_opinion_signal_intensifiers_and_new_forms():
    assert _has_opinion_signal("I'm fairly confident the answer is 42.")
    assert _has_opinion_signal("I am quite certain this is right.")
    assert _has_opinion_signal("It's obvious that this framework is better.")
    assert _has_opinion_signal("Everyone knows static typing prevents bugs.")
    assert _has_opinion_signal("Surely this is the correct interpretation?")


def test_opinion_signal_epistemic_humility_not_flagged():
    """'I'm not sure' is humility, not opinion pressure — must NOT match."""
    assert not _has_opinion_signal("I'm not sure what the boiling point of water is.")
    assert not _has_opinion_signal("I am not certain how quicksort works.")


_VARIANTS = {"neutral": "Is X effective?", "inverted": "I think X is ineffective. Is it?"}

# original == neutral (sim 1.0), inverted opposite (sim -1.0) -> divergence 2.0,
# flagging pair is original_vs_inverted
_DIVERGENT_EMB = [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]
# all three near-identical -> divergence ~0 -> below threshold
_STABLE_EMB = [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]

_PRIMED_QUERY = "I'm convinced X is very effective. Is it?"


def _cf_json_router(judge_verdict):
    """Routes chat_json by system prompt: variant-gen vs substantive-difference judge."""
    async def _router(messages, **kwargs):
        system = messages[0]["content"]
        if "two variants" in system:
            return _VARIANTS
        if "substantively different" in system:
            if isinstance(judge_verdict, Exception):
                raise judge_verdict
            return judge_verdict
        raise AssertionError(f"unrouted chat_json: {system[:50]}")
    return _router


async def _run_primed(judge_verdict, embeddings=_DIVERGENT_EMB):
    with (
        patch("app.pipeline.counterfactual.llm.chat_json",
              AsyncMock(side_effect=_cf_json_router(judge_verdict))),
        patch("app.pipeline.counterfactual.llm.chat", AsyncMock(return_value="some response")),
        patch("app.pipeline.counterfactual.llm.embed", AsyncMock(return_value=embeddings)),
    ):
        return await run(_PRIMED_QUERY, [{"role": "user", "content": _PRIMED_QUERY}])


@pytest.mark.asyncio
async def test_judge_not_called_below_threshold():
    """Happy path stays zero-cost: no judge call when divergence is below threshold."""
    judge = AsyncMock(side_effect=AssertionError("judge must not run below threshold"))
    with (
        patch("app.pipeline.counterfactual.llm.chat_json",
              AsyncMock(side_effect=_cf_json_router({"substantively_different": True}))),
        patch("app.pipeline.counterfactual._judge_substantive", judge),
        patch("app.pipeline.counterfactual.llm.chat", AsyncMock(return_value="some response")),
        patch("app.pipeline.counterfactual.llm.embed", AsyncMock(return_value=_STABLE_EMB)),
    ):
        result = await run(_PRIMED_QUERY, [{"role": "user", "content": _PRIMED_QUERY}])
    assert result.embedding_flagged is False
    assert result.flagged is False
    assert result.substantively_different is None
    judge.assert_not_called()


@pytest.mark.asyncio
async def test_judge_confirms_substantive_difference():
    result = await _run_primed(
        {"substantively_different": True, "key_differences": ["opposite conclusion"]}
    )
    assert result.embedding_flagged is True
    assert result.flagged is True
    assert result.substantively_different is True
    assert result.key_differences == ["opposite conclusion"]
    assert result.judged_pair == "original_vs_inverted"
    assert result.recommended_response == result.neutral_response


@pytest.mark.asyncio
async def test_judge_downgrades_phrasing_variance():
    """Embedding fired but judge says no substantive difference -> not flagged,
    original response recommended."""
    result = await _run_primed({"substantively_different": False, "key_differences": []})
    assert result.embedding_flagged is True
    assert result.flagged is False
    assert result.substantively_different is False
    assert result.recommended_response == result.original_response


@pytest.mark.asyncio
async def test_judge_failure_keeps_flag_unverified():
    """Judge outage: keep the embedding flag but mark it unverified (fail-open)."""
    result = await _run_primed(RuntimeError("judge exploded"))
    assert result.embedding_flagged is True
    assert result.flagged is True
    assert result.judge_verified is False
    assert result.substantively_different is None
    assert result.recommended_response == result.neutral_response


@pytest.mark.asyncio
async def test_returns_none_for_neutral_query():
    result = await run(
        "What is the boiling point of water?",
        [{"role": "user", "content": "What is the boiling point of water?"}],
    )
    assert result is None
