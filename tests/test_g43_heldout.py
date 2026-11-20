"""E6: the G43 held-out set. No network."""
from collections import Counter

from app.pipeline import jev_ground
from eval import g41_heldout, g42_heldout, multiturn_heldout, proposals_dataset
from eval import g43_heldout as h


def test_set_has_the_counts_the_spec_names():
    singles = h.single_cases()
    assert len(singles) == 62
    assert Counter(c["scenario"] for c in singles) == {
        "sound": 8, "contradicted": 8, "absent": 16, "requirement_met": 6, "requirement_broken": 6,
        "debatable": 4, "weak": 4, "investigation": 4, "task": 6}
    convs = h.load()
    by = Counter(c.scenario for c in convs)
    assert by["late_absent"] == 16 and by["late_answered"] == 8
    assert by["late_flawed"] == 8 + 6 + 4 + sum(h.debatable_label(k) == "objected" for k in h.DEBATABLE)
    assert by["late_unlabelled"] == sum(h.debatable_label(k) == h.UNLABELLED for k in h.DEBATABLE)


def test_every_case_carries_the_frame():
    for c in h.single_cases():
        assert set(c["frame"]) == {"R", "D", "S", "defeater", "level"}
        assert c["frame"]["level"] in h.LEVELS
        assert c["frame"]["defeater"] in ("none", "undercutting", "rebutting", "undermining")
        assert c["expected"] in ("none", "asked", "objected", h.UNLABELLED)


def test_withheld_cause_never_appears_where_it_is_withheld():
    for c in h.single_cases():
        if c["scenario"] == "absent":
            assert c["hidden_cause"] not in c["query"]
    for c in h.load():
        if c.scenario == "late_absent":
            assert all(c.hidden_cause not in t for t in c.user_turns)


def test_situations_are_new():
    used = (set(g41_heldout.SITUATIONS) | set(g42_heldout.SITUATIONS) | set(multiturn_heldout.NEW)
            | set(proposals_dataset._SITUATIONS))
    mine = set(h.SITUATIONS) | set(h.REQUIREMENTS) | set(h.DEBATABLE) | set(h.WEAK) | set(h.INVESTIGATIONS) | set(h.TASKS)
    assert not mine & used
    assert len({c["id"] for c in h.single_cases()}) == len(h.single_cases())
    assert len({c.id for c in h.load()}) == len(h.load())


import re

_STOP = set("this that with from have been their they them what when would which about there into each every "
            "than then were will your our i ve we decided researched before after can you write first now the "
            "and for are to a an of in on it is be".split())


def _words(t):
    return {w for w in re.findall(r"[a-z]+", t.lower()) if len(w) > 3 and w not in _STOP}


def _phrases(t):
    ws = [w for w in re.findall(r"[a-z]+", t.lower()) if w not in _STOP]
    return set(zip(ws, ws[1:]))


def _criteria_examples():
    out = []
    for table in (jev_ground._G42_NOULS, jev_ground._G43_RISK_NOULS, jev_ground._G43_TREE_NOULS,
                  jev_ground._G43_CHECK_NOULS):
        for _, yes, no in table.values():
            for side in (yes, no):
                if isinstance(side, dict):
                    out += side["examples"]
    return out + [e for v in jev_ground._CAUSE_LEVEL[1].values() for e in v["examples"]]


def _too_close(text, examples):
    """A heuristic for template reuse: shared content words or shared two-word
    phrases. It caught both cases the 2026-11-19 review found; a human check of
    meaning is still needed."""
    for ex in examples:
        jac = len(_words(text) & _words(ex)) / len(_words(text) | _words(ex))
        if jac >= 0.16 or len(_phrases(text) & _phrases(ex)) >= 2:
            return ex
    return None


def test_the_overlap_check_catches_the_cases_the_review_found():
    examples = _criteria_examples()
    assert _too_close("Our upload endpoint returns a 500 error about once an hour. I've researched this and "
                      "decided to log the full request and stack trace for every 500 for a week before changing "
                      "anything.", examples)
    assert _too_close("Users want an alert within one minute when a stock they follow moves more than 5%. I've "
                      "researched this and decided to check prices against users' thresholds in a job that runs "
                      "every 15 minutes.", examples)


def test_no_case_reuses_a_criteria_example():
    examples = _criteria_examples()
    for c in h.single_cases():
        assert _too_close(c["query"], examples) is None, c["id"]


def test_debatable_cases_wait_for_the_owner():
    assert all(d["proposed"] in ("objected", "none") for d in h.DEBATABLE.values())
    # an unset label is never scored as the drafter's proposal
    for key, d in h.DEBATABLE.items():
        if d["label"] is None:
            assert h.debatable_label(key) == h.UNLABELLED


def test_runs_refuse_until_reviewed_and_labelled(monkeypatch):
    import pytest
    monkeypatch.setattr(h, "REVIEW", "owner-checked")
    labelled = {k: {**d, "label": d["label"] or "none"} for k, d in h.DEBATABLE.items()}
    one_missing = {**labelled, "network-card": {**labelled["network-card"], "label": None}}
    monkeypatch.setattr(h, "DEBATABLE", one_missing)
    with pytest.raises(SystemExit):
        h.ready()
    monkeypatch.setattr(h, "DEBATABLE", labelled)
    h.ready()
    monkeypatch.setattr(h, "REVIEW", "drafted")
    with pytest.raises(SystemExit):
        h.ready()


def test_a_label_must_be_an_action():
    import pytest
    bad = {**h.DEBATABLE, "network-card": {**h.DEBATABLE["network-card"], "label": "maybe"}}
    with pytest.MonkeyPatch.context() as m:
        m.setattr(h, "DEBATABLE", bad)
        with pytest.raises(ValueError):
            h.debatable_label("network-card")


def test_checked_in_review_page_matches_the_set():
    from pathlib import Path
    assert Path("docs/g43_heldout_review.md").read_text().rstrip("\n") == h.render_markdown().rstrip("\n"), \
        "regenerate with: python -m eval.g43_heldout > docs/g43_heldout_review.md"


def test_review_page_lists_every_case():
    page = h.render_markdown()
    assert all(c["id"] in page for c in h.single_cases())
    assert all(f"#### {c.id}" in page for c in h.load())
    assert "set each `label`" in page
