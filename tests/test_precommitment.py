import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.precommitment import run, classify_domain


def test_domain_classification():
    assert classify_domain("Should I take ibuprofen for a fever?") == "medical"
    assert classify_domain("Is this SQL query safe from injection?") == "technical"
    assert classify_domain("Should I invest in index funds?") == "financial"
    assert classify_domain("Can I break this contract?") == "legal"
    assert classify_domain("What time does the sun set?") == "general"


@pytest.mark.asyncio
async def test_flags_inconsistency():
    criteria = "Medical claims require RCT evidence, replication, and absence of conflicts of interest."
    judge_result = {
        "consistent": False,
        "dropped_standards": ["RCT evidence requirement", "conflict of interest check"],
        "score": 0.3,
        "reasoning": "Response endorsed an anecdote without applying stated evidentiary standards.",
    }

    with (
        patch("app.pipeline.precommitment.store.get_json", AsyncMock(return_value={"criteria": criteria})),
        patch("app.pipeline.precommitment.llm.chat", AsyncMock(return_value="That sounds right to me!")),
        patch("app.pipeline.precommitment.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await run(
            query="I'm certain this supplement cures inflammation. Is it effective?",
            conversation_messages=[{"role": "user", "content": "I'm certain this supplement cures inflammation. Is it effective?"}],
            domain="medical",
            session_id="test-session",
        )

    assert result.flagged is True
    assert result.consistency_score == 0.3
    assert "RCT evidence requirement" in result.dropped_standards
