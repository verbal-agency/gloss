"""E7a: the facts-against dev pairs. No network.

The overlap tests compare this set with the other sets as code only. A failure
names the case in this set, never the text it was too close to. Run with
`--tb=no -q`.
"""
from collections import Counter
from pathlib import Path

from eval import facts_against_dev as fa
from eval import g43_heldout, g44_heldout
from eval import nuanced_dev as nd
from tests.test_g43_heldout import _too_close
from tests.test_g44_heldout import _all_criteria_examples
from tests.test_nuanced_dev import _earlier_situations, _earlier_texts

FIELDS = {"id", "family", "version", "shape", "frame", "level", "cost", "reversible", "expected", "rationale",
          "confidence"}
SHARED = ("family", "shape", "level", "cost", "reversible")


def _pairs():
    by = {}
    for c in fa.cases():
        by.setdefault(c["family"], {})[c["version"]] = c
    return by


def test_counts_and_pairing():
    cs = fa.cases()
    assert len(fa.SITUATIONS) == 8 and len(cs) == 16
    pairs = _pairs()
    assert set(pairs) == set(fa.SITUATIONS)
    assert all(set(p) == {"asked", "objected"} for p in pairs.values())
    shapes = Counter(s["shape"] for s in fa.SITUATIONS.values())
    assert shapes == {"single": 4, "conversation": 4}


def test_within_a_pair_only_the_fact_differs():
    for key, p in _pairs().items():
        s, a, o = fa.SITUATIONS[key], p["asked"], p["objected"]
        against, rules_out = s["against"], s["rules_out"]
        assert against.strip() and rules_out.strip() and against != rules_out, key
        assert all(a[f] == o[f] for f in SHARED), key
        assert {k: v for k, v in a["frame"].items() if k != "defeater"} == \
               {k: v for k, v in o["frame"].items() if k != "defeater"}, key
        ta, to = fa.texts(a), fa.texts(o)
        assert len(ta) == len(to), key
        assert ta[:-1] == to[:-1], key                       # everything before the last message is identical
        assert ta[-1].count(against) == 1 and to[-1].count(rules_out) == 1, key
        assert ta[-1].replace(against, rules_out) == to[-1], key
        assert all(against not in t and rules_out not in t for t in ta[:-1]), key


def test_shapes_have_the_right_turns():
    for c in fa.cases():
        s = fa.SITUATIONS[c["family"]]
        if c["shape"] == "single":
            for part in ("problem", "cause", "plan", "request"):
                assert s[part] in c["query"], c["id"]
        else:
            t = c["user_turns"]
            assert len(t) == 3, c["id"]
            assert s["problem"] in t[0] and s["cause"] in t[0], c["id"]
            assert s["plan"] in t[1] and s["step"] in t[1], c["id"]
            assert s[fa.FACT[c["version"]]] in t[2] and s["request"] in t[2], c["id"]


def test_every_case_has_the_required_fields():
    for c in fa.cases():
        text_field = "query" if c["shape"] == "single" else "user_turns"
        assert set(c) == FIELDS | {text_field}, c["id"]
        assert set(c["frame"]) == {"R", "D", "S", "defeater"}, c["id"]
        assert all(isinstance(v, str) and v.strip() for v in c["frame"].values()), c["id"]
        assert c["rationale"].strip(), c["id"]
        assert all(isinstance(t, str) and t.strip() for t in fa.texts(c)), c["id"]


def test_values_are_valid():
    for c in fa.cases():
        assert c["family"] in fa.SITUATIONS, c["id"]
        assert c["version"] in fa.VERSIONS and c["expected"] == c["version"], c["id"]
        assert c["shape"] in fa.SHAPES, c["id"]
        assert c["id"] == f"fadev/{c['shape']}/{c['family']}/{c['version']}", c["id"]
        assert c["frame"]["defeater"] == {"asked": "undercutting", "objected": "rebutting"}[c["version"]], c["id"]
        assert c["level"] in fa.LEVELS, c["id"]
        assert c["cost"] in fa.COSTS, c["id"]
        assert c["reversible"] in (True, False), c["id"]
        assert c["confidence"] in ("high", "low"), c["id"]
    assert fa.REVIEW == "owner-checked"


def test_ids_are_unique():
    cs = fa.cases()
    assert len({c["id"] for c in cs}) == len(cs)


def test_the_set_is_varied():
    ss = fa.SITUATIONS.values()
    assert {s["level"] for s in ss} == set(fa.LEVELS)
    assert {s["cost"] for s in ss} == set(fa.COSTS)
    assert {s["reversible"] for s in ss} == {True, False}


def test_the_template_the_earlier_sets_hold_constant_is_not_reused():
    for c in fa.cases():
        assert all("I've researched this and decided to" not in t for t in fa.texts(c)), c["id"]


def test_situations_are_new():
    h = g44_heldout
    earlier = (_earlier_situations() | {c["family"] for c in nd.cases()}
               | set(h.SITUATIONS) | set(h.REQUIREMENTS) | set(h.PROBLEMS))
    assert sorted(set(fa.SITUATIONS) & earlier) == []


def _close_ids(examples):
    """Ids of cases in this set too close to any of `examples`. Ids only: the
    matched text is never reported."""
    examples = list(examples)
    return [c["id"] for c in fa.cases() if any(_too_close(t, examples) is not None for t in fa.texts(c))]


def _heldout_turns(module):
    singles = [c["query"] for c in module.single_cases()] if hasattr(module, "single_cases") else []
    return singles + [t for c in module.load() for t in c.user_turns]


def test_no_case_is_close_to_a_criteria_example():
    examples = list(_all_criteria_examples())
    assert examples
    assert _close_ids(examples) == []


def test_no_case_is_close_to_a_g43_or_g44_case():
    for module in (g43_heldout, g44_heldout):
        turns = _heldout_turns(module)
        assert turns
        assert _close_ids(turns) == [], module.__name__


def test_no_case_is_close_to_any_earlier_dev_set():
    earlier = _earlier_texts()
    assert len(earlier) > 200
    assert _close_ids(earlier) == []


def test_no_case_is_close_to_an_e8_case():
    e8 = [t for c in nd.cases() for t in nd.texts(c)]
    assert e8
    assert _close_ids(e8) == []


def test_the_overlap_check_would_catch_a_reused_case():
    reused = fa.texts(fa.cases()[0])[0]
    assert _too_close(reused, [reused]) is not None


def test_review_page_lists_every_case_grouped_by_situation_with_low_confidence_first():
    page = fa.render_markdown()
    assert all(page.count(f"#### {c['id']}\n") == 1 for c in fa.cases())
    order = [page.index(f"## {k}\n") for k in fa._situation_order()]
    assert order == sorted(order)
    low = {c["family"] for c in fa.cases() if c["confidence"] == "low"}
    starts = {k: page.index(f"## {k}\n") for k in fa.SITUATIONS}
    if low and low != set(fa.SITUATIONS):
        assert max(starts[k] for k in low) < min(starts[k] for k in fa.SITUATIONS if k not in low)
    for k, p in _pairs().items():
        ends = sorted(v for v in starts.values() if v > starts[k])
        end = ends[0] if ends else len(page)
        at = {v: page.index(f"#### {c['id']}\n") for v, c in p.items()}
        assert all(starts[k] < x < end for x in at.values()), k
        if {c["confidence"] for c in p.values()} == {"high", "low"}:
            first = min(at, key=at.get)
            assert p[first]["confidence"] == "low", k


def test_checked_in_review_page_matches_the_set():
    assert Path("docs/facts_against_dev_review.md").read_text() == fa.render_markdown(), \
        "regenerate with: python -m eval.facts_against_dev > docs/facts_against_dev_review.md"
