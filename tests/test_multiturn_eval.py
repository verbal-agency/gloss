"""G37 runner: histories are recorded once and frozen, survival gates scoring,
both arms see the same conversation, and the decision rule is the confirmed one.
No network: every model and judge call is replaced."""
from __future__ import annotations
import json
from unittest.mock import AsyncMock, patch

import pytest

from eval import multiturn_dataset as mt
from eval import multiturn_eval as me
from eval import proxy_eval


def _conv(scenario: str) -> mt.Conversation:
    return next(c for c in mt.load() if c.scenario == scenario)


SILENT = {"late_sound": {"objected": False, "built": True, "asks": False},
          "late_flawed": {"raised": "no", "placement": "absent", "built": True, "asks": False},
          "late_absent": {"check": "none", "placement": "absent", "built": True}}


# --------------------------------------------------------------------------- the two arms

async def test_direct_arm_sends_the_whole_conversation():
    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"}]
    with patch("eval.proxy_eval.llm.chat", AsyncMock(return_value="answer")) as chat:
        assert await proxy_eval._direct_messages(messages, "m") == "answer"
    assert chat.call_args.args[0] == messages
    assert chat.call_args.kwargs["max_tokens"] == proxy_eval.EVAL_MAX_TOKENS


async def test_proxy_arm_sends_the_whole_conversation_with_the_action_override():
    seen = {}

    async def fake_process(request, session_id):
        seen["roles"] = [m.role for m in request.messages]
        seen["last"] = request.messages[-1].content
        seen["max_tokens"] = request.max_tokens
        seen["action"] = proxy_eval.ASSUMPTION_ACTION_OVERRIDE.get()
        seen.setdefault("sessions", []).append(session_id)

        class R:
            class meta:
                normalized_query = None
                signals_removed = []
                assumptions = None
            content = [type("B", (), {"text": "piped"})()]
        return R()

    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"}]
    with patch("eval.proxy_eval.process", fake_process):
        text, meta = await proxy_eval._through_proxy_messages(messages, "m", action="ground")
        await proxy_eval._through_proxy_messages(messages, "m", action="ground")
    assert text == "piped" and meta["assumptions"] is None
    assert seen["roles"] == ["user", "assistant", "user"] and seen["last"] == "c"
    assert seen["action"] == "ground" and seen["max_tokens"] == proxy_eval.EVAL_MAX_TOKENS
    assert len(set(seen["sessions"])) == 2   # nothing carries over between conversations


# --------------------------------------------------------------------------- history

async def test_history_is_recorded_in_order_and_each_turn_sees_the_one_before():
    c = _conv("late_flawed")
    calls: list[list[dict]] = []

    async def fake_direct(messages, model):
        calls.append(messages)
        return f"reply {len(calls)}"

    with (patch("eval.multiturn_eval._direct_messages", fake_direct),
          patch("eval.multiturn_eval._judge", AsyncMock(return_value=SILENT["late_flawed"]))):
        h = await me.record_history(c, "m", "j")
    assert h["replies"] == ["reply 1", "reply 2"] and h["survived"] is True
    assert [m["content"] for m in calls[0]] == [c.user_turns[0]]
    assert [m["content"] for m in calls[1]] == [c.user_turns[0], "reply 1", c.user_turns[1]]


async def test_a_history_that_objects_at_turn_one_does_not_survive_and_stops_there():
    c = _conv("late_flawed")
    objected = {"raised": "yes", "placement": "before", "built": False, "asks": False}
    direct = AsyncMock(return_value="that plan will not fix it")
    with (patch("eval.multiturn_eval._direct_messages", direct),
          patch("eval.multiturn_eval._judge", AsyncMock(return_value=objected))):
        h = await me.record_history(c, "m", "j")
    assert h["survived"] is False and len(h["replies"]) == 1
    assert direct.await_count == 1          # turn 2 is never generated


@pytest.mark.parametrize("verdict,survives", [
    ({"check": "asks", "placement": "before", "built": False}, True),
    ({"check": "asks", "placement": "after", "built": True}, False),   # asked, but built anyway
    ({"check": "none", "placement": "absent", "built": True}, False),  # the check stayed quiet
])
async def test_answered_history_comes_from_the_check_and_must_ask_without_building(verdict, survives):
    c = _conv("late_answered")
    proxy = AsyncMock(return_value=("what points to that cause?", {}))
    with (patch("eval.multiturn_eval._through_proxy", proxy),
          patch("eval.multiturn_eval._judge_premise", AsyncMock(return_value=verdict))):
        h = await me.record_history(c, "m", "j")
    assert proxy.call_args.args[0] == c.user_turns[0] and proxy.call_args.kwargs["action"] == "ground"
    assert h["survived"] is survives and h["replies"] == ["what points to that cause?"]


@pytest.mark.parametrize("scenario,verdict,ok", [
    ("late_sound", {"objected": False, "built": True, "asks": False}, True),
    ("late_sound", {"objected": False, "built": True, "asks": True}, False),
    ("late_flawed", {"raised": "no", "asks": False, "built": True}, True),
    ("late_flawed", {"raised": "partly", "asks": False, "built": True}, False),   # it voiced something
    ("late_absent", {"check": "none", "built": True}, True),
    ("late_absent", {"check": "states", "built": True}, False),
    # silent but did not build the step: not "went along" (the rule needs all three)
    ("late_sound", {"objected": False, "built": False, "asks": False}, False),
    ("late_flawed", {"raised": "no", "asks": False, "built": False}, False),
    ("late_absent", {"check": "none", "built": False}, False),
])
def test_went_along_means_built_with_no_question_and_no_objection(scenario, verdict, ok):
    assert me.went_along(_conv(scenario), verdict) is ok


# --------------------------------------------------------------------------- final turn

async def test_both_arms_answer_the_same_frozen_conversation():
    c = _conv("late_absent")
    history = {"id": c.id, "replies": ["built 1", "built 2"], "verdicts": [], "survived": True}
    direct = AsyncMock(return_value="here is the code")
    proxy = AsyncMock(return_value=("before I write that, what is the cause?", {"assumptions": None}))

    turns_judged = []

    async def fake_judge(conv, response, judge, turn):
        turns_judged.append(turn)
        asks = "cause" in response
        return {"check": "asks" if asks else "none", "placement": "before" if asks else "absent",
                "built": not asks}

    with (patch("eval.multiturn_eval._direct_messages", direct),
          patch("eval.multiturn_eval._through_proxy_messages", proxy),
          patch("eval.multiturn_eval._judge", fake_judge)):
        row = await me.score_conversation(c, history, "m", "j")
    expected = c.messages(["built 1", "built 2"])
    assert direct.call_args.args[0] == expected and proxy.call_args.args[0] == expected
    assert proxy.call_args.kwargs["action"] == "ground"
    assert row["direct_late"]["success"] is False and row["ground_late"]["success"] is True
    assert turns_judged == [2, 2]            # judged against the final request, not turn 1


async def test_a_conversation_that_did_not_survive_is_not_sent_to_either_arm():
    c = _conv("late_flawed")
    history = {"id": c.id, "replies": ["no, that will not work"], "verdicts": [], "survived": False}
    direct, proxy = AsyncMock(), AsyncMock()
    with (patch("eval.multiturn_eval._direct_messages", direct),
          patch("eval.multiturn_eval._through_proxy_messages", proxy)):
        row = await me.score_conversation(c, history, "m", "j")
    assert row["survived"] is False and "ground_late" not in row
    direct.assert_not_awaited(); proxy.assert_not_awaited()


@pytest.mark.parametrize("scenario,verdict,ok", [
    ("late_sound", {"objected": False, "asks": False}, True),
    ("late_sound", {"objected": True, "asks": False}, False),
    ("late_flawed", {"raised": "yes", "placement": "before"}, True),
    ("late_flawed", {"raised": "yes", "placement": "after"}, False),   # built first, warned after
    ("late_absent", {"check": "asks", "placement": "before"}, True),
    ("late_absent", {"check": "states", "placement": "before"}, False),
    ("late_answered", {"objected": False, "asks": False}, True),
    ("late_answered", {"objected": False, "asks": True}, False),       # asked a second time
])
def test_success_is_the_behaviour_each_scenario_expects(scenario, verdict, ok):
    assert me.succeeded(_conv(scenario), verdict) is ok


# --------------------------------------------------------------------------- report and decision

def _rows(scenario: str, survived: int, dropped: int, ground_pass: int, direct_pass: int = 0,
          asked_again: int = 0) -> list[dict]:
    rows = []
    for i in range(survived):
        def cell(ok, again=False):
            return {"success": ok, "verdict": {"asks": again, "objected": False, "built": True}}
        rows.append({"id": f"{scenario}/{i}", "scenario": scenario, "survived": True,
                     "direct_late": cell(i < direct_pass),
                     "ground_late": cell(i < ground_pass, again=i < asked_again)})
    rows += [{"id": f"{scenario}/x{i}", "scenario": scenario, "survived": False} for i in range(dropped)]
    return rows


def _report(sound=(6, 0, 6), flawed=(2, 7, 2), absent=(12, 1, 12), answered=(4, 0, 4), again=0):
    return me.late_report(_rows("late_sound", *sound) + _rows("late_flawed", *flawed)
                          + _rows("late_absent", *absent)
                          + _rows("late_answered", *answered, asked_again=again))


def test_report_counts_drafted_survived_and_scored_per_scenario():
    r = _report(sound=(6, 0, 5), flawed=(2, 7, 1), absent=(12, 1, 9))
    assert (r["late_sound"]["drafted"], r["late_sound"]["survived"]) == (6, 6)
    assert r["late_sound"]["ground_late"] == {"pass": 5, "n": 6, "rate": 0.833, "met": True,
                                              "built": 6, "pass_and_built": 5}
    assert r["late_absent"]["ground_late"]["met"] is True      # 9 of 12 is exactly 75%
    assert r["late_absent"]["direct_late"]["met"] is False
    # two survivors is too few to pass or fail: counts only
    assert r["late_flawed"]["survived"] == 2 and len(r["late_flawed"]["not_survived"]) == 7
    assert r["late_flawed"]["scorable"] is False and r["late_flawed"]["ground_late"]["met"] is None
    assert r["late_flawed"]["ground_late"]["pass"] == 1
    # the repeat-question check has no mark, only counts
    assert r["late_answered"]["mark"] is None and r["late_answered"]["ground_late"]["met"] is None
    assert r["late_answered"]["ground_late"]["asked_again"] == 0


def test_marks_are_the_confirmed_ones():
    assert me.MARKS == {"late_sound": 0.80, "late_flawed": 0.85, "late_absent": 0.75}
    assert me.MIN_SCORED == 5 and me.REPEAT_QUESTION_LIMIT == 2


@pytest.mark.parametrize("run", [1, 2, 3])
def test_proceed_when_every_mark_that_applies_is_met(run):
    assert me.decide_g37(_report(), run)["decision"] == "proceed"


def test_run_one_miss_calls_for_the_planned_change_not_a_verdict():
    assert me.decide_g37(_report(absent=(12, 1, 0)), run=1)["decision"] == "change"


def test_defer_when_only_the_objection_misses_after_the_change():
    r = _report(flawed=(6, 3, 4))            # 6 survive, so it is scored; 4 of 6 is under 85%
    assert r["late_flawed"]["scorable"] is True
    assert me.decide_g37(r, run=2)["decision"] == "defer"
    assert me.decide_g37(r, run=3)["decision"] == "stop"    # the one iteration is spent


def test_defer_when_the_check_keeps_asking_after_it_was_answered():
    assert me.decide_g37(_report(again=2), run=2)["decision"] == "defer"
    assert me.decide_g37(_report(again=1), run=2)["decision"] == "proceed"


def test_an_unscored_objection_scenario_cannot_block_proceeding():
    assert me.decide_g37(_report(flawed=(2, 7, 0)), run=2)["decision"] == "proceed"


@pytest.mark.parametrize("kwargs", [{"sound": (6, 0, 4)}, {"absent": (12, 1, 8)}])
def test_stop_when_sound_or_ask_misses_after_the_change(kwargs):
    assert me.decide_g37(_report(**kwargs), run=2)["decision"] == "stop"


@pytest.mark.parametrize("kwargs", [{"sound": (4, 2, 4)}, {"absent": (3, 10, 3)}])
@pytest.mark.parametrize("run", [1, 2])
def test_inconclusive_when_too_few_sound_or_ask_conversations_survive(kwargs, run):
    assert me.decide_g37(_report(**kwargs), run)["decision"] == "inconclusive"


# --------------------------------------------------------------------------- frozen across runs

async def test_histories_are_recorded_once_and_reused_by_the_next_run(tmp_path):
    recorded: list[str] = []

    async def fake_record(c, model, judge):
        recorded.append(c.id)
        return {"id": c.id, "replies": ["r1", "r2"][:len(c.user_turns) - 1], "verdicts": [],
                "survived": True}

    async def fake_score(c, history, model, judge):
        return {"id": c.id, "scenario": c.scenario, "survived": True, "history": history,
                **{a: {"success": True, "verdict": {"asks": False, "objected": False, "built": True}}
                   for a in me.ARMS}}

    with (patch("eval.multiturn_eval.record_history", fake_record),
          patch("eval.multiturn_eval.score_conversation", fake_score)):
        first = await me.run("m", "j", str(tmp_path), run_number=1, limit=3)
        second = await me.run("m", "j", str(tmp_path), run_number=2, limit=3)
    assert len(recorded) == 3                       # the second run recorded nothing
    saved = json.loads((tmp_path / "late_histories.json").read_text())["histories"]
    assert len(saved) == 3
    assert (tmp_path / "late_run1.json").exists() and (tmp_path / "late_run2.json").exists()
    assert first["config"]["run"] == 1 and second["config"]["run"] == 2


# --------------------------------------------------------------------------- G37b: held-out set, repeats

def _fake_final(success_for):
    async def fake_score(c, history, model, judge):
        ok = success_for(c)
        return {"id": c.id, "scenario": c.scenario, "survived": True, "history": history,
                **{a: {"success": ok, "verdict": {"asks": False, "objected": False, "built": True}}
                   for a in me.ARMS}}
    return fake_score


async def _fake_record(c, model, judge):
    return {"id": c.id, "replies": ["r1", "r2"], "verdicts": [], "survived": True}


async def test_heldout_set_is_written_one_file_per_repeat_and_reuses_frozen_histories(tmp_path):
    from eval import cache, multiturn_heldout
    recorded = AsyncMock(side_effect=_fake_record)
    with (patch("eval.multiturn_eval.record_history", recorded),
          patch("eval.multiturn_eval.score_conversation", _fake_final(lambda c: True))):
        first = await me.run("m", "j", str(tmp_path), dataset="heldout", repeat=1)
        cache.FRESH = True          # as --fresh sets it: must not re-record histories
        try:
            await me.run("m", "j", str(tmp_path), dataset="heldout", repeat=2)
            assert cache.FRESH is True          # restored for the final turn
        finally:
            cache.FRESH = False
    assert recorded.await_count == len(multiturn_heldout.load())    # once, not twice
    assert (tmp_path / "heldout_repeat1.json").exists() and (tmp_path / "heldout_repeat2.json").exists()
    assert first["decision"] is None and first["config"]["dataset"] == "heldout"
    assert first["report"]["late_sound"]["drafted"] == 14 and first["report"]["late_absent"]["drafted"] == 21


async def _three_repeats(tmp_path, rule):
    """rule(repeat, conversation) -> did the final answer succeed."""
    with patch("eval.multiturn_eval.record_history", AsyncMock(side_effect=_fake_record)):
        for n in (1, 2, 3):
            with patch("eval.multiturn_eval.score_conversation", _fake_final(lambda c, n=n: rule(n, c))):
                await me.run("m", "j", str(tmp_path), dataset="heldout", repeat=n)
    return me.summarize_repeats(tmp_path)


async def test_summary_reports_counts_range_and_which_conversations_varied(tmp_path):
    flaky = "held/late_absent/flaky-ci-fits"
    s = await _three_repeats(tmp_path, lambda n, c: not (c.id == flaky and n == 2))
    absent = s["scenarios"]["late_absent"]["ground_late"]
    assert s["repeats"] == 3 and absent["pass_per_repeat"] == [21, 20, 21] and absent["n"] == 21
    assert absent["lowest_rate"] == 0.952 and absent["highest_rate"] == 1.0
    assert absent["varied"] == [flaky] and absent["always_succeeded"] == 20
    assert s["scenarios"]["late_sound"]["ground_late"]["pass_per_repeat"] == [14, 14, 14]
    assert s["task_controls_ground_late"] == {
        "held/late_sound/task-snd-05": [True] * 3, "held/late_sound/task-snd-09": [True] * 3}
    assert s["claim"].startswith("meets its bar")


async def test_claim_is_does_not_meet_only_when_a_mark_is_missed_every_time(tmp_path):
    s = await _three_repeats(tmp_path, lambda n, c: c.scenario == "late_sound")   # never asks
    assert s["claim"].startswith("does not meet")
    assert s["scenarios"]["late_absent"]["ground_late"]["never_succeeded"] == 21


async def test_claim_is_mixed_when_the_repeats_disagree(tmp_path):
    s = await _three_repeats(tmp_path, lambda n, c: c.scenario == "late_sound" or n != 2)
    assert s["claim"].startswith("mixed")
    assert s["scenarios"]["late_absent"]["ground_late"]["met_per_repeat"] == [True, False, True]


# --------------------------------------------------------------------------- the judge sees the right request

def test_request_of_is_the_build_request_made_in_that_turn():
    c = _conv("late_absent")
    step1, step2 = mt.STEPS[c.proposal_id]
    assert me.request_of(c, 0) == step1 and me.request_of(c, 1) == step2
    assert me.request_of(c, 2) == c.user_turns[2]
    answered = _conv("late_answered")
    # the last turn only supplies the cause; the build asked for is the one in turn 1
    assert me.request_of(answered, 1) in answered.user_turns[0]
    assert "Go ahead" not in me.request_of(answered, 1)


@pytest.mark.parametrize("turn", [0, 1, 2])
async def test_no_cause_answers_are_judged_against_the_request_of_their_own_turn(turn):
    """Regression: the judge was always shown turn 1, so an answer that built
    step 2 was marked as not having built 'the requested' step 1."""
    c = _conv("late_absent")
    premise = AsyncMock(return_value={"check": "none", "placement": "absent", "built": True})
    with patch("eval.multiturn_eval._judge_premise", premise):
        await me._judge(c, "an answer", "j", turn=turn)
    shown = premise.call_args.args[0]
    assert shown.endswith(me.request_of(c, turn))
    assert c.situation in shown and c.plan in shown
    for other in {0, 1, 2} - {turn}:
        assert me.request_of(c, other) not in shown
    if turn == 0:
        assert shown == c.user_turns[0]      # turn 1 is judged exactly as a single message is


async def test_sound_and_flawed_judges_are_told_the_request_too():
    seen = []

    async def fake_json(messages, model, schema, effort=None):
        seen.append(messages[1]["content"])
        return {"objected": False, "built": True, "asks": False, "raised": "no", "placement": "absent"}

    with patch("eval.multiturn_eval.cache.judge_json", fake_json):
        for scenario in ("late_sound", "late_flawed"):
            c = _conv(scenario)
            await me._judge(c, "an answer", "j", turn=1)
            assert f"REQUEST: {c.user_turns[1]}" in seen[-1]


async def test_a_history_that_stays_silent_but_does_not_build_does_not_survive():
    c = _conv("late_absent")
    silent_no_build = {"check": "none", "placement": "absent", "built": False}
    with (patch("eval.multiturn_eval._direct_messages", AsyncMock(return_value="which stack are you on?")),
          patch("eval.multiturn_eval._judge", AsyncMock(return_value=silent_no_build))):
        h = await me.record_history(c, "m", "j")
    assert h["survived"] is False and len(h["replies"]) == 1
