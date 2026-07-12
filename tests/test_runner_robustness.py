"""G22: eval runner survives live-scale hazards — malformed JSON, per-question
failures, and a concurrency cap. These are the failures that aborted G15."""
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import app.llm as llm
from eval import runner
from eval.dataset import EvalQuestion


def _q(qid: str) -> EvalQuestion:
    return EvalQuestion(
        id=qid, question="Q?", correct_answer="A", domain="general",
        agree_primed="I'm sure. Q?", disagree_primed="I doubt it. Q?",
    )


# ---------------------------------------------------------------------------
# chat_json: retry-once then typed error
# ---------------------------------------------------------------------------

async def test_chat_json_retries_then_succeeds():
    # first completion is malformed, second is valid
    responses = iter(["not json at all", '{"correct": true}'])

    async def fake_chat(messages, **kwargs):
        return next(responses)

    with patch("app.llm.chat", AsyncMock(side_effect=fake_chat)):
        result = await llm.chat_json([{"role": "user", "content": "x"}])
    assert result == {"correct": True}


async def test_chat_json_raises_typed_error_after_two_failures():
    async def fake_chat(messages, **kwargs):
        return "still not json"

    with patch("app.llm.chat", AsyncMock(side_effect=fake_chat)):
        with pytest.raises(llm.JsonParseError) as exc:
            await llm.chat_json([{"role": "user", "content": "x"}])
    assert "still not json" in exc.value.raw


# ---------------------------------------------------------------------------
# Grader resilience: unparseable grade -> ungraded, not fabricated, not fatal
# ---------------------------------------------------------------------------

async def test_grade_response_returns_none_on_parse_failure():
    with patch("eval.runner.llm.chat_json", AsyncMock(side_effect=llm.JsonParseError("junk"))):
        assert await runner._grade_response("q", "a", "resp") is None


async def test_score_question_drops_accuracy_when_a_grade_fails():
    # divergence still computed; accuracy None because one grade is unparseable
    grades = iter([True, None, True])  # middle grade failed to parse

    async def fake_grade(*a, **k):
        return next(grades)

    with (
        patch("eval.runner.llm.chat", AsyncMock(return_value="a response")),
        patch("eval.runner._grade_response", AsyncMock(side_effect=fake_grade)),
        patch("eval.runner.llm.embed", AsyncMock(return_value=[[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])),
    ):
        result = await runner._score_question(_q("g1"), "m", grade_accuracy=True)
    assert result["accuracy"] is None            # dropped
    assert "divergence_score" in result          # divergence preserved


# ---------------------------------------------------------------------------
# run(): one failing question doesn't abort the batch
# ---------------------------------------------------------------------------

async def test_run_isolates_a_failing_question(tmp_path):
    good, bad = _q("ok"), _q("boom")

    async def fake_score(q, model, grade_accuracy=True):
        if q.id == "boom":
            raise RuntimeError("simulated question failure")
        return {"id": q.id, "domain": q.domain, "question": q.question,
                "divergence_score": 0.5, "flagged": True, "accuracy": None,
                "responses": {}}

    with (
        patch("eval.runner.load_dataset", lambda p: [good, bad]),
        patch("eval.runner._score_question", AsyncMock(side_effect=fake_score)),
    ):
        await runner.run("m", None, str(tmp_path), grade_accuracy=False, concurrency=4)

    import json
    summary = json.loads((tmp_path / "results.json").read_text())
    assert summary["question_count"] == 1   # only the good one
    assert summary["failed_count"] == 1
    assert summary["flagged_count"] == 1


async def test_run_bounded_respects_concurrency_cap():
    live = 0
    peak = 0

    async def worker(item):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1
        return item

    outcomes = await runner._run_bounded(list(range(20)), worker, concurrency=3)
    assert len(outcomes) == 20
    assert all(err is None for _, _, err in outcomes)
    assert peak <= 3, f"concurrency cap exceeded: peak {peak}"
