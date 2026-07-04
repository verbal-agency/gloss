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
