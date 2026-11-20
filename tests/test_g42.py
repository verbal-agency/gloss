"""G42: the held-out set, the new questions and rules, and the runner's guards. No network."""
from collections import Counter

import pytest

from app.pipeline import jev_ground
from app.pipeline.jev_ground import G42Rule
from eval import g41_heldout, g42_eval as ge, g42_heldout as h
from eval import multiturn_heldout, proposals_dataset


# --------------------------------------------------------------------------- the set

def test_set_has_the_counts_the_spec_names():
    assert Counter(c["scenario"] for c in h.single_cases()) == {
        "sound": 8, "contradicted": 8, "absent": 16, "task": 6}
    convs = h.load()
    assert Counter(c.scenario for c in convs) == {"late_sound": 14, "late_absent": 16, "late_answered": 8}
    assert Counter(h.PATTERN.values()) == {"error-type": 4, "plan-names": 4}
    assert set(h.PATTERN) == set(h.SITUATIONS)


def test_withheld_cause_never_appears_where_it_is_withheld():
    for c in h.single_cases():
        if c["scenario"] == "absent":
            assert c["hidden_cause"] not in c["query"]
    for c in h.load():
        if c.scenario == "late_absent":
            assert all(c.hidden_cause not in t for t in c.user_turns)


def test_situations_are_new():
    used = set(g41_heldout.SITUATIONS) | set(multiturn_heldout.NEW) | set(proposals_dataset._SITUATIONS)
    assert not set(h.SITUATIONS) & used
    assert all(c["id"].startswith("g42/") for c in h.single_cases())
    assert len({c["id"] for c in h.single_cases()}) == len(h.single_cases())


def test_criteria_examples_are_not_from_the_test_set():
    examples = []
    for _, yes, no in jev_ground._G42_NOULS.values():
        examples += yes["examples"] + no["examples"]
    words = [s["problem"].split(" ")[1:4] for s in h.SITUATIONS.values()]
    for ex in examples:
        assert not any(" ".join(w) in ex for w in words)


def test_review_page_lists_every_case():
    page = h.render_markdown()
    assert "# G42 held-out set" in page and f"Review status: {h.REVIEW}" in page
    assert all(c["id"] in page for c in h.single_cases())


# --------------------------------------------------------------------------- battery and rules

def test_battery_is_accepted_by_the_sdk():
    from typesafe_sdk import Choice, Noul
    for conv in (False, True):
        for ignore in (False, True):
            qs = jev_ground.g42_battery(conv, ignore)
            assert set(qs) == {"request", "link", *jev_ground.G42_NOULS}
            for q in qs.values():
                (Choice if q["type"] == "choice" else Noul)(**q)


def test_ignore_confidence_note_reaches_every_question():
    with_note = jev_ground.g42_battery(False, True)
    without = jev_ground.g42_battery(False, False)
    assert all("researched" in q["instructions"] for q in with_note.values())
    assert not any(jev_ground._IGNORE_CONFIDENCE in q["instructions"] for q in without.values())


def test_g41_questions_are_unchanged_without_the_note():
    old = jev_ground.g41_battery("text", True)
    new = jev_ground.g42_battery(True, False)
    assert all(new[k] == old[k] for k in old)


def _a(problem=0.9, cause=0.1, mech=0.1, outside=0.1, contra=0.1, absent=0.6):
    return {"link": {"choice": "absent", "probabilities": {"absent": absent, "stated": 1 - absent,
                                                           "contradicted": 0.0}},
            "request": {"choice": "fix", "probabilities": {}},
            "is_fix": {"noul": 0.8}, "problem_described": {"noul": problem},
            "cause_stated": {"noul": cause}, "contradicted": {"noul": contra},
            "mechanism_stated": {"noul": mech}, "cause_outside_plan": {"noul": outside}}


def test_objection_can_require_evidence():
    no_cause_but_contra = _a(contra=0.33)          # G41's card-failures miss
    assert jev_ground.g42_action(no_cause_but_contra, G42Rule(contra_t=0.3)) == "objected"
    assert jev_ground.g42_action(no_cause_but_contra,
                                 G42Rule(contra_t=0.3, contra_needs_evidence=True)) == "asked"
    stated = _a(contra=0.9, absent=0.05)
    assert jev_ground.g42_action(stated, G42Rule(contra_t=0.3, contra_needs_evidence=True)) == "objected"


def test_all_named_evidence_must_be_present():
    plan_implies = _a(cause=0.9, mech=0.8, outside=0.1, absent=0.05)  # G41's database-disk miss
    assert jev_ground.g42_action(plan_implies, G42Rule(evidence=("cause_stated",), ev_t=0.5)) == "none"
    rule = G42Rule(evidence=("cause_stated", "cause_outside_plan"), ev_t=0.5)
    assert jev_ground.g42_action(plan_implies, rule) == "asked"


def test_rules_are_unique_and_include_g41_s_pick_shape():
    names = [r.name for r in ge.rules()]
    assert len(names) == len(set(names))
    assert "problem_described>=0.3 p_absent>=0.2 contra>=0.3" in names


# --------------------------------------------------------------------------- guards

async def test_runs_refuse_before_the_owner_review(monkeypatch):
    monkeypatch.setattr(h, "REVIEW", "drafted")
    with pytest.raises(SystemExit):
        await ge.run_arm("llm", 1, 1)
    with pytest.raises(SystemExit):
        await ge.record(1)


def test_dev_includes_g41_s_spent_test_set():
    dev = ge.dev_cases()
    assert all(c["split"] == "dev" for c in dev)
    assert sum(c["id"].startswith("g41/") for c in dev) == 70
