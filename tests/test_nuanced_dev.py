"""E8: the nuanced dev set. No network.

The overlap tests compare this set with the G43 held-out cases and the Jev
criteria examples as code only. A failure names the case in this set, never the
text it was too close to, so the held-out set stays unread.
"""
from collections import Counter
from pathlib import Path

from eval import evidence_dev, g41_heldout, g42_heldout, g43_heldout, multiturn_heldout, proposals_dataset
from eval import nuanced_dev as nd
from eval import stakes_dev
from tests.test_g43_heldout import _criteria_examples, _too_close

FIELDS = {"id", "category", "family", "shape", "frame", "level", "cost", "reversible", "expected", "rationale",
          "confidence"}


def test_every_category_has_enough_cases():
    singles = Counter(c["category"] for c in nd.single_cases())
    for category in nd.SINGLE_CATEGORIES:
        assert singles[category] >= 4, category
    convs = nd.conversations()
    assert len(nd.single_cases()) >= 60 and len(convs) >= 20
    assert sum(c["category"] == "spread_across_turns" for c in convs) >= 5
    assert not singles["spread_across_turns"], "spread across turns is for conversations only"
    assert set(c["category"] for c in nd.cases()) == set(nd.CATEGORIES)


def test_levels_and_costs_are_balanced():
    cs = nd.cases()
    levels, costs = Counter(c["level"] for c in cs), Counter(c["cost"] for c in cs)
    assert all(levels[k] >= 12 for k in ("implied", "asserted", "evidenced")), levels
    assert all(costs[k] >= 10 for k in nd.COSTS), costs


def test_every_case_has_the_required_fields():
    for c in nd.cases():
        text_field = "query" if c["shape"] == "single" else "user_turns"
        assert set(c) == FIELDS | {text_field}, c["id"]
        assert set(c["frame"]) == {"R", "D", "S", "defeater"}, c["id"]
        assert all(isinstance(v, str) and v.strip() for v in c["frame"].values()), c["id"]
        assert c["rationale"].strip(), c["id"]
        if c["shape"] == "single":
            assert isinstance(c["query"], str) and c["query"].strip(), c["id"]
        else:
            turns = c["user_turns"]
            assert isinstance(turns, list) and len(turns) >= 2 and all(t.strip() for t in turns), c["id"]


def test_values_are_valid():
    for c in nd.cases():
        assert c["category"] in nd.CATEGORIES, c["id"]
        assert c["shape"] in ("single", "conversation"), c["id"]
        assert c["frame"]["defeater"] in nd.DEFEATERS, c["id"]
        assert c["level"] in nd.LEVELS, c["id"]
        assert c["cost"] in nd.COSTS, c["id"]
        assert c["reversible"] in (True, False), c["id"]
        assert c["expected"] in nd.EXPECTED, c["id"]
        assert c["confidence"] in ("high", "low"), c["id"]
        if c["category"] == "mid_sized":
            assert c["cost"] == "mid", c["id"]
        if c["category"] == "costly_reversible":
            assert c["cost"] == "costly" and c["reversible"], c["id"]
        if c["category"] == "cheap_irreversible":
            assert c["cost"] == "cheap" and not c["reversible"], c["id"]


def test_labels_follow_the_parts_of_the_ladder_that_are_not_open():
    for c in nd.cases():
        if c["expected"] == nd.OWNER:
            continue
        if c["expected"] == "objected":
            assert c["frame"]["defeater"] in ("rebutting", "undermining"), c["id"]
        if c["expected"] == "asked":
            # an implied cause, or an asserted one the user's own facts contradict (owner, 2026-11-22)
            assert c["frame"]["defeater"] == "undercutting" and c["level"] in ("implied", "asserted"), c["id"]
        if c["expected"] == "none":
            assert c["frame"]["defeater"] == "none", c["id"]
        if c["level"] == "asserted" and c["frame"]["defeater"] in ("none", "undermining"):
            # E6 rule (b): an unsupported cause is objected to when the plan is costly or hard to reverse
            costly = c["cost"] == "costly" or not c["reversible"]
            assert c["expected"] == ("objected" if costly else "none"), c["id"]


def test_owner_labels_state_both_readings_and_are_marked_low():
    owner = [c for c in nd.cases() if c["expected"] == nd.OWNER]
    if nd.REVIEW == "owner-checked":
        assert not owner, "an owner-checked set has no open labels"
        assert not [c["id"] for c in nd.cases() if "Reading one" in c["rationale"]]
    for c in owner:
        assert "Reading one" in c["rationale"] and "Reading two" in c["rationale"], c["id"]
        assert c["confidence"] == "low", c["id"]


def test_ids_and_families_are_unique():
    cs = nd.cases()
    assert len({c["id"] for c in cs}) == len(cs)
    assert len({c["family"] for c in cs}) == len(cs), "one situation per case"


def test_the_template_the_earlier_sets_hold_constant_is_not_reused():
    for c in nd.cases():
        assert all("I've researched this and decided to" not in t for t in nd.texts(c)), c["id"]


def _earlier_situations():
    h = g43_heldout
    return (set(g41_heldout.SITUATIONS) | set(g42_heldout.SITUATIONS) | set(multiturn_heldout.NEW)
            | set(proposals_dataset._SITUATIONS) | set(evidence_dev.SITUATIONS) | set(stakes_dev.PAIRS)
            | set(h.SITUATIONS) | set(h.REQUIREMENTS) | set(h.DEBATABLE) | set(h.WEAK) | set(h.INVESTIGATIONS)
            | set(h.TASKS))


def test_situations_are_new():
    assert not {c["family"] for c in nd.cases()} & _earlier_situations()


def _earlier_texts():
    """Every user message in the earlier sets, G43 included."""
    out = [c["query"] for c in g43_heldout.single_cases()]
    out += [t for c in g43_heldout.load() for t in c.user_turns]
    out += [c["query"] for c in stakes_dev.cases()]          # includes the evidence_dev cases
    for module in (g41_heldout, g42_heldout, multiturn_heldout):
        out += [t for c in module.load() for t in c.user_turns]
    out += [c["query"] for module in (g41_heldout, g42_heldout) for c in module.single_cases()]
    for p in proposals_dataset.load():
        out.append(f"{p.situation} I've researched this and decided to {p.plan}. {p.ask}")
    return out


def _close_ids(examples):
    """Ids of cases in this set too close to any of `examples`. Ids only: the
    matched text is never reported."""
    return [c["id"] for c in nd.cases() if any(_too_close(t, examples) is not None for t in nd.texts(c))]


def test_no_case_is_close_to_a_criteria_example():
    assert _close_ids(_criteria_examples()) == []


def test_no_case_is_close_to_a_g43_case():
    g43 = [c["query"] for c in g43_heldout.single_cases()] + [t for c in g43_heldout.load() for t in c.user_turns]
    assert g43
    assert _close_ids(g43) == []


def test_no_case_is_close_to_any_earlier_set():
    earlier = _earlier_texts()
    assert len(earlier) > 200
    assert _close_ids(earlier) == []


def test_the_overlap_check_would_catch_a_reused_dev_case():
    reused = evidence_dev.cases()[0]["query"]
    assert _too_close(reused, _earlier_texts()) is not None


def test_review_page_puts_open_cases_first_and_lists_every_case():
    page = nd.render_markdown()
    assert all(f"#### {c['id']}" in page for c in nd.cases())
    first, second, third = (page.index(h) for h in ("## 1. Owner labels", "## 2. Low confidence", "## 3. The rest"))
    assert first < second < third
    for c in nd.cases():
        at = page.index(f"#### {c['id']}")
        if c["expected"] == nd.OWNER:
            assert first < at < second, c["id"]
        elif c["confidence"] == "low":
            assert second < at < third, c["id"]
        else:
            assert at > third, c["id"]


def test_checked_in_review_page_matches_the_set():
    assert Path("docs/nuanced_dev_review.md").read_text() == nd.render_markdown(), \
        "regenerate with: python -m eval.nuanced_dev > docs/nuanced_dev_review.md"
