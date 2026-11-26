"""E7, before the held-out run: every G43 and G44 case's utility assignment, as code only
(docs/e7_heldout_run_goal.md, "Utility"). No history, no Jev or LLM call. Failures name
case ids, never case texts."""
from __future__ import annotations

from collections import Counter

import pytest

from eval import e7_dev
from eval import g43_eval as ge

FRAMES = ge.e7_frames()
BY_ID = {f["id"]: f for f in FRAMES}
BUTTON_COLOUR = "g43/single/debatable/button-colour"


def _kind(f: dict) -> str:
    form = f["id"].rsplit("-", 1)[-1] if f["scenario"] in ("absent", "late_absent") else ""
    return f"{f['set']} {f['shape']} {f['scenario']}{' ' + form if form else ''} {f['expected']}"


# What each kind of held-out case's plan is, by the spec's rules. G43's debatable
# cases carry the owner's labels (2026-11-20; button-colour relabelled 2026-11-22).
EXPECTED_P = {
    "g43 single sound none": 0.0,
    "g43 single contradicted objected": 1.0,
    "g43 single absent fits asked": 0.0,
    "g43 single absent misses asked": 1.0,
    "g43 single requirement_met none": 0.0,
    "g43 single requirement_broken objected": 1.0,
    "g43 single debatable objected": 1.0,
    "g43 single debatable none": 0.0,
    "g43 single debatable asked": 0.0,          # button-colour: see test_button_colour_awaits_a_ruling
    "g43 single weak objected": 1.0,
    "g43 single investigation none": 0.0,
    "g43 single task none": 0.0,
    "g43 conversation late_sound none": 0.0,
    "g43 conversation late_task none": 0.0,
    "g43 conversation late_absent fits asked": 0.0,
    "g43 conversation late_absent misses asked": 1.0,
    "g43 conversation late_answered none": 0.0,
    "g43 conversation late_flawed objected": 1.0,
    "g44 conversation late_fact_for none": 0.0,
    "g44 conversation late_fact_against asked": 0.5,     # owner, 2026-11-25
    "g44 conversation late_switch_fits none": 0.0,
    "g44 conversation late_switch_misses objected": 1.0,
    "g44 conversation late_req_met none": 0.0,
    "g44 conversation late_req_broken objected": 1.0,
    "g44 conversation late_problem_stated none": 0.0,
    "g44 conversation late_problem_absent asked": 0.0,   # the same plan as its stated twin
}


def test_every_held_out_case_has_a_known_kind():
    unknown = sorted({f["id"] for f in FRAMES if _kind(f) not in EXPECTED_P})
    assert not unknown, unknown


def test_every_held_out_case_gets_its_kinds_chance_of_a_wrong_plan():
    bad = sorted(f["id"] for f in FRAMES if ge.e7_p_wrong(f) != EXPECTED_P[_kind(f)])
    assert not bad, bad


def test_the_sets_are_the_sizes_the_spec_gives():
    singles = [f for f in FRAMES if f["shape"] == "single"]
    assert Counter(f["expected"] for f in singles) == {"objected": 19, "asked": 17, "none": 26}
    g44 = [f for f in FRAMES if f["set"] == "g44"]
    assert Counter(f["expected"] for f in g44) == {"objected": 14, "asked": 18, "none": 32}
    # G43's conversations as recorded: 70 entries, one of which (deb-button-colour) is no longer built.
    assert sum(f["set"] == "g43" and f["shape"] == "conversation" for f in FRAMES) == 69


def test_counts_of_wrong_plans_by_set():
    def total(cond):
        return sum(ge.e7_p_wrong(f) for f in FRAMES if cond(f))

    assert total(lambda f: f["shape"] == "single") == 19 + 8        # every objection, and 8 misses withheld
    assert total(lambda f: f["set"] == "g44") == 14 + 8 * 0.5


def test_button_colour_awaits_a_ruling():
    # The spec's two rules make its plan right: it is neither objected nor withheld-cause.
    # Like G44's late facts against the cause, it is labelled `asked` for a fact against
    # its cause. Until the owner rules, it keeps the spec's literal assignment.
    assert BY_ID[BUTTON_COLOUR]["expected"] == "asked"
    assert ge.e7_p_wrong(BY_ID[BUTTON_COLOUR]) == ge.E7_P_WRONG_RULINGS.get(BUTTON_COLOUR, 0.0)


def test_asking_scores_best_on_a_late_fact_against_the_cause():
    case = next(f for f in FRAMES if f["scenario"] == "late_fact_against")
    p = ge.e7_p_wrong(case)
    u = {a: p * e7_dev.utility_of(a, True, False) + (1 - p) * e7_dev.utility_of(a, False, False)
         for a in ("none", "asked", "objected")}
    assert u["asked"] > u["objected"] > u["none"]
    assert u == pytest.approx({"none": -1.5, "asked": -0.55, "objected": -0.65})


def test_answered_conversations_charge_a_repeat_question():
    assert e7_dev.utility_of("asked", False, True) == pytest.approx(-0.5)
    assert e7_dev.utility_of("objected", False, True) == pytest.approx(-0.5)
    assert e7_dev.utility_of("none", False, True) == 0.0


def test_cells_pool_g43_and_g44_and_keep_g43s_conversation_objections_apart():
    cells = Counter(ge.e7_cell(f) for f in FRAMES)
    assert cells[ge.E7_REPORTED_ONLY] == 19                     # G43's late_flawed: none survived
    assert cells["object/conversation"] == 14                   # G44 only
    assert cells["task/single"] == 6 and cells["answered/conversation"] == 8
    assert set(cells) == {"quiet/single", "task/single", "ask/single", "object/single", "quiet/conversation",
                          "task/conversation", "ask/conversation", "answered/conversation",
                          "object/conversation", ge.E7_REPORTED_ONLY}


def test_the_decision_rule():
    llm = {"ask/single": {"rate": 0.9, "cases": 17}, "object/conversation": {"rate": 0.8, "cases": 14},
           ge.E7_REPORTED_ONLY: {"rate": 1.0, "cases": 0}}
    near = {"ask/single": {"rate": 0.84, "cases": 17}, "object/conversation": {"rate": 0.73, "cases": 14},
            ge.E7_REPORTED_ONLY: {"rate": 0.0, "cases": 0}}
    ok = ge.e7_decide(llm, near, -0.30, -0.32)
    assert ok["replaces_llm"] and ge.E7_REPORTED_ONLY not in ok["cells"]
    assert not ge.e7_decide(llm, near, -0.30, -0.321)["replaces_llm"]           # utility 0.021 worse
    far = {**near, "object/conversation": {"rate": 0.72, "cases": 14}}         # 0.08 below; one case is 0.071
    assert not ge.e7_decide(llm, far, -0.30, -0.30)["replaces_llm"]
    small = {"object/conversation": {"rate": 0.8, "cases": 5}}
    assert ge.e7_decide(small, {"object/conversation": {"rate": 0.6, "cases": 5}}, 0, 0)["replaces_llm"]


def test_the_held_out_run_refuses_before_a_configuration_is_committed():
    import asyncio

    assert ge.E7_CONFIG is None
    with pytest.raises(SystemExit):
        asyncio.run(ge.e7_run_arm("jev", 1))
