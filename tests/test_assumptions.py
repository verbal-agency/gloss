"""G27 spike — unit coverage with the LLM mocked (no live calls).

Proves the extractor parses into the schema and that the go/no-go metric math is
correct. The actual faithfulness numbers come from the live harness
(`eval.assumptions_spike`), which is spend-gated and run separately.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.pipeline import assumptions
from app.pipeline.assumptions import AssumptionResult
from eval.assumptions_spike import QueryOutcome, summarize


async def test_extract_parses_into_schema():
    payload = {
        "premises": ["the stack is appropriate for the task"],
        "questionable": ["that this stack is necessary for a simple to-do list"],
        "reasoning": "the query presupposes a heavy stack for a trivial task",
    }
    with patch("app.llm.chat_json", AsyncMock(return_value=payload)):
        result = await assumptions.extract("How do I use React+Redux+Mongo for a to-do list?")
    assert isinstance(result, AssumptionResult)
    assert result.questionable == payload["questionable"]
    assert result.premises == payload["premises"]


async def test_extract_faithful_empty_questionable():
    # A clean query: premises may exist, but questionable must be allowed to be empty.
    payload = {"premises": ["HTTPS is in use"], "questionable": [], "reasoning": "well-posed"}
    with patch("app.llm.chat_json", AsyncMock(return_value=payload)):
        result = await assumptions.extract("How does HTTPS keep data secure in transit?")
    assert result.questionable == []


def _outcome(fired: bool) -> QueryOutcome:
    r = AssumptionResult(
        premises=["p"], questionable=["q"] if fired else [], reasoning="r"
    )
    return QueryOutcome("query", r)


def test_summarize_rates():
    # 3/4 loaded fired -> 0.75 recall; 1/4 clean fired -> 0.25 false-positive
    loaded = [_outcome(True), _outcome(True), _outcome(True), _outcome(False)]
    clean = [_outcome(False), _outcome(False), _outcome(False), _outcome(True)]
    s = summarize(loaded, clean)
    assert s["detection_rate"] == 0.75
    assert s["false_positive_rate"] == 0.25
    assert s["detected"] == 3
    assert s["false_positives"] == 1
