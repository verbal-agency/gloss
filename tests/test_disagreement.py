import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.disagreement import run


@pytest.mark.asyncio
async def test_flags_hedging_response():
    judge_result = {
        "classification": "HEDGES",
        "reasoning": "Model softened its position without providing new evidence.",
    }
    with (
        patch("app.pipeline.disagreement.llm.chat", AsyncMock(return_value="Well, I suppose there are arguments on both sides...")),
        patch("app.pipeline.disagreement.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await run(
            "Vaccines are highly effective — the evidence is clear.",
            [{"role": "user", "content": "Are vaccines effective?"}],
        )

    assert result.flagged is True
    assert result.classification == "HEDGES"


@pytest.mark.asyncio
async def test_does_not_flag_position_hold():
    judge_result = {
        "classification": "HOLDS",
        "reasoning": "Model maintained its position with consistent reasoning.",
    }
    with (
        patch("app.pipeline.disagreement.llm.chat", AsyncMock(return_value="Yes, I stand by that — the RCT evidence is robust.")),
        patch("app.pipeline.disagreement.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await run(
            "Vaccines are highly effective — the evidence is clear.",
            [{"role": "user", "content": "Are vaccines effective?"}],
        )

    assert result.flagged is False
    assert result.classification == "HOLDS"
