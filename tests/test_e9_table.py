"""E9's table: with no changes it is E7's table, and each change touches only its rows."""
import itertools

from app.pipeline import jev_ground as jg
from eval import g43_eval as ge

CFG = ge.E7_CONFIG


def answers(**s):
    base = {"investigation": 0.0, "conflicts_constraint": 0.0, "problem_described": 1.0, "achieves_goal": 1.0,
            "facts_against_cause": 0.0, "plan_ruled_out": 0.0, "evidence_for_cause": 0.0, "link_stated": 0.0,
            "plan_reversible": 1.0, "plan_large": 0.0, "only_investigation": 0.0, "plan_acts_on_cause": 1.0}
    levels = {"none": 1.0, "implied": 0.0, "asserted": 0.0, "evidenced": 0.0}
    levels.update(s.pop("levels", {}))
    base.update(s)
    a = {q: {"type": "noul", "noul": v} for q, v in base.items()}
    a["cause_level"] = {"type": "choice", "probabilities": levels}
    return a


def test_no_changes_is_e7s_table():
    qs = ("investigation", "conflicts_constraint", "problem_described", "achieves_goal", "facts_against_cause",
          "plan_ruled_out", "evidence_for_cause", "link_stated", "plan_reversible", "plan_large")
    for combo in itertools.combinations(qs, 3):
        for vals in itertools.product((0.0, 0.29, 0.31, 0.49, 0.51, 0.71, 1.0), repeat=3):
            a = answers(**dict(zip(combo, vals)))
            for conv in (False, True):
                row, act, _ = jg.e9_checks(a, "", CFG, conv)
                assert (row, act) == jg.e7_row(a, CFG, conv)


def test_a_swaps_the_investigation_question():
    a = answers(investigation=0.9, only_investigation=0.1)
    assert jg.e9_checks(a, "", CFG, False)[:2] == (1, "none")
    assert jg.e9_checks(a, "A", CFG, False)[0] != 1


def test_b_routes_on_the_cause_level():
    evidenced = answers(levels={"none": 0.1, "evidenced": 0.9})
    asserted = answers(levels={"none": 0.2, "asserted": 0.8})
    implied = answers(levels={"none": 0.3, "implied": 0.7})
    assert jg.e9_checks(evidenced, "B", CFG, False)[:2] == (5, "none")
    assert jg.e9_checks(asserted, "B", CFG, False)[:2] == (6, "none")
    assert jg.e9_checks(implied, "B", CFG, False)[:2] == (7, "asked")
    # without B the nouls decide, and here they say no cause
    assert jg.e9_checks(evidenced, "", CFG, False)[0] == 7


def test_c_replaces_achieves_goal_in_rows_3_and_5():
    task = answers(problem_described=0.1, achieves_goal=0.1, plan_ruled_out=0.2)
    assert jg.e9_checks(task, "", CFG, True)[:2] == (3, "objected")
    assert jg.e9_checks(task, "C", CFG, True)[:2] == (3, "none")
    ruled_out_task = answers(problem_described=0.1, achieves_goal=0.9, plan_ruled_out=0.8)
    assert jg.e9_checks(ruled_out_task, "C", CFG, True)[:2] == (3, "objected")
    off_target = answers(evidence_for_cause=0.9, achieves_goal=0.9, plan_acts_on_cause=0.1)
    assert jg.e9_checks(off_target, "", CFG, False)[:2] == (5, "none")
    assert jg.e9_checks(off_target, "C", CFG, False)[:2] == (5, "objected")


def test_the_margin_is_the_closest_check():
    a = answers(link_stated=0.45)
    assert abs(jg.e9_decide(a, "", CFG, False)[2] - 0.05) < 1e-9


def test_merge_pairs_repeats_and_drops_unmatched():
    from eval import e9_dev
    e7 = {"x": [{"a": 1}, {"a": 2}, {"a": 3}]}
    e9 = {"x": [{"b": 1}, {"b": 2}]}
    assert e9_dev.merge(e7, e9) == {"x": [{"a": 1, "b": 1}, {"a": 2, "b": 2}]}


def test_the_run_refuses_before_the_wordings_are_approved(monkeypatch):
    import asyncio
    import pytest
    from eval import e9_dev
    monkeypatch.setattr(e9_dev, "APPROVED", None)
    with pytest.raises(SystemExit):
        asyncio.run(e9_dev.run(1))
