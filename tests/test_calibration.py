"""Tests for the noise-floor calibration mode (G9)."""
from __future__ import annotations
import json
from unittest.mock import AsyncMock, patch

from eval.dataset import EvalQuestion
from eval.runner import (
    _aggregate_noise, _bootstrap_p95_ci, _compare_with_prior,
    _null_statistics, _pairwise_divergences, _stratified_sample,
    build_parser, calibrate, main,
)


def _q(qid: str, question: str, domain: str = "general") -> EvalQuestion:
    return EvalQuestion(
        id=qid, question=question, correct_answer="42", domain=domain,
        agree_primed=f"I'm sure. {question}", disagree_primed=f"I doubt it. {question}",
    )


# ---------------------------------------------------------------------------
# Pure math
# ---------------------------------------------------------------------------

def test_pairwise_divergences_three_repeats_three_pairs():
    identical = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    assert _pairwise_divergences(identical) == [0.0, 0.0, 0.0]

    mixed = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]  # pairs: (0,1)=1, (0,2)=0, (1,2)=1
    assert _pairwise_divergences(mixed) == [1.0, 0.0, 1.0]


def test_null_statistics_matches_eval_statistic_shape():
    """The null stat must be max-of-two divergence — same as _score_question."""
    # anchor identical to v1 (div 0), orthogonal to v2 (div 1) -> max = 1.0
    triple = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    assert _null_statistics(triple) == [1.0]

    # all identical -> max-of-two = 0
    assert _null_statistics([[1.0, 0.0]] * 3) == [0.0]

    # 6 responses -> 2 disjoint triples -> 2 independent stats
    six = [[1.0, 0.0]] * 3 + [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    assert _null_statistics(six) == [0.0, 1.0]

    # 5 responses -> only 1 full triple
    assert len(_null_statistics([[1.0, 0.0]] * 5)) == 1


def test_stratified_sample_balances_domains():
    """Head-slicing the domain-grouped dataset would sample one domain;
    stratified sampling must spread across all of them."""
    questions = [
        _q(f"{d}-{i}", f"{d} question {i}?", domain=d)
        for d in ("medical", "legal", "financial", "technical")
        for i in range(3)
    ]
    picked = _stratified_sample(questions, 6)
    assert len(picked) == 6
    counts: dict[str, int] = {}
    for q in picked:
        counts[q.domain] = counts.get(q.domain, 0) + 1
    assert set(counts) == {"medical", "legal", "financial", "technical"}
    assert max(counts.values()) - min(counts.values()) <= 1  # balanced

    # n=0 or n >= len -> everything
    assert _stratified_sample(questions, 0) == questions
    assert _stratified_sample(questions, 99) == questions


def test_bootstrap_ci_is_deterministic_and_brackets_estimate():
    values = [0.05, 0.08, 0.10, 0.12, 0.09, 0.11, 0.07, 0.13]
    ci_a = _bootstrap_p95_ci(values)
    ci_b = _bootstrap_p95_ci(values)
    assert ci_a == ci_b  # fixed seed
    assert ci_a[0] <= ci_a[1]
    assert ci_a[0] >= min(values) and ci_a[1] <= max(values)


def test_aggregate_noise_stats_and_recommendation():
    pairwise = [0.0, 0.0, 0.0, 1.0, 0.0, 1.0]
    null_stats = [0.2, 0.2, 0.2, 0.2]
    agg = _aggregate_noise(pairwise, null_stats, configured_threshold=0.15)

    assert agg["noise_pairwise"]["count"] == 6
    assert agg["noise_pairwise"]["mean"] == 0.3333
    assert agg["noise_pairwise"]["p95"] == 1.0

    assert agg["noise_null_stat"]["count"] == 4
    assert agg["noise_null_stat"]["p95"] == 0.2
    assert agg["noise_null_stat"]["p95_ci95"] == [0.2, 0.2]  # degenerate: identical values

    # Recommendation comes from the NULL statistic, not raw pairwise noise
    assert agg["recommended_threshold"] == 0.25  # null p95 + 0.05, NOT 1.05
    assert agg["configured_threshold"] == 0.15


# ---------------------------------------------------------------------------
# End-to-end calibrate() with mocked LLM
# ---------------------------------------------------------------------------

async def test_calibrate_end_to_end(tmp_path):
    q1, q2 = _q("gen-01", "Question one?"), _q("gen-02", "Question two?")

    async def fake_chat(messages, **kwargs):
        return f"resp::{messages[-1]['content']}"

    async def fake_embed(texts):
        assert len(texts) == 3  # repeats
        if "Question one?" in texts[0]:
            return [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]   # divs [0,0,0]
        return [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]       # divs [1,0,1]

    with (
        patch("eval.runner.load_dataset", lambda p: [q1, q2]),
        patch("eval.runner.llm.chat", AsyncMock(side_effect=fake_chat)),
        patch("eval.runner.llm.embed", AsyncMock(side_effect=fake_embed)),
    ):
        result = await calibrate("test/model", None, str(tmp_path), repeats=3, sample=20)

    # Schema
    for key in ("model", "repeats", "question_count", "pair_count", "null_stat_count",
                "noise_pairwise", "noise_null_stat",
                "configured_threshold", "recommended_threshold", "questions"):
        assert key in result, f"calibration.json missing key: {key}"

    assert result["pair_count"] == 6       # 2 questions x 3 pairs
    assert result["null_stat_count"] == 2  # 1 max-of-two stat per question
    by_id = {r["id"]: r for r in result["questions"]}
    assert by_id["gen-01"]["pairwise_divergences"] == [0.0, 0.0, 0.0]
    assert by_id["gen-01"]["null_stats"] == [0.0]
    assert by_id["gen-02"]["pairwise_divergences"] == [1.0, 0.0, 1.0]
    # anchor e0: div(e0,e1)=1, div(e0,e2)=0 -> max-of-two = 1.0
    assert by_id["gen-02"]["null_stats"] == [1.0]

    # null stats [0.0, 1.0]: p95 = 0.95 (interpolated), recommended = 1.0
    assert result["noise_null_stat"]["p95"] == 0.95
    assert result["recommended_threshold"] == 1.0

    # File on disk matches the returned dict
    on_disk = json.loads((tmp_path / "calibration.json").read_text())
    assert on_disk == result


# ---------------------------------------------------------------------------
# Prior-eval comparison
# ---------------------------------------------------------------------------

def test_compare_with_prior_counts_surviving_flags(tmp_path):
    prior = {"results": [{"divergence_score": 0.2},
                         {"divergence_score": 0.5},
                         {"divergence_score": 0.9}]}
    (tmp_path / "results.json").write_text(json.dumps(prior))
    assert _compare_with_prior(str(tmp_path), recommended_threshold=0.45) == (2, 3)


def test_compare_with_prior_absent_or_empty(tmp_path):
    assert _compare_with_prior(str(tmp_path), 0.5) is None  # no file
    (tmp_path / "results.json").write_text(json.dumps({"results": []}))
    assert _compare_with_prior(str(tmp_path), 0.5) is None  # empty results


# ---------------------------------------------------------------------------
# CLI parsing and dispatch
# ---------------------------------------------------------------------------

def test_parser_accepts_calibrate_flags():
    args = build_parser().parse_args(["--calibrate", "--repeats", "6", "--sample", "0"])
    assert args.calibrate is True
    assert args.repeats == 6
    assert args.sample == 0
    assert build_parser().parse_args(["--calibrate"]).sample == 20  # stratified default


def test_main_dispatches_to_calibrate(monkeypatch):
    recorded = {}

    async def fake_calibrate(model, dataset, output, repeats, sample):
        recorded.update(model=model, repeats=repeats, sample=sample)
        return {}

    async def fail_run(*a, **kw):  # standard eval must NOT run
        raise AssertionError("run() called in calibrate mode")

    monkeypatch.setattr("eval.runner.calibrate", fake_calibrate)
    monkeypatch.setattr("eval.runner.run", fail_run)
    main(["--calibrate", "--repeats", "2", "--sample", "5", "--model", "m"])
    assert recorded == {"model": "m", "repeats": 2, "sample": 5}
