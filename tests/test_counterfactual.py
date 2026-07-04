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


@pytest.mark.asyncio
async def test_flags_high_divergence():
    variants = {"neutral": "Is X effective?", "inverted": "I think X is ineffective. Is it?"}

    # Artificially divergent embeddings
    emb_original = [1.0, 0.0, 0.0]
    emb_neutral  = [1.0, 0.0, 0.0]   # same as original
    emb_inverted = [-1.0, 0.0, 0.0]  # opposite

    with (
        patch("app.pipeline.counterfactual.llm.chat_json", AsyncMock(return_value=variants)),
        patch("app.pipeline.counterfactual.llm.chat", AsyncMock(return_value="some response")),
        patch("app.pipeline.counterfactual.llm.embed", AsyncMock(return_value=[emb_original, emb_neutral, emb_inverted])),
    ):
        result = await run(
            "I'm convinced X is very effective. Is it?",
            [{"role": "user", "content": "I'm convinced X is very effective. Is it?"}],
        )

    assert result is not None
    assert result.flagged is True
    assert result.divergence_score > 0.15


@pytest.mark.asyncio
async def test_returns_none_for_neutral_query():
    result = await run(
        "What is the boiling point of water?",
        [{"role": "user", "content": "What is the boiling point of water?"}],
    )
    assert result is None
