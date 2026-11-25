"""E7d: a blind check of the facts-against pairs' labels (docs/e7d_pairs_blind_check_goal.md).

E7 tunes the thresholds of its two new questions mainly on the 16 pairs of E7a, whose labels have one author and no
review yet. Here a model that wrote none of the pairs, none of the Jev questions and none of their examples labels
them from the user's words alone, under E7b's guide with the owner's rulings of 2026-11-25 added.

The two versions of a situation never share a batch. Each pass has two batches, each holding one version of every
situation, so each version is judged without its twin, as the classifier will judge it.

    python -m eval.pairs_blind --prompts DIR     write the prompt files (A1.md, A2.md, B1.md, B2.md)
    python -m eval.pairs_blind --collect DIR [NOTE ...]
                                                 read A1.json ... B2.json, write the labels file;
                                                 each NOTE records one rerun
    python -m eval.pairs_blind                   print the results page
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

from eval import facts_against_dev as fa
from eval import nuanced_blind as nb
from eval import older_blind as ob

PASSES = ("A", "B")
PRIMARY = "A"
BATCHES = 2
_ID_SEED = 83000
_ORDER_SEEDS = {"A": 83001, "B": 83002}
LABELS_PATH = Path(__file__).with_name("pairs_blind_labels.json")
# `level` isn't compared: the set records the cause as stated before the fact, and this branch doesn't score it.
COMPARED = ("expected", "cost", "reversible", "defeater")

# The owner's rulings of 2026-11-25, added to E7b's guide as (old, new) pairs:
# - "a plan that works whatever the cause" is narrowed to a plan that makes the problem impossible by construction;
# - the user's own facts are judged at any level, before the level's own rule: object when they show the plan can't
#   deliver the goal, whether or not a cause is named; otherwise ask when they count against the cause the plan acts
#   on. E7b's guide had the second part only for asserted causes; E7's table applies it before the evidence row.
_CHANGES = [
    ("3. **A plan that works whatever the cause.** If the plan is cheap or reversible and delivers the goal whatever "
     "is causing the problem, stay quiet: it needs no stated cause.\n",
     "3. **A plan that makes the problem impossible by construction.** If the plan is cheap or reversible and makes "
     "the problem impossible whatever is causing it, as a uniqueness check, a hard cap below a limit or an "
     "idempotency key does, stay quiet: it needs no stated cause. A plan that is only likely to help whatever the "
     "cause doesn't count.\n"),
    ("4. **An implied cause:** ask, whatever the plan costs.",
     "4. **The user's own facts,** whatever the level:\n"
     "   - if they show the plan can't deliver the goal, whatever the real cause turns out to be, object, whether or "
     "not a cause is named;\n"
     "   - otherwise, if they count against the cause the plan acts on, stated or only implied by the plan, ask. A "
     "fact that only shows another cause is also at work doesn't count against it.\n"
     "5. **An implied cause:** ask, whatever the plan costs."),
    ("5. **An asserted cause:**\n"
     "   - if the user's own facts count against the cause, ask, unless those facts also rule out the plan itself, in "
     "which case object;\n"
     "   - otherwise, object if the plan is costly or not reversible, and stay quiet if it is cheap or mid-sized and "
     "reversible.\n",
     "6. **An asserted cause:** object if the plan is costly or not reversible, and stay quiet if it is cheap or "
     "mid-sized and reversible.\n"),
    ("6. **An evidenced cause:** stay quiet when the plan acts on the evidenced cause, whatever it costs. Object when "
     "the plan acts on something else, or when the user's own facts show it can't deliver the goal.\n",
     "7. **An evidenced cause:** stay quiet when the plan acts on the evidenced cause, whatever it costs. Object when "
     "the plan acts on something else.\n"),
]


def _current_guide() -> str:
    guide = ob.GUIDE
    for old, new in _CHANGES:
        assert guide.count(old) == 1, old
        guide = guide.replace(old, new)
    return guide


GUIDE = _current_guide()


# ── prompts ──────────────────────────────────────────────────────────────────

def cases() -> list[dict]:
    return fa.cases()


def neutral_ids() -> dict[str, str]:
    """Set id -> neutral id ("t01" to "t16"), fixed by a seed and shared by both passes."""
    ids = [c["id"] for c in cases()]
    random.Random(_ID_SEED).shuffle(ids)
    return {cid: f"t{n:02d}" for n, cid in enumerate(ids, 1)}


def batches(pass_name: str) -> list[list[dict]]:
    """Two batches, each with one version of every situation, and in each shape two `asked` and two `objected`
    versions. The pass's seed fixes which situations send which version to which batch, and the order within each
    batch."""
    rng = random.Random(_ORDER_SEEDS[pass_name])
    by_id = {c["id"]: c for c in cases()}
    out: list[list[dict]] = [[] for _ in range(BATCHES)]
    for shape in fa.SHAPES:
        families = sorted(k for k, s in fa.SITUATIONS.items() if s["shape"] == shape)
        rng.shuffle(families)
        half = len(families) // 2
        for n, family in enumerate(families):
            first, second = fa.VERSIONS if n < half else fa.VERSIONS[::-1]
            out[0].append(by_id[f"{fa.TAG}/{shape}/{family}/{first}"])
            out[1].append(by_id[f"{fa.TAG}/{shape}/{family}/{second}"])
    for batch in out:
        rng.shuffle(batch)
    return out


def prompts(pass_name: str) -> list[str]:
    ids = neutral_ids()
    return [GUIDE + f"\n## Cases ({len(chunk)})\n\n" + "\n\n".join(nb.render_blind(c, ids[c["id"]]) for c in chunk)
            + "\n" for chunk in batches(pass_name)]


def fingerprints() -> dict:
    """Hashes of the guide and of every prompt; stored with the labels."""
    return {"guide_sha256": nb._sha256(GUIDE),
            "prompts_sha256": {p: [nb._sha256(t) for t in prompts(p)] for p in PASSES}}


# ── collecting the answers ───────────────────────────────────────────────────

def set_labels() -> dict[str, dict]:
    return {c["id"]: {"level": c["level"], "cost": c["cost"], "reversible": c["reversible"],
                      "expected": c["expected"], "defeater": c["frame"]["defeater"], "confidence": c["confidence"]}
            for c in cases()}


def snapshot() -> dict[str, dict]:
    """The set's labels and rationales as they stand; stored with the blind labels when they are collected."""
    labels = set_labels()
    return {c["id"]: {**labels[c["id"]], "rationale": c["rationale"]} for c in sorted(cases(), key=lambda c: c["id"])}


def collect(answer_dir: Path, reruns: list[str] | None = None) -> dict:
    """Read A1.json ... B2.json, check each batch holds exactly its cases, and map the neutral ids back."""
    ids = neutral_ids()
    back = {v: k for k, v in ids.items()}
    passes: dict[str, dict] = {}
    for p in PASSES:
        passes[p] = {}
        for n, chunk in enumerate(batches(p), 1):
            rows = nb._parse((answer_dir / f"{p}{n}.json").read_text())
            got, want = sorted(r.get("id") for r in rows), sorted(ids[c["id"]] for c in chunk)
            if got != want:
                raise ValueError(f"{p}{n}: ids {sorted(set(want) - set(got))} missing, "
                                 f"{sorted(set(got) - set(want))} unexpected, {len(got) - len(set(got))} repeated")
            for r in rows:
                passes[p][back[r["id"]]] = nb._check(r)
    return {"labeller": "a model that wrote none of the pairs, none of the Jev questions and none of their examples",
            **fingerprints(), "reruns": list(reruns or []),
            "passes": {p: dict(sorted(passes[p].items())) for p in PASSES}, "set_at_run": snapshot()}


def load_labels() -> dict:
    return json.loads(LABELS_PATH.read_text())


# ── measures ─────────────────────────────────────────────────────────────────

def reading(k: float) -> str:
    """The reading rule fixed before the run."""
    if k >= 0.6:
        return "reliable enough to tune `t_fa` and `t_ro` on, once the owner has ruled on the disagreements"
    if k >= 0.4:
        return ("usable with care: tuning waits for the owner's rulings, and E7 reports the agreement as a limit")
    return "not reliable yet: E7 doesn't tune `t_fa` and `t_ro` on the pairs until the owner has reconciled the labels"


def disagreements(labels: dict) -> list[dict]:
    """Cases where pass A or pass B differs on `expected` from the set as it was at the run; stable ones first."""
    gold, a, b = labels["set_at_run"], labels["passes"]["A"], labels["passes"]["B"]
    out = []
    for c in cases():
        i = c["id"]
        if a[i]["expected"] != gold[i]["expected"] or b[i]["expected"] != gold[i]["expected"]:
            out.append({"case": c, "stable": a[i]["expected"] == b[i]["expected"] != gold[i]["expected"]})
    return sorted(out, key=lambda d: not d["stable"])


def separated(labels: dict, pass_name: str) -> list[str]:
    """Situations whose two versions the pass labels `asked` and `objected`, the set's way round."""
    run = labels["passes"][pass_name]
    out = []
    for family in fa.SITUATIONS:
        got = {c["version"]: run[c["id"]]["expected"] for c in cases() if c["family"] == family}
        if got == {"asked": "asked", "objected": "objected"}:
            out.append(family)
    return out


# ── results page ─────────────────────────────────────────────────────────────

def _fmt(x: float) -> str:
    return f"{x:.2f}"


def _labels_line(who: str, lab: dict) -> str:
    rev = "reversible" if lab["reversible"] else "hard to reverse"
    return (f"- **{who}:** `{lab['expected']}` · {lab['level']} · {lab['cost']}, {rev} · "
            f"{lab['defeater']} · {lab['confidence']}")


def render_markdown() -> str:
    labels = load_labels()
    gold, a, b = labels["set_at_run"], labels["passes"]["A"], labels["passes"]["B"]
    k_exp = nb.agreement(gold, a, "expected")[1]
    lines = [
        "# E7d: blind check of the facts-against pairs", "",
        "Generated from `eval/pairs_blind.py` and `eval/pairs_blind_labels.json`; regenerate with "
        "`python -m eval.pairs_blind > docs/pairs_blind_review.md`. Don't edit by hand.", "",
        f"The labeller was {labels['labeller']}. It saw only the guide in `eval/pairs_blind.py` (E7b's guide with the "
        "owner's rulings of 2026-11-25) and the user's words, under neutral ids and in a shuffled order. The two "
        "versions of a situation were never in the same batch. Pass A is primary and pass B is a replicate. The goal "
        "and its reading rule are in [e7d_pairs_blind_check_goal.md](e7d_pairs_blind_check_goal.md).", "",
        "Everything below compares the passes with the set as it was at the run. Labels changed since are listed at "
        "the end.", "",
        f"Reruns: {'; '.join(labels['reruns']) if labels['reruns'] else 'none'}.", "",
        "## Agreement", "",
        "| Field | Set vs A | κ | Set vs B | κ | A vs B | κ |", "|---|---|---|---|---|---|---|"]
    for f in COMPARED:
        cells = []
        for x, y in ((gold, a), (gold, b), (a, b)):
            raw, k = nb.agreement(x, y, f)
            cells += [_fmt(raw), _fmt(k)]
        lines.append(f"| `{f}` | " + " | ".join(cells) + " |")
    lines += ["", f"**Reading, fixed before the run:** κ on `expected` (set vs pass A) is {_fmt(k_exp)}, so the "
              f"labels are {reading(k_exp)}. Whatever the κ, the owner rules on every disagreement.", "",
              "## The pairs", "",
              "Each situation's `against` version should be `asked` and its `rules_out` version `objected`. A pass "
              "separates a pair when it labels both that way.", "",
              "| Situation | Shape | `against`: A · B | `rules_out`: A · B |", "|---|---|---|---|"]
    for family, s in fa.SITUATIONS.items():
        ids = {c["version"]: c["id"] for c in cases() if c["family"] == family}
        cells = [" · ".join(f"`{run[ids[v]]['expected']}`" for run in (a, b)) for v in fa.VERSIONS]
        lines.append(f"| {family} | {s['shape']} | {cells[0]} | {cells[1]} |")
    sep_a, sep_b = separated(labels, "A"), separated(labels, "B")
    lines += ["", f"Pairs separated: {len(sep_a)} of {len(fa.SITUATIONS)} by pass A, {len(sep_b)} by pass B.", "",
              "## `expected`: set against pass A", ""]
    counts = Counter((gold[i]["expected"], a[i]["expected"]) for i in gold)
    values = nb.VALUES["expected"]
    lines += ["| Set ↓ · pass A → | " + " | ".join(f"`{v}`" for v in values) + " |", "|---|" + "---|" * len(values)]
    lines += [f"| `{g}` | " + " | ".join(str(counts[(g, v)]) for v in values) + " |" for g in fa.VERSIONS]
    dis = disagreements(labels)
    lines += ["", f"## Disagreements on `expected` ({len(dis)}; {sum(d['stable'] for d in dis)} stable)", "",
              "A disagreement is stable when both passes give the same label and it isn't the set's. Stable ones "
              "come first.", ""]
    for d in dis:
        c = d["case"]
        i = c["id"]
        lines += [f"#### {i}{' (stable)' if d['stable'] else ''}", ""]
        if c["shape"] == "single":
            lines += nb._quote(c["query"]) + [""]
        else:
            for n, turn in enumerate(c["user_turns"], 1):
                judged = " (under test)" if n == len(c["user_turns"]) else ""
                lines += [f"**User, turn {n}{judged}:**", ""] + nb._quote(turn) + [""]
        lines += [_labels_line("Set at the run", gold[i]), f"  - {gold[i]['rationale']}",
                  _labels_line("Pass A", a[i]), f"  - {a[i]['rationale']}",
                  _labels_line("Pass B", b[i]), f"  - {b[i]['rationale']}", ""]
    now = set_labels()
    fields = ("expected", "cost", "reversible", "defeater", "confidence")
    changed = [i for i in sorted(gold) if any(now[i][f] != gold[i][f] for f in fields)]
    lines += ["## Since the run", ""]
    if not changed:
        lines += ["No label has changed since the run.", ""]
    else:
        lines += ["These labels have changed since the run:", ""]
        for i in changed:
            diffs = ", ".join(f"`{f}` {gold[i][f]} → {now[i][f]}" for f in fields if now[i][f] != gold[i][f])
            lines.append(f"- {i}: {diffs}")
        (ra, ka), (rb, kb) = nb.agreement(now, a, "expected"), nb.agreement(now, b, "expected")
        lines += ["", f"Against the set as it stands now, agreement on `expected` is {_fmt(ra)} (κ {_fmt(ka)}) for "
                  f"pass A and {_fmt(rb)} (κ {_fmt(kb)}) for pass B.", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--prompts"]:
        out = Path(argv[1])
        out.mkdir(parents=True, exist_ok=True)
        for p in PASSES:
            for n, text in enumerate(prompts(p), 1):
                (out / f"{p}{n}.md").write_text(text)
        print(json.dumps(fingerprints(), indent=1))
    elif argv[:1] == ["--collect"]:
        LABELS_PATH.write_text(json.dumps(collect(Path(argv[1]), argv[2:]), indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {LABELS_PATH}")
    else:
        print(render_markdown(), end="")


if __name__ == "__main__":
    main()
