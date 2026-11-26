"""E7's candidate, code only: the one-request battery and the 7-row decision table
(docs/e7_heldout_run_goal.md; row 4 as fixed by the owner on 2026-11-26). No Jev call."""
from __future__ import annotations

import pytest

from app.pipeline import jev_ground as jg

CFG = jg.E7Config()              # every tuned threshold at 0.5
HIGH = jg.E7Config(t_link=0.7, t_ev=0.7, t_ach_conv=0.3, t_fa=0.7, t_ro=0.7)

# An answer set that falls through to row 7: nothing fires.
BASE = {"investigation": 0.1, "conflicts_constraint": 0.1, "problem_described": 0.9, "achieves_goal": 0.8,
        "facts_against_cause": 0.1, "plan_ruled_out": 0.1, "evidence_for_cause": 0.1, "link_stated": 0.1,
        "plan_reversible": 0.9, "plan_large": 0.1}


def answers(**over: float) -> dict:
    return {k: {"noul": v} for k, v in {**BASE, **over}.items()}


def row(cfg: jg.E7Config = CFG, conversation: bool = False, **over: float) -> tuple[int, str]:
    return jg.e7_row(answers(**over), cfg, conversation)


# --------------------------------------------------------------------------- battery

def test_battery_asks_every_e7_question_in_one_request():
    for conv in (False, True):
        assert tuple(jg.e7_battery(conv)) == jg.E7_QUESTIONS
    assert len(jg.E7_QUESTIONS) == 10


def test_kept_questions_are_e5bs_unchanged():
    for conv in (False, True):
        kept, e5b = jg.e7_battery(conv), jg.e5b_battery(conv)
        assert set(e5b) == set(jg.E7_KEPT)
        for name in jg.E7_KEPT:
            assert kept[name] == e5b[name], name


def test_changed_questions_use_the_e7_wordings_and_examples():
    for conv in (False, True):
        b = jg.e7_battery(conv)
        note = jg._CONVERSATION_NOTE if conv else ""
        for name in jg.E7_CHANGED:
            q, yes, no = jg._E7_NOULS[name]
            assert b[name] == {"type": "noul", "instructions": q + note, "criteria": {"true": yes, "false": no}}


def test_conversation_note_on_every_question_and_overall_plan_note_only_on_achieves_goal():
    conv, single = jg.e7_battery(True), jg.e7_battery(False)
    for name, q in conv.items():
        assert jg._CONVERSATION_NOTE in q["instructions"], name
        assert (jg._E5B_OVERALL in q["instructions"]) == (name == "achieves_goal"), name
    for name, q in single.items():
        assert jg._CONVERSATION_NOTE not in q["instructions"], name
        assert jg._E5B_OVERALL not in q["instructions"], name


def test_questions_can_be_split_into_their_own_requests():
    apart = jg.E7_OWN_REQUESTS["e5d"]
    rest = jg.e7_battery(False, apart=apart)
    own = jg.e7_questions(apart, False)
    assert set(rest) | set(own) == set(jg.E7_QUESTIONS) and not set(rest) & set(own)
    assert own == {k: jg.e7_battery(False)[k] for k in apart}
    with pytest.raises(ValueError):
        jg.e7_questions(("plan_scope",), False)


# --------------------------------------------------------------------------- grid

def test_the_grid_has_the_spec_s_32_configurations():
    cfgs = jg.e7_configs()
    assert len(cfgs) == len(set(cfgs)) == 32
    assert {c.t_link for c in cfgs} == {0.5, 0.7}
    assert {c.t_ev for c in cfgs} == {0.5, 0.7}
    assert {c.t_ach_conv for c in cfgs} == {0.5, 0.3}
    assert {c.t_fa for c in cfgs} == {0.5, 0.7}
    assert {c.t_ro for c in cfgs} == {0.5, 0.7}
    assert sum(c.per_shape for c in cfgs) == 16
    assert len({c.name for c in cfgs}) == 32


# --------------------------------------------------------------------------- rows, one at a time

def test_row_1_investigation_is_quiet_whatever_else_fires():
    assert row(investigation=0.5, conflicts_constraint=0.9, plan_ruled_out=0.9) == (1, "none")
    assert row(investigation=0.49)[0] != 1


def test_row_2_a_broken_stated_requirement_objects():
    assert row(conflicts_constraint=0.5, plan_ruled_out=0.1, achieves_goal=0.9) == (2, "objected")
    assert row(conflicts_constraint=0.49)[0] != 2


def test_row_3_nothing_going_wrong_is_checked_against_the_goal_only():
    assert row(problem_described=0.29, achieves_goal=0.49) == (3, "objected")
    assert row(problem_described=0.29, achieves_goal=0.5) == (3, "none")
    # Row 3 comes before the facts-against branch and the level rows.
    assert row(problem_described=0.29, achieves_goal=0.9, plan_ruled_out=0.9, link_stated=0.9,
               plan_reversible=0.1) == (3, "none")
    assert row(problem_described=0.3)[0] != 3


def test_row_4_facts_against_the_cause_ask():
    assert row(facts_against_cause=0.5) == (4, "asked")
    assert row(HIGH, facts_against_cause=0.69)[0] != 4
    assert row(HIGH, facts_against_cause=0.7) == (4, "asked")


def test_row_4_facts_that_rule_out_the_plan_object_without_facts_against_the_cause():
    # Fixed 2026-11-26: plan_ruled_out fires row 4 on its own.
    assert row(plan_ruled_out=0.5, facts_against_cause=0.1) == (4, "objected")
    assert row(plan_ruled_out=0.5, facts_against_cause=0.9) == (4, "objected")
    assert row(HIGH, plan_ruled_out=0.69, facts_against_cause=0.1)[0] != 4
    assert row(HIGH, plan_ruled_out=0.69, facts_against_cause=0.7) == (4, "asked")
    assert row(HIGH, plan_ruled_out=0.7, facts_against_cause=0.1) == (4, "objected")


def test_row_4_comes_before_evidence_and_rule_b():
    assert row(facts_against_cause=0.9, evidence_for_cause=0.9, achieves_goal=0.9) == (4, "asked")
    assert row(plan_ruled_out=0.9, link_stated=0.9, plan_reversible=0.9) == (4, "objected")


def test_row_5_an_evidenced_cause_is_quiet_unless_the_plan_cant_deliver():
    assert row(evidence_for_cause=0.5, achieves_goal=0.5) == (5, "none")
    assert row(evidence_for_cause=0.5, achieves_goal=0.49) == (5, "objected")
    # Evidence comes before rule (b): a costly plan on an evidenced cause stays quiet.
    assert row(evidence_for_cause=0.5, link_stated=0.9, plan_reversible=0.1, plan_large=0.9) == (5, "none")
    assert row(HIGH, evidence_for_cause=0.69)[0] != 5


def test_row_6_an_asserted_cause_objects_only_behind_a_costly_plan():
    assert row(link_stated=0.5) == (6, "none")
    assert row(link_stated=0.5, plan_reversible=0.49) == (6, "objected")
    assert row(link_stated=0.5, plan_large=0.5) == (6, "objected")
    assert row(link_stated=0.5, plan_reversible=0.5, plan_large=0.49) == (6, "none")
    # Rule (b) does not consult achieves_goal.
    assert row(link_stated=0.5, achieves_goal=0.0) == (6, "none")
    assert row(HIGH, link_stated=0.69)[0] == 7


def test_row_7_an_implied_cause_asks():
    assert row() == (7, "asked")
    assert row(HIGH) == (7, "asked")


# --------------------------------------------------------------------------- t_ach by shape

def test_single_messages_always_use_t_ach_0_5():
    for cfg in (CFG, HIGH):
        assert row(cfg, False, problem_described=0.1, achieves_goal=0.4) == (3, "objected")
        assert row(cfg, False, evidence_for_cause=0.9, achieves_goal=0.4) == (5, "objected")


def test_conversations_use_the_configuration_s_t_ach():
    assert row(CFG, True, problem_described=0.1, achieves_goal=0.4) == (3, "objected")
    assert row(HIGH, True, problem_described=0.1, achieves_goal=0.4) == (3, "none")
    assert row(HIGH, True, problem_described=0.1, achieves_goal=0.29) == (3, "objected")
    assert row(HIGH, True, evidence_for_cause=0.9, achieves_goal=0.4) == (5, "none")
    assert row(HIGH, True, evidence_for_cause=0.9, achieves_goal=0.29) == (5, "objected")


def test_every_configuration_returns_a_known_action_on_random_answers():
    import random

    rng = random.Random(7)
    for _ in range(200):
        a = {k: {"noul": rng.random()} for k in BASE}
        for cfg in jg.e7_configs():
            for conv in (False, True):
                n, act = jg.e7_row(a, cfg, conv)
                assert 1 <= n <= 7 and act in ("none", "asked", "objected")
                assert jg.e7_action(a, cfg, conv) == act


def test_e5bs_table_runs_on_the_same_answers():
    # The baseline reads only questions the E7 battery asks.
    assert jg.e5b_action(answers()) in ("none", "asked", "objected")
    assert jg.e5b_action(answers(link_stated=0.9, achieves_goal=0.4)) == "objected"
