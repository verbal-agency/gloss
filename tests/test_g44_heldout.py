"""E9: the G44 late-flaw held-out set. No network."""
from collections import Counter, defaultdict

from app.pipeline import jev_ground
from eval import (evidence_dev, g41_heldout, g42_heldout, g43_heldout, multiturn_eval, multiturn_heldout,
                  nuanced_dev, proposals_dataset, stakes_dev)
from eval import g44_heldout as h
from tests.test_g43_heldout import _too_close


def test_set_has_the_counts_the_spec_names():
    by = Counter(c.scenario for c in h.load())
    assert by == {"late_fact_for": 8, "late_fact_against": 8, "late_switch_fits": 8, "late_switch_misses": 8,
                  "late_req_met": 6, "late_req_broken": 6, "late_problem_stated": 10, "late_problem_absent": 10}
    verdicts = Counter(h.EXPECTED[c.scenario] for c in h.load())
    assert verdicts == {"none": 32, "objected": 14, "asked": 18}
    assert len({c.id for c in h.load()}) == 64


def test_situations_are_new():
    used = (set(g41_heldout.SITUATIONS) | set(g42_heldout.SITUATIONS) | set(multiturn_heldout.NEW)
            | set(proposals_dataset._SITUATIONS) | set(evidence_dev.SITUATIONS) | set(stakes_dev.PAIRS)
            | set(g43_heldout.SITUATIONS) | set(g43_heldout.REQUIREMENTS) | set(g43_heldout.DEBATABLE)
            | set(g43_heldout.WEAK) | set(g43_heldout.INVESTIGATIONS) | set(g43_heldout.TASKS)
            | {c["family"] for c in nuanced_dev.cases()})
    mine = list(h.SITUATIONS) + list(h.REQUIREMENTS) + list(h.PROBLEMS)
    assert len(mine) == len(set(mine)) and not set(mine) & used


def test_only_the_last_turn_differs_within_a_family():
    by = defaultdict(list)
    for c in h.load():
        by[c.family].append(c)
    for family, convs in by.items():
        assert len({tuple(c.user_turns[:2]) for c in convs}) == 1, family
        assert len({c.user_turns[2] for c in convs}) == len(convs), family
        assert all(len(c.user_turns) == 3 for c in convs)


def test_fact_twins_share_the_request_and_cause_twins_differ_by_the_cause():
    for s in h.SITUATIONS.values():
        assert s["fact_for"] != s["fact_against"]
    by = {c.id: c for c in h.load()}
    for key, p in h.PROBLEMS.items():
        stated, absent = by[f"g44/late_problem_stated/{key}"], by[f"g44/late_problem_absent/{key}"]
        assert all(p["cause"] not in t for t in absent.user_turns)
        assert stated.user_turns[2].replace(f" {p['cause']}", "") == absent.user_turns[2]


def test_every_flawed_case_says_why_and_every_case_has_a_frame():
    for c in h.load():
        assert (c.flaw is not None) == (h.EXPECTED[c.scenario] == "objected"), c.id
        f = h.frame(c)
        assert set(f) == {"R", "D", "S", "defeater", "level"} and all(f.values())
        assert f["level"] in g43_heldout.LEVELS
        assert f["defeater"] in ("none", "undercutting", "rebutting", "undermining")


def _all_criteria_examples():
    """Every example list in the Jev question tables, found by walking the module."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "examples":
                    out.extend(v)
                else:
                    walk(v)
        elif isinstance(x, (tuple, list)):
            for v in x:
                walk(v)

    for name, value in vars(jev_ground).items():
        if name.startswith("_") and name[1:2].isupper():
            walk(value)
    return out


def test_no_turn_reuses_a_criteria_example():
    examples = _all_criteria_examples()
    assert len(examples) > 40
    for c in h.load():
        for turn in (c.user_turns[0], c.user_turns[2]):
            assert _too_close(turn, examples) is None, c.id


def test_recording_sees_sound_histories_and_refuses_before_the_review(monkeypatch):
    import asyncio
    import pytest
    from eval import g43_eval as e
    view = h.history_view()
    assert len(view) == 64 and {c.scenario for c in view} == {"late_sound"}
    for c, original in zip(view, h.load()):
        assert c.id == original.id and c.user_turns == original.user_turns
        assert multiturn_eval.request_of(c, 0).startswith("First, can you")
    monkeypatch.setattr(h, "REVIEW", "drafted")
    with pytest.raises(SystemExit):
        asyncio.run(e.record_g44(1))


def test_checked_in_review_page_matches_the_set():
    from pathlib import Path
    assert Path("docs/g44_heldout_review.md").read_text().rstrip("\n") == h.render_markdown().rstrip("\n"), \
        "regenerate with: python -m eval.g44_heldout > docs/g44_heldout_review.md"
    page = h.render_markdown()
    assert all(f"#### {c.id}" in page for c in h.load())
