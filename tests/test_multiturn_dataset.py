from collections import Counter

import pytest

from eval import multiturn_dataset as mt
from eval import proposals_dataset as base


def test_scenario_counts():
    counts = Counter(c.scenario for c in mt.load())
    assert counts == {"late_sound": 6, "late_flawed": 9, "late_absent": 13, "late_answered": 4}


def test_ids_are_unique_and_point_at_real_proposals():
    convs = mt.load()
    assert len({c.id for c in convs}) == len(convs)
    known = {p.id for p in base.load()}
    assert all(c.proposal_id in known for c in convs)


def test_recorded_replies_are_slotted_between_the_user_turns():
    c = next(c for c in mt.load() if c.scenario == "late_flawed")
    msgs = c.messages(["built step one", "built step two"])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]
    assert [m["content"] for m in msgs if m["role"] == "user"] == c.user_turns
    assert msgs[1]["content"] == "built step one" and msgs[3]["content"] == "built step two"


def test_the_wrong_number_of_recorded_replies_is_refused():
    c = next(c for c in mt.load() if c.scenario == "late_answered")
    with pytest.raises(ValueError):
        c.messages(["a", "b"])


def test_the_turn_under_test_does_not_restate_the_situation_or_the_plan():
    """The point of the set: the last message alone must not carry the case."""
    for c in mt.load():
        if c.scenario == "late_answered":
            continue
        assert c.situation not in c.user_turns[-1] and c.plan not in c.user_turns[-1]
        assert c.situation in c.user_turns[0] and c.plan in c.user_turns[0]


def test_late_absent_never_states_the_withheld_cause():
    for c in mt.load():
        if c.scenario == "late_absent":
            assert all(c.hidden_cause not in turn for turn in c.user_turns)


def test_late_answered_gives_the_cause_only_in_the_last_turn():
    for c in mt.load():
        if c.scenario == "late_answered":
            assert c.hidden_cause in c.user_turns[-1]
            assert c.hidden_cause not in c.user_turns[0]


def test_the_three_requests_of_a_late_conversation_are_distinct():
    for c in mt.load():
        if c.scenario != "late_answered":
            step1, step2 = mt.STEPS[c.proposal_id]
            assert c.user_turns[0].endswith(step1) and c.user_turns[1] == step2
            assert c.user_turns[2] not in (step1, step2)


def test_the_same_plan_gets_the_same_steps_with_and_without_the_cause():
    by_proposal: dict[str, set[str]] = {}
    for c in mt.load():
        if c.scenario != "late_answered":
            by_proposal.setdefault(c.proposal_id, set()).add(c.user_turns[1])
    assert all(len(v) == 1 for v in by_proposal.values())


def test_history_comes_from_the_check_only_where_the_question_was_asked():
    for c in mt.load():
        assert c.history_source == ("ground" if c.scenario == "late_answered" else "direct")


def test_every_conversation_carries_the_review_status():
    assert mt.REVIEW == "owner-checked"
    assert all(c.review == mt.REVIEW for c in mt.load())


def test_render_lists_every_conversation():
    page = mt.render_markdown()
    assert all(f"### {c.id}" in page for c in mt.load())
