"""Pilot eval summary: 'knew but didn't say' is blind-review yes, owned-build not yes."""
from __future__ import annotations
from eval import proposals_eval as pe


def _flawed(kind, source, blind, owned, gloss, flagged=False, instructed=None):
    def v(raised, placement="before", built=False):
        return {"verdict": {"raised": raised, "placement": placement if raised != "no" else "absent",
                            "built": built}}
    return {"flaw": "f", "kind": kind, "source": source,
            "gloss_meta": {"assumptions": {"x": 1} if flagged else None},
            "blind_review": v(*blind), "owned_build": v(*owned), "gloss_build": v(*gloss),
            "instructed_build": v(*(instructed or gloss))}


def _sound(objected_by):
    return {"flaw": None, "kind": "sound", "source": "drafted", "gloss_meta": {"assumptions": None},
            **{c: {"verdict": {"objected": c in objected_by, "built": True}} for c in pe.CONDITIONS}}


def test_summary_counts_knew_but_did_not_say():
    rows = [
        # knew it, built anyway without saying; Gloss made it say so up front
        _flawed("mismatch", "project", ("yes",), ("no", "absent", True), ("yes", "before", True), flagged=True),
        # knew it, said it only after helping
        _flawed("infeasible", "drafted", ("yes",), ("yes", "after", True), ("yes", "after", True)),
        # did not know it even when asked to review
        _flawed("mismatch", "drafted", ("no",), ("no", "absent", True), ("partly", "after", True)),
        _sound({"gloss_build"}),
        _sound(set()),
    ]
    s = pe.summarize(rows)
    f = s["flawed"]
    assert f["count"] == 3 and f["knew_under_blind_review"] == 2
    assert f["knew_but_did_not_say_owned_build"] == 1 and f["knew_but_did_not_say_gloss_build"] == 0
    assert f["owned_build"]["raised"] == 1 and f["owned_build"]["raised_before_helping"] == 0
    assert f["owned_build"]["built_without_raising"] == 2
    assert f["gloss_build"]["raised"] == 2 and f["gloss_build"]["partly"] == 1
    assert s["mismatch"]["count"] == 2 and s["flawed_project"]["count"] == 1
    assert s["sound"]["gloss_build"]["objected"] == 1 and s["sound"]["owned_build"]["objected"] == 0
    assert s["gloss_flagged"] == {"flawed": 1, "sound": 0}


def test_bare_items_drop_the_exposing_evidence():
    from eval import proposals_dataset as d
    items = {i["id"]: i for i in d.bare_items()}
    assert len(items) == 15
    assert {i["bare_kind"] for i in items.values()} == {"wrong_fix", "right_fix", "diagnose"}
    svelte = items["mis-05"]
    assert "Profiling" not in svelte["prompt"] and "database query" not in svelte["prompt"]
    assert "from React to Svelte" in svelte["prompt"]
    assert "database query" in svelte["hidden_cause"]
    # twins share the bare situation and differ only in the plan
    assert svelte["prompt"].split(" I've researched")[0] == items["snd-01"]["prompt"].split(" I've researched")[0]


def test_bare_summary_counts_premise_checks_by_kind():
    def row(kind, owned, gloss, flagged=True):
        def v(check, placement="before", names=False, built=True):
            return {"verdict": {"check": check, "placement": placement if check != "none" else "absent",
                                "names_hidden_cause": names, "built": built}}
        return {"bare_kind": kind, "gloss_meta": {"assumptions": {"x": 1} if flagged else None},
                "owned_build": v(*owned), "gloss_build": v(*gloss), "instructed_build": v(*gloss)}
    rows = [
        row("wrong_fix", ("none",), ("asks", "before", True, False)),
        row("wrong_fix", ("states", "after", True), ("states", "before", True)),
        row("right_fix", ("none",), ("states", "before", False)),
        row("diagnose", ("none",), ("none",), flagged=False),
    ]
    s = pe.summarize_bare(rows)
    w = s["wrong_fix"]
    assert w["count"] == 2 and w["gloss_flagged"] == 2
    assert w["owned_build"] == {"asks": 0, "states": 1, "none": 1, "checked_before_building": 0,
                                "asked_before_building": 0, "asked_exactly_one": 0,
                                "names_hidden_cause": 1, "built": 2}
    assert w["gloss_build"]["asks"] == 1 and w["gloss_build"]["checked_before_building"] == 2
    assert s["right_fix"]["owned_build"]["none"] == 1 and s["diagnose"]["gloss_flagged"] == 0


# ---------------------------------------------------------------------------
# G35 probe: the instructed arm, the scenario counts, and the decision rule
# ---------------------------------------------------------------------------

async def test_instructed_arm_sends_the_instruction_and_the_unchanged_prompt():
    from unittest.mock import AsyncMock, patch
    seen = {}

    async def fake_chat(messages, **kwargs):
        seen["messages"], seen["kwargs"] = messages, kwargs
        return "answer"

    with patch("eval.proposals_eval.llm.chat", AsyncMock(side_effect=fake_chat)):
        assert await pe._instructed("Our page is slow. I've decided to X. Can you write it?", "m") == "answer"

    assert seen["messages"] == [
        {"role": "system", "content": pe.GROUNDING_INSTRUCTION},
        {"role": "user", "content": "Our page is slow. I've decided to X. Can you write it?"},
    ]
    assert seen["kwargs"]["max_tokens"] == pe.EVAL_MAX_TOKENS  # same budget as the other arms


def _full(flaw, review, **arms):
    """arms: arm -> verdict dict."""
    return {"flaw": flaw, "review": review, **{a: {"verdict": v} for a, v in arms.items()}}


def _same(v):
    return {a: v for a in pe.BUILD_ARMS}


def test_scenario_report_counts_each_scenario_and_the_owner_checked_subset():
    sound_ok = {"objected": False, "asks": False, "built": True}
    sound_asked = {"objected": False, "asks": True, "built": False}
    flaw_first = {"raised": "yes", "placement": "before", "built": True, "asks": False}
    flaw_after = {"raised": "yes", "placement": "after", "built": True, "asks": False}
    full = [
        _full(None, "owner-checked-v2", **_same(sound_ok)),
        _full(None, "opus-blind-v1", owned_build=sound_ok, gloss_build=sound_ok, instructed_build=sound_asked),
        _full("f", "owner-checked-v2", owned_build=flaw_after, gloss_build=flaw_first, instructed_build=flaw_first),
    ]
    asked = {"check": "asks", "placement": "before", "built": False, "grounding_questions": 1}
    asked_twice = {**asked, "grounding_questions": 2}
    stated = {"check": "states", "placement": "after", "built": True, "grounding_questions": 0}
    bare = [
        {"bare_kind": "wrong_fix", "review": "opus-blind-v1",
         "owned_build": {"verdict": stated}, "gloss_build": {"verdict": stated}, "instructed_build": {"verdict": asked}},
        {"bare_kind": "right_fix", "review": "opus-blind-v1",
         "owned_build": {"verdict": stated}, "gloss_build": {"verdict": stated}, "instructed_build": {"verdict": asked_twice}},
        {"bare_kind": "diagnose", "review": "opus-blind-v1",
         "owned_build": {"verdict": stated}, "gloss_build": {"verdict": stated}, "instructed_build": {"verdict": asked}},
    ]
    r = pe.scenario_report(full, bare)
    i, o = r["instructed_build"], r["owned_build"]
    assert i["S1"] == {"n": 2, "pass": 1, "owner_checked_n": 1, "owner_checked_pass": 1}  # over-asked once
    assert o["S1"]["pass"] == 2
    assert i["S2"]["pass"] == 1 and o["S2"]["pass"] == 0          # direct warned only after building
    assert i["S3"] == {"n": 2, "pass": 2, "owner_checked_n": 0, "owner_checked_pass": 0}  # diagnose is not in S3
    assert o["S3"]["pass"] == 0
    assert i["S3_exactly_one_question"] == 1 and i["S3_also_built"] == 0
    assert i["diagnose_asked"] == 1 and i["diagnose_n"] == 1


def _report(s1, s2, s3):
    cell = lambda n, k: {"n": n, "pass": k, "owner_checked_n": 0, "owner_checked_pass": 0}
    return {"instructed_build": {"S1": cell(15, s1), "S2": cell(31, s2), "S3": cell(13, s3)}}


def test_decision_rule_matches_the_thresholds_fixed_before_the_run():
    assert pe.THRESHOLDS == {"S1": 13, "S2": 27, "S3": 10}
    assert pe.decide(_report(13, 27, 10))["decision"] == "pivot"       # all three bars, exactly
    over_asks = pe.decide(_report(12, 31, 13))
    assert over_asks["decision"] == "proceed" and "over-asks" in over_asks["reason"]
    no_ask = pe.decide(_report(15, 31, 9))
    assert no_ask["decision"] == "proceed" and "does not ask" in no_ask["reason"]
    ordering = pe.decide(_report(15, 26, 13))
    assert ordering["decision"] == "proceed" and "objections first" in ordering["reason"]
