"""E5c: the paired dev cases and the evidence questions. No network."""
from collections import Counter

from app.pipeline import jev_ground
from eval import evidence_dev as ev
from eval import g41_heldout, g42_heldout, g43_heldout, multiturn_heldout, proposals_dataset


def test_each_situation_is_written_four_ways_with_one_plan():
    cs = ev.cases()
    assert len(cs) == 32 and Counter(c["variant"] for c in cs) == {v: 8 for v in ev.VARIANTS}
    for key, s in ev.SITUATIONS.items():
        mine = [c for c in cs if c["family"] == key]
        assert all(s["plan"] in c["query"] for c in mine)
        assert s["evidenced"] not in next(c for c in mine if c["variant"] == "asserted")["query"]


def test_dev_situations_are_unused_elsewhere():
    used = (set(g41_heldout.SITUATIONS) | set(g42_heldout.SITUATIONS) | set(multiturn_heldout.NEW)
            | set(proposals_dataset._SITUATIONS) | set(g43_heldout.SITUATIONS) | set(g43_heldout.REQUIREMENTS)
            | set(g43_heldout.DEBATABLE) | set(g43_heldout.WEAK) | set(g43_heldout.INVESTIGATIONS)
            | set(g43_heldout.TASKS))
    assert not set(ev.SITUATIONS) & used


def test_evidence_question_has_paired_examples_and_is_accepted():
    from typesafe_sdk import Noul
    _, yes, no = jev_ground._E5C_NOULS["evidence_for_cause"]
    assert len(yes["examples"]) >= 2 and len(no["examples"]) >= 3
    for conv in (False, True):
        for q in jev_ground.e5c_battery(conv).values():
            Noul(**q)


def test_stakes_pairs_and_questions():
    from typesafe_sdk import Choice, Noul
    from eval import stakes_dev as sd
    cs = sd.cases()
    paired = [c for c in cs if c["id"].startswith(sd.TAG)]
    assert len(paired) == 20 and sum(c["tricky"] for c in paired) == 4
    for q in jev_ground.e5d_battery(False).values():
        (Choice if q["type"] == "choice" else Noul)(**q)
    a = {"plan_reversible": {"noul": 0.15}, "plan_large": {"noul": 0.33}}
    assert jev_ground.plan_costly(a)                       # hard to reverse is enough
    assert not jev_ground.plan_costly({"plan_reversible": {"noul": 0.9}, "plan_large": {"noul": 0.1}})
