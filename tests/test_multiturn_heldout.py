"""G37a held-out conversations: disjoint from the first set, and the cause is
withheld where it should be."""
from collections import Counter

from eval import multiturn_dataset as mt
from eval import multiturn_heldout as held


def test_counts_and_scenarios():
    assert Counter(c.scenario for c in held.load()) == {"late_sound": 14, "late_absent": 21}


def test_ids_are_unique():
    convs = held.load()
    assert len({c.id for c in convs}) == len(convs)


def test_no_proposal_is_shared_with_the_first_multi_turn_set():
    assert not {c.proposal_id for c in held.load()} & {c.proposal_id for c in mt.load()}


def test_the_withheld_cause_never_appears_in_a_late_absent_conversation():
    for c in held.load():
        if c.scenario == "late_absent":
            assert all(c.hidden_cause not in turn for turn in c.user_turns)


def test_sound_conversations_state_their_cause_in_turn_one():
    for family, item in held.NEW.items():
        c = next(c for c in held.load() if c.id == f"held/late_sound/{family}")
        assert item["cause"] in c.user_turns[0]


def test_the_request_under_test_does_not_restate_the_situation_or_plan():
    for c in held.load():
        assert c.situation not in c.user_turns[-1] and c.plan not in c.user_turns[-1]
        assert len(c.user_turns) == 3 and len(set(c.user_turns)) == 3


def test_each_new_situation_has_a_fitting_and_a_non_fitting_plan_with_different_steps():
    for item in held.NEW.values():
        assert item["fits"][0] != item["misses"][0]
        assert not set(item["fits"][1:]) & set(item["misses"][1:])
