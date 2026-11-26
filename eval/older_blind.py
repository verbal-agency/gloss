"""E7b: a label-only check of the older dev cases (docs/e7b_older_label_check_goal.md).

The older dev pool (G40 to G42) was labelled before rule (b), the owner's
2026-11-22 rule and the conventions of 2026-11-24 and 2026-11-25. E7 tunes its
thresholds on it. Here a model that wrote none of these cases labels them from
the user's words alone, under E8b's guide with the 2026-11-25 clarifications
added. Where both passes disagree with a stored label, the owner rules.

The older sets record only the expected action, so only `expected` is compared;
the labeller's other fields are kept to explain a disagreement.

Conversations come from their source sets, user turns only. The dev pool holds
only the conversations whose recorded histories survived, and that list lives
with the recorded histories, so a conversation's disagreement is acted on only
once its membership is checked.

    python -m eval.older_blind --prompts DIR     write the prompt files (A1.md ... B6.md)
    python -m eval.older_blind --collect DIR [NOTE ...]
    python -m eval.older_blind                   print the results page
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

from eval import g41_eval as g41
from eval import g42_eval as g42
from eval import ground_classifier_eval as g
from eval import multiturn_dataset as mt
from eval import multiturn_heldout as mh
from eval import nuanced_blind as nb
from eval import proposals_dataset as pd
from eval.g43_explore import RELABELLED

PASSES = ("A", "B")
BATCHES = 6
_ID_SEED = 82000
_ORDER_SEEDS = {"A": 82001, "B": 82002}
LABELS_PATH = Path(__file__).with_name("older_blind_labels.json")

# The owner's rulings on the 22 stable disagreements (2026-11-25). Only these five change. Under the narrowed rule,
# each plan makes the problem impossible by construction (a limiter or connection cap below the provider's limit, an
# idempotency key). A conversation's relabel applies only if that conversation is in the dev pool, that is, if its
# recorded history survived. The other 17 keep their stored labels: the six older objections stand, because the
# user's facts rule out the plan whether or not a cause is named.
RELABELS: dict[str, str] = {
    "g41/single/absent/partner-rate-limit-fits": "none",
    "g42/single/absent/mail-connections-fits": "none",
    "g41/late_absent/partner-rate-limit-fits": "none",
    "g42/late_absent/mail-connections-fits": "none",
    "held/late_absent/snd-02": "none",
}

# The owner's clarifications of 2026-11-25, added to E8b's guide as (old, new) pairs.
_CHANGES = [
    ("- Judge the user's whole plan, not only the step they ask for in the latest message.\n",
     "- Judge the user's whole plan, not only the step they ask for in the latest message.\n"
     "- When the user names two causes, judge the one the plan acts on.\n"),
    ("  - A timing remark followed by \"so it's X\" makes the cause asserted.\n",
     "  - A timing remark followed by \"so it's X\" makes the cause asserted.\n"
     "  - A cause the user names by testing it counts as stated, even when the test proves nothing.\n"),
    ("  - a design fact that is only a plausible reason.\n",
     "  - a design fact that is only a plausible reason.\n\n"
     "  Timing plus a pattern that singles the cause out is evidence, even if the user never names the cause.\n"),
    ("  Judge money against the size of the organisation.\n",
     "  Judge money against the size of the organisation, and count the time of everyone involved.\n"),
    ("when the plan breaks it or puts it at risk, unless",
     "when the plan breaks it, or the user's own facts show it would, unless"),
    ("If the plan delivers the goal whatever is causing the problem, stay quiet",
     "If the plan is cheap or reversible and delivers the goal whatever is causing the problem, stay quiet"),
]


def _current_guide() -> str:
    guide = nb.GUIDE
    for old, new in _CHANGES:
        assert guide.count(old) == 1, old
        guide = guide.replace(old, new)
    return guide


GUIDE = _current_guide()


# ── the older cases, from their source sets ──────────────────────────────────

def cases() -> list[dict]:
    """Every older single message, and every older conversation's user turns."""
    out = []
    for p in pd.load():
        out.append({"id": f"full/{p.id}", "source": "G40 proposals", "shape": "single", "scenario": p.kind,
                    "expected": "none" if p.kind == "sound" else "objected",
                    "query": pd.prompts(p)["owned_build"]})
    for b in pd.bare_items():
        out.append({"id": f"bare/{b['id']}", "source": "G40 bare", "shape": "single", "scenario": b["bare_kind"],
                    "expected": g._BARE_EXPECTED[b["bare_kind"]], "query": b["prompt"]})
    for source, singles in (("G41", g41.h.single_cases()), ("G42", g42.h.single_cases())):
        for c in singles:
            out.append({"id": c["id"], "source": source, "shape": "single", "scenario": c["scenario"],
                        "expected": "none" if c["id"] in RELABELLED else c["expected"], "query": c["query"]})
    for source, convs, mapping in (("multiturn", mt.load(), g._MT_EXPECTED),
                                   ("multiturn held-out", mh.load(), g._MT_EXPECTED),
                                   ("G41", g41.h.load(), g41._LATE_EXPECTED),
                                   ("G42", g42.h.load(), g41._LATE_EXPECTED)):
        for c in convs:
            out.append({"id": c.id, "source": source, "shape": "conversation", "scenario": c.scenario,
                        "expected": "none" if c.id in RELABELLED else mapping[c.scenario],
                        "user_turns": list(c.user_turns)})
    return out


def neutral_ids() -> dict[str, str]:
    ids = [c["id"] for c in cases()]
    random.Random(_ID_SEED).shuffle(ids)
    return {cid: f"o{n:03d}" for n, cid in enumerate(ids, 1)}


def order(pass_name: str) -> list[dict]:
    cs = cases()
    random.Random(_ORDER_SEEDS[pass_name]).shuffle(cs)
    return cs


def render_blind(c: dict, nid: str) -> str:
    if c["shape"] == "single":
        lines = [f"### {nid}", "", "Message:", ""] + nb._quote(c["query"])
    else:
        lines = [f"### {nid} (conversation)", ""]
        for n, turn in enumerate(c["user_turns"], 1):
            judged = " (the turn being judged)" if n == len(c["user_turns"]) else ""
            lines += [f"Turn {n}{judged}:", ""] + nb._quote(turn) + [""]
    return "\n".join(lines).rstrip("\n")


def batches(pass_name: str) -> list[list[dict]]:
    cs = order(pass_name)
    size = -(-len(cs) // BATCHES)
    return [cs[b * size:(b + 1) * size] for b in range(BATCHES)]


def prompts(pass_name: str) -> list[str]:
    ids = neutral_ids()
    return [GUIDE + f"\n## Cases ({len(chunk)})\n\n" + "\n\n".join(render_blind(c, ids[c["id"]]) for c in chunk) + "\n"
            for chunk in batches(pass_name)]


def fingerprints() -> dict:
    return {"guide_sha256": nb._sha256(GUIDE),
            "prompts_sha256": {p: [nb._sha256(t) for t in prompts(p)] for p in PASSES}}


# ── collecting ───────────────────────────────────────────────────────────────

def collect(answer_dir: Path, reruns: list[str] | None = None) -> dict:
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
    stored = {c["id"]: c["expected"] for c in cases()}
    return {"labeller": "a model that wrote none of these cases and none of the Jev questions",
            **fingerprints(), "reruns": list(reruns or []),
            "passes": {p: dict(sorted(passes[p].items())) for p in PASSES},
            "stored_at_run": dict(sorted(stored.items()))}


def load_labels() -> dict:
    return json.loads(LABELS_PATH.read_text())


# ── results page ─────────────────────────────────────────────────────────────

def disagreements(labels: dict) -> list[dict]:
    """Cases where pass A or B differs from the stored label; stable ones first."""
    stored, a, b = labels["stored_at_run"], labels["passes"]["A"], labels["passes"]["B"]
    out = []
    for c in cases():
        i = c["id"]
        if a[i]["expected"] != stored[i] or b[i]["expected"] != stored[i]:
            out.append({"case": c, "stable": a[i]["expected"] == b[i]["expected"] != stored[i]})
    return sorted(out, key=lambda d: (d["case"]["shape"] != "single", not d["stable"]))


def _agreement(x: dict, y: dict, ids: list[str]) -> str:
    pairs = [(x[i], y[i]) for i in ids]
    raw = sum(p == q for p, q in pairs) / len(pairs)
    return f"{raw:.2f} (κ {nb.kappa(pairs):.2f})"


def render_markdown() -> str:
    labels = load_labels()
    stored, a, b = labels["stored_at_run"], labels["passes"]["A"], labels["passes"]["B"]
    ea, eb = {i: r["expected"] for i, r in a.items()}, {i: r["expected"] for i, r in b.items()}
    cs = cases()
    lines = [
        "# E7b: a label-only check of the older dev cases", "",
        "Generated from `eval/older_blind.py` and `eval/older_blind_labels.json`; regenerate with "
        "`python -m eval.older_blind > docs/older_blind_review.md`. Don't edit by hand.", "",
        f"The labeller was {labels['labeller']}. It saw only the guide in `eval/older_blind.py` (E8b's guide with the "
        "owner's 2026-11-25 clarifications) and the user's words, under neutral ids and in a shuffled order. The goal is "
        "in [e7b_older_label_check_goal.md](e7b_older_label_check_goal.md).", "",
        f"Reruns: {'; '.join(labels['reruns']) if labels['reruns'] else 'none'}.", "",
        "## Agreement on `expected`", "",
        "| Cases | n | Stored vs A | Stored vs B | A vs B |", "|---|---|---|---|---|"]
    for name, ids in (("single messages", [c["id"] for c in cs if c["shape"] == "single"]),
                      ("conversations", [c["id"] for c in cs if c["shape"] == "conversation"])):
        lines.append(f"| {name} | {len(ids)} | {_agreement(stored, ea, ids)} | {_agreement(stored, eb, ids)} | "
                     f"{_agreement(ea, eb, ids)} |")
    dis = disagreements(labels)
    by = Counter((d["case"]["shape"], d["stable"]) for d in dis)
    lines += ["", f"Disagreements: {len(dis)}. Stable (both passes give the same other label): "
              f"{by[('single', True)]} single messages and {by[('conversation', True)]} conversations.", "",
              "Single messages are all in the dev pool. A conversation is in it only if its recorded history "
              "survived, which is checked before its disagreement is acted on.", ""]
    for shape, title in (("single", "Single messages"), ("conversation", "Conversations")):
        mine = [d for d in dis if d["case"]["shape"] == shape]
        lines += [f"## {title} ({len(mine)})", ""]
        for d in mine:
            c = d["case"]
            i = c["id"]
            lines += [f"#### {i}{' (stable)' if d['stable'] else ''}", "",
                      f"{c['source']}, scenario `{c['scenario']}`.", ""]
            if shape == "single":
                lines += nb._quote(c["query"]) + [""]
            else:
                for n, turn in enumerate(c["user_turns"], 1):
                    judged = " (under test)" if n == len(c["user_turns"]) else ""
                    lines += [f"**User, turn {n}{judged}:**", ""] + nb._quote(turn) + [""]
            lines.append(f"- **Stored:** `{stored[i]}`")
            for who, lab in (("Pass A", a[i]), ("Pass B", b[i])):
                rev = "reversible" if lab["reversible"] else "hard to reverse"
                lines += [f"- **{who}:** `{lab['expected']}` · {lab['level']} · {lab['cost']}, {rev} · "
                          f"{lab['defeater']} · {lab['confidence']}", f"  - {lab['rationale']}"]
            lines.append("")
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
