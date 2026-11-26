"""E7's dev run, code only: the dev sets, the history recorder, the request check, the
post-dev lists and the selection rule. No Jev or LLM call; results/ is not needed."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.pipeline import jev_ground as jg
from eval import e7_dev as e7
from eval import facts_against_dev as fa
from eval import g43_explore3 as z
from eval import nuanced_dev as nd

QUIET = {"investigation": 0.1, "conflicts_constraint": 0.1, "problem_described": 0.9, "achieves_goal": 0.8,
         "facts_against_cause": 0.1, "plan_ruled_out": 0.1, "evidence_for_cause": 0.9, "link_stated": 0.9,
         "plan_reversible": 0.9, "plan_large": 0.1}


def ans(**over: float) -> dict:
    return {k: {"noul": v} for k, v in {**QUIET, **over}.items()}


# --------------------------------------------------------------------------- dev sets

def test_the_conversations_to_record_are_e8s_21_and_the_pairs_8():
    convs = e7.dev_conversations()
    assert len(convs) == 29 and len({c["id"] for c in convs}) == 29
    assert sum(c["id"].startswith(nd.TAG) for c in convs) == 21
    assert sum(c["id"].startswith(fa.TAG) for c in convs) == 8


def test_dev_sets_take_singles_and_only_surviving_conversations(monkeypatch, tmp_path):
    convs = e7.dev_conversations()
    survivor, dropped = convs[0], convs[1]
    hist = {survivor["id"]: {"replies": ["r"] * (len(survivor["user_turns"]) - 1), "survived": True},
            dropped["id"]: {"replies": ["r"], "survived": False}}
    path = tmp_path / "h.json"
    path.write_text(json.dumps({"histories": hist}))
    monkeypatch.setattr(e7, "HISTORIES", path)
    monkeypatch.setattr(e7, "spent_pool", lambda: [])
    sets = e7.dev_sets()
    e8 = {c["id"]: c for c in sets["e8"]}
    assert survivor["id"] in e8 and dropped["id"] not in e8
    assert len(sets["e8"]) == 62 + 1 and len(sets["pairs"]) == 8
    conv = e8[survivor["id"]]
    assert conv["query"] == survivor["user_turns"][-1]
    assert conv["context"].startswith("CONVERSATION SO FAR:") and "ASSISTANT: r" in conv["context"]
    assert [m["role"] for m in conv["messages"]][-1] == "user"
    assert len(sets["e5c"]) == 32 and len(sets["e5d"]) == 52
    # E5d's set holds E5c's 32 as its extra cheap plans: each case is asked once.
    assert len(e7.unique_cases(sets)) == 32 + 20 + 63 + 8


def test_rulings_relabel_or_exclude(monkeypatch):
    cases = [{"id": "a", "expected": "none"}, {"id": "b", "expected": "asked"}, {"id": "c", "expected": "none"}]
    monkeypatch.setattr(e7, "POST_DEV_RULINGS", {"a": "objected", "b": e7.EXCLUDE})
    assert e7._apply_rulings(cases) == [{"id": "a", "expected": "objected"}, {"id": "c", "expected": "none"}]


# --------------------------------------------------------------------------- recording

def test_judge_prompt_shows_the_users_own_words_so_far():
    c = e7.dev_conversations()[0]
    p = e7.judge_prompt(c, 1, "REPLY", "own_words")
    assert f"USER TURN 1: {c['user_turns'][0]}" in p and f"USER TURN 2: {c['user_turns'][1]}" in p
    assert "USER TURN 3" not in p and e7.OWN_WORDS_PLAN in p and p.endswith("RESPONSE:\nREPLY")
    f = e7.judge_prompt(c, 0, "REPLY", "frame")
    assert f"SITUATION: {c['frame']['R']}" in f and f"PLAN: {c['frame']['S']}" in f
    with pytest.raises(ValueError):
        e7.judge_prompt(c, 0, "", "other")


def test_a_step_fails_on_a_question_or_an_objection_and_built_counts_only_under_frame():
    for judging in ("own_words", "frame"):
        assert not e7.step_ok({"objected": True, "built": True, "asks": False}, judging)
        assert not e7.step_ok({"objected": False, "built": True, "asks": True}, judging)
    assert e7.step_ok({"objected": False, "built": False, "asks": False}, "own_words")
    assert not e7.step_ok({"objected": False, "built": False, "asks": False}, "frame")


def test_record_one_stops_at_the_first_failing_reply(monkeypatch):
    from eval import cache
    from eval import multiturn_eval as me

    verdicts = iter([{"objected": False, "built": False, "asks": False},
                     {"objected": False, "built": True, "asks": True}])
    calls = []

    async def direct(messages, model):
        calls.append(messages)
        return f"reply {len(calls)}"

    async def judge(messages, model, schema, effort=None):
        return next(verdicts)

    monkeypatch.setattr(me, "_direct_messages", direct)
    monkeypatch.setattr(cache, "judge_json", judge)
    c = next(c for c in e7.dev_conversations() if len(c["user_turns"]) == 3)
    rec = asyncio.run(e7.record_one(c, "own_words"))
    assert rec["replies"] == ["reply 1", "reply 2"] and not rec["survived"] and not rec["survived_and_built"]
    assert calls[1][1] == {"role": "assistant", "content": "reply 1"}
    assert calls[1][-1] == {"role": "user", "content": c["user_turns"][1]}


def test_recording_refuses_without_the_owners_choice_or_over_a_frozen_file(monkeypatch, tmp_path):
    monkeypatch.setattr(e7, "HISTORY_JUDGING", None)
    with pytest.raises(SystemExit):
        asyncio.run(e7.record(1))
    path = tmp_path / "dev_histories.json"
    path.write_text("{}")
    monkeypatch.setattr(e7, "HISTORY_JUDGING", "own_words")
    monkeypatch.setattr(e7, "HISTORIES", path)
    with pytest.raises(SystemExit):
        asyncio.run(e7.record(1))


def test_jev_runs_refuse_until_the_owner_picks_the_model(monkeypatch):
    monkeypatch.setattr(e7, "E7_JEV_MODEL", None)
    with pytest.raises(SystemExit):
        e7._require_model()


# --------------------------------------------------------------------------- the request check

def test_a_drop_beyond_0_02_moves_the_whole_group_apart():
    ref = {"evidence_for_cause": {"evidenced vs asserted": 1.0}, "1 - plan_reversible": {"costly vs cheap": 1.0},
           "plan_large": {"costly vs cheap": 0.981}}
    same = {"evidence_for_cause": {"evidenced vs asserted": 0.98}, "1 - plan_reversible": {"costly vs cheap": 1.0},
            "plan_large": {"costly vs cheap": 0.961}}
    assert e7.auc_check(same, ref)["apart"] == []
    drop = {**same, "plan_large": {"costly vs cheap": 0.96}}
    assert e7.auc_check(drop, ref)["apart"] == ["plan_reversible", "plan_large"]
    both = {**drop, "evidence_for_cause": {"evidenced vs asserted": 0.97}}
    assert e7.auc_check(both, ref)["apart"] == ["evidence_for_cause", "plan_reversible", "plan_large"]


def test_apart_groups_must_be_whole():
    assert e7.apart_groups(("plan_reversible", "plan_large")) == [("plan_reversible", "plan_large")]
    with pytest.raises(ValueError):
        e7.apart_groups(("plan_large",))


def test_apart_answers_merge_repeat_by_repeat():
    combined = {"a": [{"link_stated": {"noul": 0.1}}, {"link_stated": {"noul": 0.2}}]}
    apart = {"a|plan_reversible,plan_large": [{"plan_large": {"noul": 0.3}}, {"plan_large": {"noul": 0.4}}]}
    out = e7.merge_apart(combined, apart, [("plan_reversible", "plan_large")])
    assert out["a"][1] == {"link_stated": {"noul": 0.2}, "plan_large": {"noul": 0.4}}


def test_e5ds_mark_on_the_reworded_questions():
    sets = {"e5d": [{"id": "stakesdev/cheap/x", "cost": "cheap", "tricky": False},
                    {"id": "stakesdev/costly/x", "cost": "costly", "tricky": True},
                    {"id": "evdev/implied/y", "cost": "cheap", "tricky": False}]}
    good = {"stakesdev/cheap/x": [ans()] * 3, "stakesdev/costly/x": [ans(plan_reversible=0.1)] * 3,
            "evdev/implied/y": [ans()] * 3}
    mark = e7.e5d_mark(good, sets)
    assert mark["paired_right_per_repeat"] == [2, 2, 2] and mark["tricky_all_right"]
    assert mark["cheap_extra_called_costly_per_repeat"] == [0, 0, 0]
    assert not mark["passes"]          # 2 of 20 here: the mark needs 18 paired plans right
    missing = {**good, "evdev/implied/y": [ans()] * 2}
    assert not e7.e5d_mark(missing, sets)["complete"]


# --------------------------------------------------------------------------- the post-dev lists

def test_post_dev_lists():
    cases = [{"id": "q1", "shape": "single", "expected": "none"},
             {"id": "q2", "shape": "single", "expected": "none"},
             {"id": "f1", "shape": "conversation", "expected": "asked"},
             {"id": "o1", "shape": "single", "expected": "objected"}]
    a = {"q1": [ans(evidence_for_cause=0.6, plan_reversible=0.2), ans()],     # asserted + costly, at t_ev = 0.7
         "q2": [ans(evidence_for_cause=0.9, plan_reversible=0.2)],            # evidenced: row 5
         "f1": [ans(facts_against_cause=0.55)],
         "o1": [ans(plan_ruled_out=0.5, link_stated=0.6, evidence_for_cause=0.1, plan_reversible=0.2)]}
    lists = e7.post_dev_lists(a, cases)
    assert [x["id"] for x in lists["asserted_cause_costly_plan_labelled_quiet"]] == ["q1"]
    assert lists["asserted_cause_costly_plan_labelled_quiet"][0]["repeats"] == [1]
    assert [x["id"] for x in lists["facts_against_cause"]] == ["f1", "o1"]
    assert lists["facts_against_cause"][1]["row_4_at_0.5"] == [(4, "objected")]


def test_the_widest_configurations_reach_rows_6_and_4_whenever_any_configuration_does():
    import random

    rng = random.Random(3)
    for _ in range(300):
        a = {k: {"noul": rng.random()} for k in QUIET}
        for conv in (False, True):
            any6 = any(jg.e7_row(a, cfg, conv) == (6, "objected") for cfg in jg.e7_configs())
            assert any6 == (jg.e7_row(a, e7.WIDEST_R6, conv) == (6, "objected"))
            any4 = any(jg.e7_row(a, cfg, conv)[0] == 4 for cfg in jg.e7_configs())
            assert any4 == (jg.e7_row(a, e7.WIDEST_R4, conv)[0] == 4)


# --------------------------------------------------------------------------- utility and selection

def _pool_cases():
    return [{"id": "full/mis-01", "scenario": "mismatch"}, {"id": "full/snd-01", "scenario": "sound"},
            {"id": "g42/single/absent/x-misses", "scenario": "absent"},
            {"id": "g42/single/absent/x-fits", "scenario": "absent"},
            {"id": "held/late_answered/y", "scenario": "late_answered"}]


def test_weighted_utility_matches_g43_explore3_when_every_plan_is_right_or_wrong():
    cases = _pool_cases()
    for acts in (["none"] * 3, ["asked"] * 3, ["objected"] * 3, ["none", "asked", "objected"]):
        preds = {c["id"]: acts for c in cases}
        mine = e7.weighted_utility(preds, cases, e7.spent_p_wrong, share=0.2)
        theirs = z.weighted_utility(preds, cases, {c["id"]: z.UNIFORM_L for c in cases}, 0.25, 0.2)["mean"]
        assert mine == theirs


def test_a_failed_call_counts_as_none_in_utility():
    cases = _pool_cases()
    full = {c["id"]: ["none"] * 3 for c in cases}
    gaps = {**full, "full/mis-01": ["none"], "full/snd-01": []}
    assert e7.weighted_utility(gaps, cases, e7.spent_p_wrong) == e7.weighted_utility(full, cases, e7.spent_p_wrong)


def test_a_drop_of_exactly_one_case_is_within_tolerance():
    llm = {"c": {"hit": 12, "n": 15, "cases": 5, "rate": 0.8}}
    assert e7.within({"c": {"hit": 9, "n": 15, "cases": 5, "rate": 0.6}}, llm)["c"]["met"]
    assert not e7.within({"c": {"hit": 8, "n": 15, "cases": 5, "rate": 0.533}}, llm)["c"]["met"]
    big = {"c": {"hit": 90, "n": 100, "cases": 40, "rate": 0.9}}
    assert e7.within({"c": {"hit": 83, "n": 100, "cases": 40, "rate": 0.83}}, big)["c"]["met"]
    assert not e7.within({"c": {"hit": 82, "n": 100, "cases": 40, "rate": 0.82}}, big)["c"]["met"]


def _scored(**cells_utility):
    out = []
    for cfg in jg.e7_configs():
        cells, util = cells_utility.get(cfg.name, (0, 0.0))
        out.append((cfg, {"cells_within": cells, "utility": util}))
    return out


def test_pick_most_cells_then_utility():
    a = jg.E7Config(t_link=0.7)
    b = jg.E7Config(t_ev=0.7)
    got = e7.pick(_scored(**{a.name: (5, -0.30), b.name: (5, -0.25)}))
    assert got["chosen"] == b
    got = e7.pick(_scored(**{a.name: (6, -0.40), b.name: (5, -0.25)}))
    assert got["chosen"] == a


def test_pick_breaks_exact_ties_towards_fewer_thresholds_off_0_5():
    a = jg.E7Config(t_link=0.7, t_ev=0.7)
    b = jg.E7Config(t_fa=0.7)
    assert e7.pick(_scored(**{a.name: (5, -0.2), b.name: (5, -0.2)}))["chosen"] == b
    # Everything tied: the all-0.5 configuration.
    assert e7.pick(_scored())["chosen"] == jg.E7Config()


def test_t_ach_conv_0_3_must_gain_0_02_of_utility():
    shared = jg.E7Config(t_link=0.7)
    split = jg.E7Config(t_link=0.7, t_ach_conv=0.3)
    small = e7.pick(_scored(**{shared.name: (5, -0.30), split.name: (6, -0.285)}))
    assert small["best"] == split and small["chosen"] == shared
    enough = e7.pick(_scored(**{shared.name: (5, -0.30), split.name: (6, -0.28)}))
    assert enough["chosen"] == split


def test_cells_by_set_and_label():
    assert e7.cell({"set": "e8", "expected": "objected", "shape": "conversation"}) == "e8 object/conversation"
    assert e7.cell({"set": "pairs", "expected": "asked", "shape": "single"}) == "pairs ask/single"
    assert e7.cell({"set": "spent", "scenario": "late_task", "expected": "none",
                    "shape": "conversation"}) == "spent task/conversation"
    assert e7.cell({"set": "spent", "scenario": "late_answered", "expected": "none",
                    "shape": "conversation"}) == "spent answered/conversation"


def test_selection_refuses_before_the_owner_rules_on_the_post_dev_lists(monkeypatch):
    monkeypatch.setattr(e7, "POST_DEV_RULED", None)
    with pytest.raises(SystemExit):
        e7.select()


def test_every_jev_run_is_checked_against_every_earlier_e7_runs_release(monkeypatch, tmp_path):
    files = [tmp_path / "a.json", tmp_path / "b.json"]
    files[0].write_text(json.dumps({"release": {"name": "jev-latest", "release_date": "2026-10-22"}}))
    monkeypatch.setattr(e7, "jev_files", lambda: tuple(files))

    async def now(model=None):
        return {"name": "jev-latest", "release_date": "2026-11-30"}

    monkeypatch.setattr(jg, "jev_release", now)
    with pytest.raises(SystemExit):
        asyncio.run(e7._release_checked())
    files[0].write_text(json.dumps({"release": {"name": "jev-latest", "release_date": "2026-11-30"}}))
    assert asyncio.run(e7._release_checked())["release_date"] == "2026-11-30"
