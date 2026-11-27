"""E9: the three new questions have paired examples, none close to any dev or
held-out text (G43 and G44 included) or to another question's examples.
Failures name only questions and example positions, never a case's text. No network."""
from __future__ import annotations

from app.pipeline import jev_ground as jg
from eval import g44_heldout
from tests.test_e7_questions import _dev_texts
from tests.test_g43_heldout import _too_close
from tests.test_g44_heldout import _all_criteria_examples

_TABLES = {"only_investigation": jg._E9_ONLY_INVESTIGATION, "plan_acts_on_cause": jg._E9_ACTS_ON_CAUSE,
           "only_investigation_a2": jg._E9_ONLY_INVESTIGATION_A2}


def _examples() -> list[tuple[str, str, int, str]]:
    out = []
    for name, (_, yes, no) in _TABLES.items():
        for side, d in (("yes", yes), ("no", no)):
            out += [(name, side, i, t) for i, t in enumerate(d["examples"])]
    for level, d in jg._E9_CAUSE_LEVEL[1].items():
        out += [("cause_level", level, i, t) for i, t in enumerate(d["examples"])]
    return out


def _all_case_texts() -> list[str]:
    out = list(_dev_texts())
    for c in g44_heldout.load():
        out += list(c.user_turns)
    return out


def test_the_battery_asks_the_three_questions():
    for conv in (False, True):
        b = jg.e9_battery(conv)
        assert set(b) == set(jg.E9_QUESTIONS)
        assert b["cause_level"]["type"] == "choice"
        assert set(b["cause_level"]["criteria"]) == {"none", "implied", "asserted", "evidenced"}


def test_every_side_and_level_has_two_examples():
    short = [(n, s) for n, (_, yes, no) in _TABLES.items() for s, d in (("yes", yes), ("no", no))
             if len(d["examples"]) < 2]
    short += [("cause_level", k) for k, d in jg._E9_CAUSE_LEVEL[1].items() if len(d["examples"]) < 2]
    assert not short, short


def test_no_example_is_close_to_a_dev_or_held_out_text():
    texts = _all_case_texts()
    bad = [(n, s, i) for n, s, i, t in _examples() if _too_close(t, texts)]
    assert not bad, bad


def test_no_example_is_close_to_an_earlier_questions_examples():
    mine = {t for *_, t in _examples()}
    earlier = [t for t in _all_criteria_examples() if t not in mine]
    bad = [(n, s, i) for n, s, i, t in _examples() if _too_close(t, earlier)]
    assert not bad, bad


def test_the_three_questions_use_different_situations():
    by = {}
    for n, _, _, t in _examples():
        by.setdefault(n, []).append(t)
    names = list(by)
    same = {frozenset(("only_investigation", "only_investigation_a2"))}   # A2 rewords A, same situation
    bad = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
           if frozenset((a, b)) not in same and any(_too_close(t, by[b]) for t in by[a])]
    assert not bad, bad


def test_a2_changes_one_sentence_and_adds_one_yes_example():
    a, a2 = jg._E9_ONLY_INVESTIGATION, jg._E9_ONLY_INVESTIGATION_A2
    assert a2[0].replace("already committed to a fix that goes ahead whatever they find",
                         "also chosen a fix") == a[0]
    assert a2[1]["examples"][:2] == a[1]["examples"] and len(a2[1]["examples"]) == 3
    assert a2[2]["examples"] == a[2]["examples"]
