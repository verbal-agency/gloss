"""E7b: the label-only check of the older dev cases. No network.

The prompts must show the labeller nothing but the guide and the user's words,
the guide must be E8b's with exactly the owner's 2026-11-25 clarifications, and
the stored labels must come from these prompts.
"""
import re
from pathlib import Path

from eval import nuanced_blind as nb
from eval import older_blind as ob


def test_the_guide_is_e8b_s_with_the_2026_11_25_clarifications():
    for old, new in ob._CHANGES:
        assert nb.GUIDE.count(old) == 1 and ob.GUIDE.count(new) == 1, old
    undone = ob.GUIDE
    for old, new in ob._CHANGES:
        undone = undone.replace(new, old)
    assert undone == nb.GUIDE


def test_neutral_ids_are_unique_and_cover_every_case():
    ids = ob.neutral_ids()
    assert set(ids) == {c["id"] for c in ob.cases()}
    assert len(set(ids.values())) == len(ids) == 280
    assert all(re.fullmatch(r"o\d{3}", v) for v in ids.values())


def test_each_pass_shows_every_case_once():
    want = sorted(ob.neutral_ids().values())
    for p in ob.PASSES:
        seen = [n for t in ob.prompts(p) for n in re.findall(r"^### (o\d{3})", t, re.M)]
        assert sorted(seen) == want, p


def test_prompts_show_no_case_id_or_scenario_name():
    cases = ob.cases()
    scenarios = {c["scenario"] for c in cases if "_" in c["scenario"]}
    for p in ob.PASSES:
        for text in ob.prompts(p):
            assert not [c["id"] for c in cases if c["id"] in text], p
            assert not [s for s in scenarios if re.search(rf"\b{re.escape(s)}\b", text)], p


def test_labels_cover_every_case_with_valid_values():
    labels = ob.load_labels()
    ids = {c["id"] for c in ob.cases()}
    assert set(labels["stored_at_run"]) == ids
    for p in ob.PASSES:
        assert set(labels["passes"][p]) == ids, p
        for i, row in labels["passes"][p].items():
            for k, allowed in nb.VALUES.items():
                assert row[k] in allowed, (p, i, k)


def test_labels_were_made_from_this_guide_and_these_prompts():
    labels, now = ob.load_labels(), ob.fingerprints()
    assert labels["guide_sha256"] == now["guide_sha256"], "the guide changed after the labelling run"
    assert labels["prompts_sha256"] == now["prompts_sha256"], "the prompts changed after the labelling run"


def test_relabels_are_stable_disagreements_the_owner_settled():
    labels = ob.load_labels()
    stable = {d["case"]["id"] for d in ob.disagreements(labels) if d["stable"]}
    assert len(ob.RELABELS) == 5
    for i, new in ob.RELABELS.items():
        assert i in stable, i
        assert labels["stored_at_run"][i] == "asked", i
        assert new == labels["passes"]["A"][i]["expected"] == labels["passes"]["B"][i]["expected"] == "none", i


def test_checked_in_review_page_matches_the_labels():
    assert Path("docs/older_blind_review.md").read_text() == ob.render_markdown(), \
        "regenerate with: python -m eval.older_blind > docs/older_blind_review.md"
