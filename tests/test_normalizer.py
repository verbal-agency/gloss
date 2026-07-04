import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.normalizer import run


@pytest.mark.asyncio
async def test_strips_authority_claim():
    mock_response = {
        "normalized": "Is intermittent fasting effective for weight loss?",
        "signals_removed": ["authority_claim"],
        "was_modified": True,
        "rationale": "Removed authority framing that validates a conclusion.",
    }
    with patch("app.pipeline.normalizer.llm.chat_json", AsyncMock(return_value=mock_response)):
        result = await run("As a nutritionist, I know intermittent fasting is the best diet. Is it effective?")

    assert result.was_modified is True
    assert "authority_claim" in result.signals_removed
    assert "nutritionist" not in result.normalized_query


@pytest.mark.asyncio
async def test_preserves_neutral_query():
    mock_response = {
        "normalized": "What is the capital of France?",
        "signals_removed": [],
        "was_modified": False,
        "rationale": "No pressure signals detected.",
    }
    with patch("app.pipeline.normalizer.llm.chat_json", AsyncMock(return_value=mock_response)):
        result = await run("What is the capital of France?")

    assert result.was_modified is False
    assert result.signals_removed == []
    assert result.normalized_query == "What is the capital of France?"
