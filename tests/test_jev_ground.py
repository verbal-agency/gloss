"""The Jev-backed grounding classifier (G40). No network: Jev's answers are faked."""
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.pipeline import assumptions, jev_ground
from eval import ground_classifier_eval as g


def _answers(request="fix", link="absent", is_fix=0.9, cause=0.1, contra=0.1, beyond=0.1):
    return {
        "request": {"type": "choice", "choice": request, "confidence": 0.9, "probabilities": {}},
        "link": {"type": "choice", "choice": link, "confidence": 0.9, "probabilities": {}},
        "is_fix": {"type": "noul", "noul": is_fix},
        "cause_stated": {"type": "noul", "noul": cause},
        "contradicted": {"type": "noul", "noul": contra},
        "evidence_beyond_plan": {"type": "noul", "noul": beyond},
    }


def test_battery_is_accepted_by_the_sdk_question_types():
    from typesafe_sdk import Choice, Noul
    for conversation in (False, True):
        for name, q in jev_ground.battery(conversation).items():
            (Choice if q["type"] == "choice" else Noul)(**q)


def test_conversation_note_only_when_there_is_a_conversation():
    single = jev_ground.battery(False)["link"]["instructions"]
    multi = jev_ground.battery(True)["link"]["instructions"]
    assert "LATEST REQUEST" not in single and "LATEST REQUEST" in multi


def test_choice_action_matches_the_llm_classifier_rule():
    assert jev_ground.choice_action(_answers("fix", "absent")) == "asked"
    assert jev_ground.choice_action(_answers("task", "absent")) == "none"
    assert jev_ground.choice_action(_answers("task", "contradicted")) == "objected"
    assert jev_ground.choice_action(_answers("fix", "stated")) == "none"


@pytest.mark.parametrize("kw,expected", [
    ({}, "asked"),                                   # a fix, no cause stated
    ({"cause": 0.8}, "none"),                        # cause stated
    ({"is_fix": 0.2}, "none"),                       # not a fix: nothing to ask about
    ({"contra": 0.8}, "objected"),                   # objection outranks the question
])
def test_route_default_rule(kw, expected):
    assert jev_ground.route(_answers(**kw)) == expected


def test_route_can_use_the_non_standard_evidence_question():
    a = _answers(cause=0.9, beyond=0.1)              # plan implies the cause, no evidence
    assert jev_ground.route(a) == "none"
    assert jev_ground.route(a, jev_ground.Rule(cause_noul="evidence_beyond_plan")) == "asked"


def test_to_result_gives_the_middleware_the_same_actions():
    r = jev_ground.to_result(_answers(), "jev_nouls")
    assert (r.request, r.link, r.action) == ("fix", "absent", "asked")
    r = jev_ground.to_result(_answers(contra=0.9), "jev_nouls")
    assert r.action == "objected"
    r = jev_ground.to_result(_answers("task", "stated"), "jev_choice")
    assert r.action == "none"


async def test_run_ground_uses_jev_when_the_backend_says_so():
    fake = AsyncMock(return_value=_answers())
    with patch.object(settings, "ground_backend", "jev_nouls"), \
         patch.object(jev_ground, "ask_jev", fake):
        r = await assumptions.run_ground("msg", context=None)
    assert r.action == "asked"
    fake.assert_awaited_once_with("msg", conversation=False)


async def test_run_ground_passes_through_when_jev_fails():
    with patch.object(settings, "ground_backend", "jev_choice"), \
         patch.object(jev_ground, "ask_jev", AsyncMock(side_effect=RuntimeError("401"))):
        assert await assumptions.run_ground("msg") is None


async def test_llm_backend_is_still_the_default():
    assert settings.ground_backend == "llm"


# --------------------------------------------------------------------------- benchmark

def test_benchmark_split_and_expected_actions():
    cs = g.cases()
    assert {c["split"] for c in cs} == {"dev", "test"}
    assert all(c["group"] == "multiturn_heldout" for c in cs if c["split"] == "test")
    assert all(c["expected"] in g.ACTIONS for c in cs)
    assert len({c["id"] for c in cs}) == len(cs)
    late = [c for c in cs if c["group"].startswith("multiturn")]
    assert all(c["context"] and "LATEST REQUEST" in c["context"] for c in late)


def test_score_counts_every_repeat_and_balances_actions():
    cs = [{"id": "a", "expected": "asked", "group": "x", "scenario": "s"},
          {"id": "b", "expected": "none", "group": "x", "scenario": "t"}]
    s = g.score({"a": ["asked", "none"], "b": ["none", "none"]}, cs)
    assert s["per_action"]["asked"] == {"hit": 1, "n": 2, "rate": 0.5}
    assert s["balanced"] == 0.75


def test_decide_allows_one_conversation_of_slack():
    def t(none, asked):
        return {"per_action": {"none": {"rate": none}, "asked": {"rate": asked}}}
    assert g.decide(t(0.95, 0.80), t(0.93, 0.74))["matches_current"] is True
    assert g.decide(t(0.95, 0.80), t(0.95, 0.70))["matches_current"] is False


def test_every_jev_variant_gives_a_known_action():
    acts = g.jev_actions(_answers())
    assert "jev_choice" in acts and "jev_both_ask" in acts and len(acts) == len(g.rules()) + 3
    assert set(acts.values()) <= set(g.ACTIONS)
