"""G41: the held-out set, JSON state, the new rules, and the runner's guards. No network."""
from collections import Counter

import pytest

from app.pipeline import jev_ground
from app.pipeline.jev_ground import G41Rule
from eval import g41_eval as ge
from eval import g41_heldout as h


# --------------------------------------------------------------------------- the set

def test_set_has_the_counts_the_spec_names():
    assert Counter(c["scenario"] for c in h.single_cases()) == {
        "sound": 8, "contradicted": 8, "absent": 16, "task": 6}
    convs = h.load()
    assert len(convs) == 38
    assert sum(c.family.startswith("task-") for c in convs) == 6
    assert Counter(c.scenario for c in convs) == {"late_sound": 14, "late_absent": 16, "late_answered": 8}
    assert all(c.history_source == "ground" for c in convs if c.scenario == "late_answered")


def test_most_tasks_avoid_the_problem_question_s_own_examples():
    words = ("migrat", "requir", "upgrad", "feature", "compliance", "adding")
    plain = [k for k, (situation, *_r) in h.TASKS.items()
             if not any(w in situation.lower() for w in words)]
    assert len(plain) >= 4


def test_every_case_has_a_family():
    assert all(c["family"] for c in h.single_cases())
    assert len({c["family"] for c in h.single_cases()}) == 14


def test_withheld_cause_never_appears_where_it_is_withheld():
    for c in h.single_cases():
        if c["scenario"] == "absent":
            assert c["hidden_cause"] not in c["query"]
    for c in h.load():
        if c.scenario == "late_absent":
            assert all(c.hidden_cause not in t for t in c.user_turns)


def test_the_turn_under_test_does_not_restate_the_case():
    for c in h.load():
        assert c.plan not in c.user_turns[-1] and c.situation not in c.user_turns[-1]


def test_no_overlap_with_earlier_held_out_sets():
    from eval import multiturn_heldout as old
    assert not set(h.SITUATIONS) & set(old.NEW)
    assert len({c["id"] for c in h.single_cases()}) == len(h.single_cases())


def test_review_page_lists_every_case():
    page = h.render_markdown()
    assert all(c["id"] in page for c in h.single_cases())
    assert all(f"#### {c.id}" in page for c in h.load())


# --------------------------------------------------------------------------- JSON state and battery

def test_json_state_separates_user_and_assistant_turns():
    msgs = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"}]
    assert jev_ground.json_state(msgs) == {
        "earlier_user_turns": ["u1"], "assistant_replies": ["a1"], "latest_user_request": "u2"}


def test_json_state_for_one_message_has_the_same_shape():
    s = jev_ground.json_state([{"role": "user", "content": "only"}])
    assert s == {"earlier_user_turns": [], "assistant_replies": [], "latest_user_request": "only"}


def test_json_state_cuts_long_assistant_replies():
    long = "x" * 5000
    s = jev_ground.json_state([{"role": "user", "content": "u"}, {"role": "assistant", "content": long},
                               {"role": "user", "content": "v"}])
    assert len(s["assistant_replies"][0]) < 2000 and "[...]" in s["assistant_replies"][0]


def test_g41_battery_is_accepted_by_the_sdk_and_names_the_fields():
    from typesafe_sdk import Choice, Noul
    for form in ("text", "json"):
        for conv in (False, True):
            for q in jev_ground.g41_battery(form, conv).values():
                (Choice if q["type"] == "choice" else Noul)(**q)
    assert "latest_user_request" in jev_ground.g41_battery("json", False)["link"]["instructions"]
    assert set(jev_ground.g41_battery("json", True)) == {"request", "link", *jev_ground.G41_NOULS}


# --------------------------------------------------------------------------- rules

def _a(problem=0.9, is_fix=0.8, cause=0.1, contra=0.1, absent=0.6, request="fix", link="absent"):
    return {"request": {"choice": request, "probabilities": {}},
            "link": {"choice": link, "probabilities": {"absent": absent, "stated": 1 - absent,
                                                       "contradicted": 0.0}},
            "is_fix": {"noul": is_fix}, "problem_described": {"noul": problem},
            "cause_stated": {"noul": cause}, "contradicted": {"noul": contra}}


def test_problem_gate_keeps_a_plain_task_quiet():
    task = _a(problem=0.1, is_fix=0.7, cause=0.2)          # G40's failure: is_fix ~0.7 on tasks
    assert jev_ground.g41_action(task, G41Rule(gate="is_fix")) == "asked"
    assert jev_ground.g41_action(task, G41Rule(gate="problem_described")) == "none"


def test_link_rule_reads_the_probability_not_the_top_label():
    a = _a(absent=0.35, link="stated")
    assert jev_ground.g41_action(a, G41Rule(family="choice")) == "none"
    assert jev_ground.g41_action(a, G41Rule(family="link", gate=None, cause_t=0.3)) == "asked"


def test_objection_outranks_asking():
    assert jev_ground.g41_action(_a(contra=0.9), G41Rule()) == "objected"


def test_every_rule_has_a_unique_name():
    names = [r.name for r in ge.rules()]
    assert len(names) == len(set(names))


# --------------------------------------------------------------------------- scoring and guards

def test_groups_are_scored_per_shape():
    cases = [{"id": "a", "scenario": "task", "expected": "none", "shape": "single"},
             {"id": "b", "scenario": "late_task", "expected": "none", "shape": "conversation"},
             {"id": "c", "scenario": "late_answered", "expected": "none", "shape": "conversation"}]
    rates = ge.group_rates({"a": ["none"], "b": ["asked"], "c": ["none"]}, cases, repeats=1)
    assert rates["task/single"]["rate"] == 1.0 and rates["task/conversation"]["rate"] == 0.0
    assert rates["answered/conversation"]["rate"] == 1.0


def test_a_failed_classification_is_a_miss():
    cases = [{"id": "a", "scenario": "absent", "expected": "asked", "shape": "single"}]
    r = ge.group_rates({"a": ["asked"]}, cases, repeats=3)["absent/single"]
    assert (r["hit"], r["n"], r["missing"]) == (1, 3, 2)


def _cell(rate, cases=20):
    return {"rate": rate, "cases": cases}


def test_decide_needs_every_gated_cell_and_ignores_contradiction():
    llm = {"sound/single": _cell(1.0), "sound/conversation": _cell(1.0),
           "absent/single": _cell(0.8), "contradicted/single": _cell(0.5)}
    ok = {"sound/single": _cell(0.95), "sound/conversation": _cell(0.94),
          "absent/single": _cell(0.85), "contradicted/single": _cell(0.0)}
    assert ge.decide(llm, ok)["matches_current"] is True
    # good on singles is no cover for a conversation failure
    assert ge.decide(llm, {**ok, "sound/conversation": _cell(0.8)})["matches_current"] is False


def test_small_cells_get_one_case_of_slack():
    llm = {"answered/conversation": _cell(1.0, cases=8)}
    assert ge.decide(llm, {"answered/conversation": _cell(0.875, cases=8)})["matches_current"] is True
    assert ge.decide(llm, {"answered/conversation": _cell(0.75, cases=8)})["matches_current"] is False


def test_pick_prefers_shared_thresholds_unless_per_shape_clearly_wins():
    dev = [{"id": "s", "shape": "single", "expected": "asked", "group": "x", "scenario": "s"},
           {"id": "c", "shape": "conversation", "expected": "none", "group": "x", "scenario": "c"}]
    answers = {"jev_json": {"s": [_a()], "c": [_a(cause=0.9, absent=0.1, link="stated")]}}
    chosen = ge.pick(answers, dev)
    assert chosen["conversation"] is None and chosen["dev_balanced"] == 1.0


async def test_runs_refuse_before_the_owner_review(monkeypatch):
    monkeypatch.setattr(h, "REVIEW", "drafted")
    with pytest.raises(SystemExit):
        await ge.run_arm("llm", 1, 1)
    with pytest.raises(SystemExit):
        await ge.record(1)
