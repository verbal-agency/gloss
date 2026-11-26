"""E7d: the blind check of the facts-against pairs. No network.

The prompts must show the labeller nothing but the guide and the user's words, the guide must be E7b's with exactly
the owner's 2026-11-25 rulings, and the two versions of a situation must never share a batch.
"""
import re
from pathlib import Path

from eval import facts_against_dev as fa
from eval import nuanced_blind as nb
from eval import older_blind as ob
from eval import pairs_blind as pb


def test_the_guide_is_e7b_s_with_the_2026_11_25_rulings():
    for old, new in pb._CHANGES:
        assert ob.GUIDE.count(old) == 1 and pb.GUIDE.count(new) == 1, old
    undone = pb.GUIDE
    for old, new in pb._CHANGES:
        undone = undone.replace(new, old)
    assert undone == ob.GUIDE


def test_neutral_ids_are_unique_and_cover_every_case():
    ids = pb.neutral_ids()
    assert set(ids) == {c["id"] for c in fa.cases()}
    assert len(set(ids.values())) == len(ids) == 16
    assert all(re.fullmatch(r"t\d{2}", v) for v in ids.values())


def test_each_pass_shows_every_case_once():
    want = sorted(pb.neutral_ids().values())
    for p in pb.PASSES:
        seen = [n for t in pb.prompts(p) for n in re.findall(r"^### (t\d{2})", t, re.M)]
        assert sorted(seen) == want, p


def test_twins_never_share_a_batch_and_batches_are_balanced():
    for p in pb.PASSES:
        for chunk in pb.batches(p):
            assert sorted(c["family"] for c in chunk) == sorted(fa.SITUATIONS), p
            for shape in fa.SHAPES:
                got = sorted(c["expected"] for c in chunk if c["shape"] == shape)
                assert got == ["asked", "asked", "objected", "objected"], (p, shape)


def test_prompts_show_nothing_but_the_guide_and_the_user_s_words():
    cases = fa.cases()
    hidden = [c["id"] for c in cases] + list(fa.SITUATIONS) + [c["rationale"] for c in cases]
    hidden += [c["frame"][k] for c in cases for k in ("R", "D", "S")]
    for p in pb.PASSES:
        for text in pb.prompts(p):
            assert text.startswith(pb.GUIDE), p
            assert not [h for h in hidden if h in text], p


def test_labels_cover_every_case_with_valid_values():
    labels = pb.load_labels()
    ids = {c["id"] for c in fa.cases()}
    assert set(labels["set_at_run"]) == ids
    for p in pb.PASSES:
        assert set(labels["passes"][p]) == ids, p
        for i, row in labels["passes"][p].items():
            for k, allowed in nb.VALUES.items():
                assert row[k] in allowed, (p, i, k)


def test_labels_were_made_from_this_guide_and_these_prompts():
    labels, now = pb.load_labels(), pb.fingerprints()
    assert labels["guide_sha256"] == now["guide_sha256"], "the guide changed after the labelling run"
    assert labels["prompts_sha256"] == now["prompts_sha256"], "the prompts changed after the labelling run"


def test_the_reported_result_is_measured_against_the_set_at_the_run():
    labels = pb.load_labels()
    gold = labels["set_at_run"]
    for p in pb.PASSES:
        raw, k = nb.agreement(gold, labels["passes"][p], "expected")
        assert (round(raw, 2), round(k, 2)) == (0.94, 0.88), p
    dis = pb.disagreements(labels)
    assert len(dis) == 2 and not any(d["stable"] for d in dis)
    assert len(pb.separated(labels, "A")) == len(pb.separated(labels, "B")) == 7


def test_checked_in_review_page_matches_the_labels():
    assert Path("docs/pairs_blind_review.md").read_text() == pb.render_markdown(), \
        "regenerate with: python -m eval.pairs_blind > docs/pairs_blind_review.md"
