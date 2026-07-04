import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.pipeline.temporal import extract_and_store, check_arc, ClaimSnapshot
import time


def _make_snapshot(turn: int, claims: list[str], embedding: list[float]) -> dict:
    return ClaimSnapshot(
        turn=turn,
        claims=claims,
        embedding=embedding,
        user_message_preview=f"user turn {turn}",
        timestamp=time.time(),
    ).model_dump()


@pytest.mark.asyncio
async def test_no_flag_below_turn_threshold():
    result = await check_arc("test-session", turn=2)
    assert result is None


@pytest.mark.asyncio
async def test_flags_arc_drift():
    # Early turn: confident risk assessment
    early = _make_snapshot(
        turn=1,
        claims=["This approach has significant security vulnerabilities.", "SQL injection is likely."],
        embedding=[1.0, 0.0, 0.0],
    )
    # Later turn: risks have quietly disappeared
    late = _make_snapshot(
        turn=6,
        claims=["This approach looks reasonable.", "The code should work fine."],
        embedding=[-0.9, 0.4, 0.0],  # meaningfully different direction
    )

    judge_result = {
        "disappeared_claims": ["This approach has significant security vulnerabilities.", "SQL injection is likely."],
        "justified_by_new_info": False,
        "drift_score": 0.75,
        "reasoning": "Security concerns named in turn 1 are absent in turn 6 with no new mitigating information.",
    }

    with (
        patch("app.pipeline.temporal.store.lrange_json", AsyncMock(return_value=[early, late])),
        patch("app.pipeline.temporal.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await check_arc("test-session", turn=6)

    assert result is not None
    assert result.flagged is True
    assert result.drift_score == 0.75
    assert len(result.disappeared_claims) == 2
    assert "security" in result.summary.lower() or "turn 1" in result.summary


@pytest.mark.asyncio
@pytest.mark.parametrize("judge_score,should_flag", [(0.5, False), (0.7, True)])
async def test_judge_score_uses_judge_threshold_not_embedding_threshold(judge_score, should_flag):
    """G7: the judge's 0-1 score is compared against DRIFT_JUDGE_THRESHOLD
    (0.6), not the embedding-scale DRIFT_THRESHOLD (0.20)."""
    early = _make_snapshot(turn=1, claims=["A is risky."], embedding=[1.0, 0.0, 0.0])
    late  = _make_snapshot(turn=5, claims=["A is fine."],  embedding=[-0.9, 0.4, 0.0])

    judge_result = {
        "disappeared_claims": ["A is risky."],
        "justified_by_new_info": False,
        "drift_score": judge_score,
        "reasoning": "test",
    }
    with (
        patch("app.pipeline.temporal.store.lrange_json", AsyncMock(return_value=[early, late])),
        patch("app.pipeline.temporal.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await check_arc("test-session", turn=5)

    assert (result is not None) == should_flag


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [(5, 5), (99, None), (None, None)])
async def test_pressure_turn_is_judge_attributed_or_none(raw, expected):
    """G7: pressure_turn comes from the judge and must reference a real
    intervening turn — otherwise None. Never fabricated."""
    early = _make_snapshot(turn=1, claims=["A is risky."], embedding=[1.0, 0.0, 0.0])
    late  = _make_snapshot(turn=5, claims=["A is fine."],  embedding=[-0.9, 0.4, 0.0])

    judge_result = {
        "disappeared_claims": ["A is risky."],
        "justified_by_new_info": False,
        "drift_score": 0.8,
        "pressure_turn": raw,
        "reasoning": "test",
    }
    with (
        patch("app.pipeline.temporal.store.lrange_json", AsyncMock(return_value=[early, late])),
        patch("app.pipeline.temporal.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await check_arc("test-session", turn=5)

    assert result is not None
    assert result.pressure_turn == expected


@pytest.mark.asyncio
async def test_no_flag_when_justified_by_new_info():
    early = _make_snapshot(turn=1, claims=["X has risk Y."], embedding=[1.0, 0.0, 0.0])
    late  = _make_snapshot(turn=5, claims=["X is safe given mitigation Z."], embedding=[-0.8, 0.0, 0.0])

    judge_result = {
        "disappeared_claims": ["X has risk Y."],
        "justified_by_new_info": True,
        "drift_score": 0.60,
        "reasoning": "User introduced mitigation Z which addresses the earlier concern.",
    }

    with (
        patch("app.pipeline.temporal.store.lrange_json", AsyncMock(return_value=[early, late])),
        patch("app.pipeline.temporal.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await check_arc("test-session", turn=5)

    assert result is None
