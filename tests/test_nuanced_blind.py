"""E8b: the blind second labelling of the E8 set. No network.

The prompts must show the labeller nothing but the guide and the user's words,
and the stored labels must come from exactly this guide and these prompts.
"""
import re
from pathlib import Path

from eval import nuanced_blind as nb
from eval import nuanced_dev as nd


def test_neutral_ids_are_unique_and_cover_every_case():
    ids = nb.neutral_ids()
    assert set(ids) == {c["id"] for c in nd.cases()}
    assert len(set(ids.values())) == len(ids)
    assert all(re.fullmatch(r"k\d\d", v) for v in ids.values())


def test_each_pass_shows_every_case_once_in_its_own_order():
    want = sorted(nb.neutral_ids().values())
    for p in nb.PASSES:
        seen = [n for t in nb.prompts(p) for n in re.findall(r"^### (k\d\d)", t, re.M)]
        assert sorted(seen) == want, p
    assert [c["id"] for c in nb.order("A")] != [c["id"] for c in nb.order("B")]


def test_prompts_show_no_label_rationale_name_or_category():
    cases = nd.cases()
    for p in nb.PASSES:
        for text in nb.prompts(p):
            for c in cases:
                own = " ".join(nd.texts(c))
                for needle in (c["id"], c["family"], c["rationale"], c["frame"]["R"], c["frame"]["D"],
                               c["frame"]["S"]):
                    # a plan the user states word for word is the user's text, not a label
                    assert needle in own or needle not in text, (p, c["id"])
            for key, (title, what) in nd.CATEGORIES.items():
                assert key not in text and title not in text and what not in text, (p, key)


def test_the_guide_names_no_case():
    for c in nd.cases():
        assert c["family"] not in nb.GUIDE and c["id"] not in nb.GUIDE
    assert "k00" in nb.GUIDE and not re.search(r"k(?!00)\d\d", nb.GUIDE), "the format example uses no real id"


def test_labels_cover_every_case_with_valid_values():
    labels = nb.load_labels()
    ids = {c["id"] for c in nd.cases()}
    for p in nb.PASSES:
        got = labels["passes"][p]
        assert set(got) == ids, p
        for i, row in got.items():
            for k, allowed in nb.VALUES.items():
                assert row[k] in allowed, (p, i, k)
            assert row["rationale"].strip(), (p, i)


def test_labels_were_made_from_this_guide_and_these_prompts():
    labels = nb.load_labels()
    now = nb.fingerprints()
    assert labels["guide_sha256"] == now["guide_sha256"], "the guide changed after the labelling run"
    assert labels["prompts_sha256"] == now["prompts_sha256"], \
        "the prompts changed after the labelling run (a case text, the order or the guide)"


def test_kappa():
    assert nb.kappa([("a", "a"), ("b", "b")]) == 1.0
    assert nb.kappa([("a", "b"), ("b", "a")]) == -1.0
    assert abs(nb.kappa([("a", "a"), ("a", "b"), ("b", "b"), ("b", "b")]) - 0.5) < 1e-9


def test_checked_in_review_page_matches_the_labels():
    assert Path("docs/nuanced_blind_review.md").read_text() == nb.render_markdown(), \
        "regenerate with: python -m eval.nuanced_blind > docs/nuanced_blind_review.md"
