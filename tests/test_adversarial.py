import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.adversarial import run


@pytest.mark.asyncio
async def test_flags_material_omission():
    judge_result = {
        "concerns": ["No mention of SQL injection risk in the dynamic query construction."],
        "assumptions": ["Input is sanitized upstream — not verified."],
        "flagged": True,
    }
    with patch("app.pipeline.adversarial.llm.chat_json", AsyncMock(return_value=judge_result)):
        result = await run(
            query="Does this database query look correct?",
            response="Yes, the query looks fine and should return the right results.",
            domain="technical",
        )

    assert result.flagged is True
    assert len(result.concerns) == 1
    assert "SQL injection" in result.concerns[0]
    assert result.domain == "technical"


@pytest.mark.asyncio
async def test_no_flag_when_response_is_complete():
    judge_result = {
        "concerns": [],
        "assumptions": [],
        "flagged": False,
    }
    with patch("app.pipeline.adversarial.llm.chat_json", AsyncMock(return_value=judge_result)):
        result = await run(
            query="Is paracetamol safe at the recommended dose?",
            response=(
                "At recommended doses paracetamol is safe for most adults. "
                "Overdose risk is serious — do not exceed 4g/day. "
                "Avoid if you have liver conditions or drink heavily."
            ),
            domain="medical",
        )

    assert result.flagged is False
    assert result.concerns == []


@pytest.mark.asyncio
async def test_auto_domain_classification():
    judge_result = {"concerns": [], "assumptions": [], "flagged": False}
    with patch("app.pipeline.adversarial.llm.chat_json", AsyncMock(return_value=judge_result)):
        result = await run(
            query="Is this authentication token implementation secure?",
            response="Looks good.",
        )
    assert result.domain == "technical"  # classify_domain maps auth/token/security → technical
