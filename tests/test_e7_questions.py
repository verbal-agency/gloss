"""E7c: the five E7 questions have paired examples, none close to any dev or held-out text or to
another question's examples. Failures name only questions and example positions."""
from __future__ import annotations

from app.pipeline import jev_ground as jg
from eval import facts_against_dev, multiturn_heldout, nuanced_dev
from tests.test_g43_heldout import _too_close
from tests.test_nuanced_dev import _earlier_texts

_NAMES = ("facts_against_cause", "plan_ruled_out", "evidence_for_cause", "plan_large", "plan_reversible")
_NEW_QUESTIONS = {
    "facts_against_cause": (
        "Does something the user reports show that the cause their plan acts on, stated or only implied by "
        "the plan, is not what is happening? Not merely that another cause is also at work."),
    "plan_ruled_out": (
        "Do the user's own facts show that the plan cannot deliver what they need, whatever the real cause "
        "turns out to be?"),
}


def _examples(name: str) -> list[tuple[str, int, str]]:
    _, yes, no = jg._E7_NOULS[name]
    return [(side, i, t) for side, d in (("yes", yes), ("no", no)) for i, t in enumerate(d["examples"])]


def _new_examples(name: str) -> list[tuple[str, int, str]]:
    kept = {"evidence_for_cause": jg._E5C_NOULS, "plan_large": jg._E5D_NOULS, "plan_reversible": jg._E5D_NOULS}
    if name not in kept:
        return _examples(name)
    old = {t for d in kept[name][name][1:] for t in d["examples"]}
    return [e for e in _examples(name) if e[2] not in old]


def _dev_texts() -> list[str]:
    out = list(_earlier_texts())
    for c in multiturn_heldout.load():
        out += list(c.user_turns)
    for c in nuanced_dev.cases():
        out += nuanced_dev.texts(c)
    for c in facts_against_dev.cases():
        out += facts_against_dev.texts(c)
    return out


def test_the_five_questions_exist_and_the_new_ones_use_the_spec_wording():
    assert set(_NAMES) <= set(jg._E7_NOULS)
    for name, text in _NEW_QUESTIONS.items():
        assert jg._E7_NOULS[name][0] == text


def test_every_question_has_two_yes_and_two_no_examples():
    short = [n for n in _NAMES
             if len(jg._E7_NOULS[n][1]["examples"]) < 2 or len(jg._E7_NOULS[n][2]["examples"]) < 2]
    assert not short, short


def test_kept_examples_are_still_there():
    for name, src in (("evidence_for_cause", jg._E5C_NOULS), ("plan_large", jg._E5D_NOULS),
                      ("plan_reversible", jg._E5D_NOULS)):
        for k in (1, 2):
            assert set(src[name][k]["examples"]) <= set(jg._E7_NOULS[name][k]["examples"]), name


def test_no_new_example_is_close_to_a_dev_or_held_out_text():
    dev = _dev_texts()
    bad = [(n, side, i) for n in _NAMES for side, i, t in _new_examples(n) if _too_close(t, dev)]
    assert not bad, bad


def test_no_new_example_is_close_to_another_questions_examples():
    others = {}
    for n in _NAMES:
        others[n] = [t for _, _, t in _examples(n)]
    for table in (jg._E5C_NOULS, jg._E5D_NOULS, jg._G42_NOULS):
        for n, (_, y, f) in table.items():
            others.setdefault("old:" + n, [])
            others["old:" + n] += y["examples"] + f["examples"]
    bad = []
    for n in _NAMES:
        for side, i, t in _new_examples(n):
            for m, pool in others.items():
                if m == n or (m == "old:" + n):
                    continue
                if _too_close(t, pool):
                    bad.append((n, side, i, m))
    assert not bad, bad
