"""E7d: the blind check of the facts-against pairs. No network.

The prompts must show the labeller nothing but the guide and the user's words, the guide must be E7b's with exactly
the owner's 2026-11-25 rulings, and the two versions of a situation must never share a batch.
"""
import re

from eval import facts_against_dev as fa
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
