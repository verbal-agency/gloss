"""Shape checks for the engineering-proposals pilot set."""
from __future__ import annotations
from collections import Counter

from eval import proposals_dataset


def test_items_are_well_formed():
    items = proposals_dataset.load()
    assert len({p.id for p in items}) == len(items)
    assert Counter(p.kind for p in items) == {"mismatch": 15, "infeasible": 16, "sound": 15}
    for p in items:
        assert (p.flaw is None) == (p.kind == "sound")   # only controls lack a flaw
        assert p.source in ("project", "drafted")
        assert p.tier in ("stated", "inferred")
        assert not p.plan[0].isupper() and not p.plan.endswith(".")  # reads after "decided to"


def test_both_framings_carry_the_same_situation_and_plan():
    p = proposals_dataset.load()[0]
    framings = proposals_dataset.prompts(p)
    assert set(framings) == {"blind_review", "owned_build"}
    for text in framings.values():
        assert p.situation in text and p.plan in text
    assert p.ask in framings["owned_build"] and p.ask not in framings["blind_review"]
    assert p.flaw not in framings["owned_build"] and p.flaw not in framings["blind_review"]


def test_plan_length_does_not_give_the_label_away():
    """v1 was reviewed as answerable from style alone: sound plans were long and
    carried a check, flawed plans were terse. Keep both styles on both sides."""
    items = proposals_dataset.load()
    def words(p): return len(p.plan.split())
    flawed = [p for p in items if p.flaw]
    sound = [p for p in items if not p.flaw]
    assert sum(words(p) >= 20 for p in flawed) >= 8     # detailed, confident flawed plans
    assert sum(words(p) <= 16 for p in sound) >= 7      # short sound plans
    assert sum(p.tier == "inferred" for p in flawed) >= 6
    assert sum(p.tier == "inferred" for p in sound) >= 4
