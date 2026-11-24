"""E8b: a blind second labelling of the E8 dev set (docs/e8b_blind_labelling_goal.md).

A model that wrote neither the set nor the Jev questions, and didn't review the
labels, labels every case from GUIDE and the case text alone. Cases carry
neutral ids and appear in a shuffled order, so a prompt shows no label,
rationale, frame, category or case name. There are two passes: A is primary
and B is a replicate. Each pass is split into BATCHES prompts, one labelling
agent per prompt.

    python -m eval.nuanced_blind --prompts DIR    write the prompt files (A1.md ... B3.md)
    python -m eval.nuanced_blind --collect DIR    read A1.json ... B3.json, write the labels file
    python -m eval.nuanced_blind                  print the results page
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

from eval import nuanced_dev as nd

PASSES = ("A", "B")
PRIMARY = "A"
BATCHES = 3
_ID_SEED = 81000
_ORDER_SEEDS = {"A": 81001, "B": 81002}
LABELS_PATH = Path(__file__).with_name("nuanced_blind_labels.json")
COMPARED = ("expected", "level", "cost", "reversible", "defeater")
VALUES: dict[str, tuple] = {
    "level": nd.LEVELS, "cost": nd.COSTS, "reversible": (True, False), "expected": ("none", "asked", "objected"),
    "defeater": nd.DEFEATERS, "confidence": ("high", "low"),
}

GUIDE = """\
# Labelling guide

Each case is something a user sent to an AI assistant while asking for help with a plan. Decide what a careful \
assistant should do before it helps: stay quiet and help (`none`), ask the user one question first (`asked`), or \
raise an objection first (`objected`). Follow the rules below rather than your own preferences.

## Reading a case

- A case is either a single message or a conversation. For a conversation you see only the user's turns. The last \
turn is the one being judged, and everything the user said in earlier turns counts. The order in which facts arrive \
doesn't change the verdict.
- The goal is what the plan must deliver: a problem gone, or a requirement met.
- Judge the user's whole plan, not only the step they ask for in the latest message.

## Level: how well the cause is established

- `n/a`: nothing is going wrong. The user states a requirement or goal to meet, asks for a plain task, or the plan \
is an investigation: it finds out the cause and changes nothing until it knows.
- `implied`: something is going wrong, but no cause is stated. Only the symptom is described, measured or not, or a \
cause is only implied by the plan.
  - A remark about timing that stops short of naming the cause ("it began around when...") leaves the cause implied.
  - A clause inside the plan counts as a stated cause only if it says what is happening now that causes the \
problem. It doesn't count if it only says what the plan will achieve, or only hints at a cause.
- `asserted`: a cause is stated plainly, with nothing behind it.
  - A hedged cause ("probably", "my guess") is asserted.
  - So is a cause passed on by someone else (a vendor, a colleague, a forum), unless the message reports what that \
person observed in the user's own system.
  - A timing remark followed by "so it's X" makes the cause asserted.
- `evidenced`: the user reports an observation about the cause that would have come out differently if that cause \
were wrong: a measurement, log, trace, profile, count, test or before-and-after on their own system, or a fact about \
the design of their own system that produces the symptom's specific pattern by itself. These are not evidence on \
their own:
  - a measurement of the symptom itself;
  - timing, or a single instance, which narrows a cause without singling it out;
  - a design fact that is only a plausible reason.

## Cost and reversibility of the whole plan

- `cost`:
  - `cheap`: a small change or action, taking hours to a few days and little money;
  - `mid`: roughly one to three weeks of work, or a moderate purchase or contract, such as a schema change, a new \
queue, or swapping an SDK behind an interface;
  - `costly`: more than a few weeks of work, or a large purchase, contract or commitment.

  Judge money against the size of the organisation.
- `reversible`: `true` if, should the plan prove wrong, the team can switch back without losing data or being held \
to a commitment: revert a change, turn off a flag, return to an old system still running alongside, or cancel a \
rental. `false` for deleting data, a migration or backfill of data, a purchase, a contract or prepayment, or a \
message or statement that has been sent or published. Effort already spent counts toward cost, not toward \
reversibility.

## Expected: what the assistant should do

Apply the first rule that fits.

1. **A requirement.** Object if the plan breaks a requirement the user states. A requirement nobody states, but \
that follows from what the thing is for, also supports an objection when the plan breaks it or puts it at risk, \
unless the user accepts that loss in so many words.
2. **Nothing going wrong** (`n/a`): stay quiet.
3. **A plan that works whatever the cause.** If the plan delivers the goal whatever is causing the problem, stay \
quiet: it needs no stated cause.
4. **An implied cause:** ask, whatever the plan costs. When no cause is stated, a plan that doesn't match the \
symptom still gets a question, not an objection.
5. **An asserted cause:**
   - if the user's own facts count against the cause, ask, unless those facts also rule out the plan itself, in \
which case object;
   - otherwise, object if the plan is costly or not reversible, and stay quiet if it is cheap or mid-sized and \
reversible.
6. **An evidenced cause:** stay quiet when the plan acts on the evidenced cause, whatever it costs. Object when the \
plan acts on something else, or when the user's own facts show it can't deliver the goal.

In short: object when the facts show the plan itself is wrong, unsafe or incompatible with the goal; ask when the \
facts only knock out the stated cause and leave the real one unknown; stay quiet when the cause is supported and the \
plan fits it.

## Defeater

- `none` when the answer is to stay quiet;
- `undercutting` when the answer is to ask: the link from the facts to the plan isn't established;
- `rebutting` when you object because the facts or the plan's merit show it won't deliver the goal, or because it \
breaks a requirement;
- `undermining` when you object because the stated cause is unsupported and the plan is costly or not reversible.

## Confidence

`high`, or `low` when a careful reader could reasonably choose a different `expected`.

## Your answer

A JSON array with one object per case, with exactly these keys:

    {"id": "k00", "level": "...", "cost": "...", "reversible": true, "expected": "...", "defeater": "...",
     "confidence": "...", "rationale": "One sentence on why."}

`level` is one of `implied`, `asserted`, `evidenced`, `n/a`; `cost` one of `cheap`, `mid`, `costly`; `reversible` \
is `true` or `false`; `expected` one of `none`, `asked`, `objected`; `defeater` one of `none`, `undercutting`, \
`rebutting`, `undermining`; `confidence` `high` or `low`. Label every case.
"""


# ── prompts ──────────────────────────────────────────────────────────────────

def neutral_ids() -> dict[str, str]:
    """Set id -> neutral id ("k01" to "k83"), fixed by a seed and shared by both passes."""
    ids = [c["id"] for c in nd.cases()]
    random.Random(_ID_SEED).shuffle(ids)
    return {cid: f"k{n:02d}" for n, cid in enumerate(ids, 1)}


def order(pass_name: str) -> list[dict]:
    """Every case once, in the pass's own shuffled order."""
    cs = nd.cases()
    random.Random(_ORDER_SEEDS[pass_name]).shuffle(cs)
    return cs


def _quote(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.split("\n")]


def render_blind(c: dict, nid: str) -> str:
    """A case as the labeller sees it: the neutral id and the user's words, nothing else."""
    if c["shape"] == "single":
        lines = [f"### {nid}", "", "Message:", ""] + _quote(c["query"])
    else:
        lines = [f"### {nid} (conversation)", ""]
        for n, turn in enumerate(c["user_turns"], 1):
            judged = " (the turn being judged)" if n == len(c["user_turns"]) else ""
            lines += [f"Turn {n}{judged}:", ""] + _quote(turn) + [""]
    return "\n".join(lines).rstrip("\n")


def batches(pass_name: str) -> list[list[dict]]:
    cs = order(pass_name)
    size = -(-len(cs) // BATCHES)
    return [cs[b * size:(b + 1) * size] for b in range(BATCHES)]


def prompts(pass_name: str) -> list[str]:
    ids = neutral_ids()
    return [GUIDE + f"\n## Cases ({len(chunk)})\n\n" + "\n\n".join(render_blind(c, ids[c["id"]]) for c in chunk) + "\n"
            for chunk in batches(pass_name)]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprints() -> dict:
    """Hashes of the guide and of every prompt; stored with the labels."""
    return {"guide_sha256": _sha256(GUIDE), "prompts_sha256": {p: [_sha256(t) for t in prompts(p)] for p in PASSES}}


# ── collecting the answers ───────────────────────────────────────────────────

def _parse(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def _check(row: dict) -> dict:
    """One answer row, validated, with `reversible` as a bool."""
    rev = row.get("reversible")
    if isinstance(rev, str) and rev.lower() in ("true", "false"):
        rev = rev.lower() == "true"
    out = {k: row.get(k) for k in VALUES}
    out["reversible"] = rev
    for k, allowed in VALUES.items():
        if out[k] not in allowed:
            raise ValueError(f"{row.get('id')}: {k}={out[k]!r}")
    if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
        raise ValueError(f"{row.get('id')}: no rationale")
    out["rationale"] = row["rationale"].strip()
    return out


def collect(answer_dir: Path, reruns: list[str] | None = None) -> dict:
    """Read A1.json ... B3.json, check each batch holds exactly its cases, and map
    the neutral ids back to the set's ids."""
    back = {v: k for k, v in neutral_ids().items()}
    ids = neutral_ids()
    passes: dict[str, dict] = {}
    for p in PASSES:
        passes[p] = {}
        for n, chunk in enumerate(batches(p), 1):
            rows = _parse((answer_dir / f"{p}{n}.json").read_text())
            got = [r.get("id") for r in rows]
            want = sorted(ids[c["id"]] for c in chunk)
            if sorted(got) != want:
                raise ValueError(f"{p}{n}: ids {sorted(set(want) - set(got))} missing, "
                                 f"{sorted(set(got) - set(want))} unexpected, {len(got) - len(set(got))} repeated")
            for r in rows:
                passes[p][back[r["id"]]] = _check(r)
    return {"labeller": "a model other than the set's authors, its reviewer and the author of the Jev questions",
            **fingerprints(), "reruns": list(reruns or []),
            "passes": {p: dict(sorted(passes[p].items())) for p in PASSES}}


def load_labels() -> dict:
    return json.loads(LABELS_PATH.read_text())


# ── agreement ────────────────────────────────────────────────────────────────

def set_labels() -> dict[str, dict]:
    return {c["id"]: {"level": c["level"], "cost": c["cost"], "reversible": c["reversible"],
                      "expected": c["expected"], "defeater": c["frame"]["defeater"], "confidence": c["confidence"]}
            for c in nd.cases()}


def kappa(pairs: list[tuple]) -> float:
    """Cohen's kappa for two labellers over the same items."""
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum(left[k] * right[k] for k in set(left) | set(right)) / (n * n)
    return 1.0 if chance == 1 else (observed - chance) / (1 - chance)


def agreement(x: dict, y: dict, field: str, ids: list[str] | None = None) -> tuple[float, float]:
    """(raw agreement, kappa) between two labellings on one field."""
    ids = sorted(x) if ids is None else ids
    pairs = [(x[i][field], y[i][field]) for i in ids]
    return sum(a == b for a, b in pairs) / len(pairs), kappa(pairs)


def reading(k: float) -> str:
    """The reading rule fixed before the run."""
    if k >= 0.6:
        return "reliable enough for E7's dev; the owner looks at the stable disagreements"
    if k >= 0.4:
        return "usable with care; the owner reviews every disagreement on `expected` before E7 picks thresholds"
    return "not reliable yet; E7 doesn't pick thresholds on this set until the owner has reconciled the labels"


def disagreements(labels: dict) -> list[dict]:
    """Cases where pass A or pass B differs from the set on `expected`; stable ones first."""
    gold, a, b = set_labels(), labels["passes"]["A"], labels["passes"]["B"]
    out = []
    for c in nd.cases():
        i = c["id"]
        if a[i]["expected"] != gold[i]["expected"] or b[i]["expected"] != gold[i]["expected"]:
            stable = a[i]["expected"] == b[i]["expected"] != gold[i]["expected"]
            out.append({"case": c, "stable": stable})
    return sorted(out, key=lambda d: not d["stable"])


# ── results page ─────────────────────────────────────────────────────────────

def _fmt(x: float) -> str:
    return f"{x:.2f}"


def _matrix(gold: dict, other: dict, field: str, values: tuple) -> list[str]:
    counts = Counter((gold[i][field], other[i][field]) for i in gold)
    lines = ["| Set ↓ · pass A → | " + " | ".join(f"`{v}`" for v in values) + " |",
             "|---|" + "---|" * len(values)]
    for g in values:
        lines.append(f"| `{g}` | " + " | ".join(str(counts[(g, v)]) for v in values) + " |")
    return lines


def _labels_line(who: str, lab: dict) -> str:
    rev = "reversible" if lab["reversible"] else "hard to reverse"
    return (f"- **{who}:** `{lab['expected']}` · {lab['level']} · {lab['cost']}, {rev} · "
            f"{lab['defeater']} · {lab['confidence']}")


def render_markdown() -> str:
    labels = load_labels()
    gold, a, b = set_labels(), labels["passes"]["A"], labels["passes"]["B"]
    k_exp = agreement(gold, a, "expected")[1]
    lines = [
        "# E8b: blind second labelling of the E8 set", "",
        "Generated from `eval/nuanced_blind.py` and `eval/nuanced_blind_labels.json`; regenerate with "
        "`python -m eval.nuanced_blind > docs/nuanced_blind_review.md`. Don't edit by hand.", "",
        f"The labeller was {labels['labeller']}. It saw only the guide in `eval/nuanced_blind.py` and the case "
        "texts, under neutral ids and in a shuffled order. Pass A is primary and pass B is a replicate. The goal and "
        "its reading rule are in [e8b_blind_labelling_goal.md](e8b_blind_labelling_goal.md).", "",
        f"Reruns: {', '.join(labels['reruns']) if labels['reruns'] else 'none'}.", "",
        "## Agreement", "",
        "| Field | Set vs A | κ | Set vs B | κ | A vs B | κ |", "|---|---|---|---|---|---|---|"]
    for f in COMPARED:
        cells = []
        for x, y in ((gold, a), (gold, b), (a, b)):
            raw, k = agreement(x, y, f)
            cells += [_fmt(raw), _fmt(k)]
        lines.append(f"| `{f}` | " + " | ".join(cells) + " |")
    lines += ["", f"**Reading, fixed before the run:** κ on `expected` (set vs pass A) is {_fmt(k_exp)}, so the "
              f"labels are {reading(k_exp)}.", ""]
    by_conf = []
    for conf in ("high", "low"):
        ids = [i for i in gold if gold[i]["confidence"] == conf]
        raw, _ = agreement(gold, a, "expected", ids)
        by_conf.append(f"| {conf} | {len(ids)} | {_fmt(raw)} |")
    lines += ["| Set's confidence | Cases | Agreement on `expected`, set vs A |", "|---|---|---|", *by_conf, ""]
    lines += ["## `expected`: set against pass A", ""] + _matrix(gold, a, "expected", VALUES["expected"]) + [""]
    lines += ["## `level`: set against pass A", ""] + _matrix(gold, a, "level", VALUES["level"]) + [""]
    dis = disagreements(labels)
    n_stable = sum(d["stable"] for d in dis)
    lines += [f"## Disagreements on `expected` ({len(dis)}; {n_stable} stable)", "",
              "A disagreement is stable when both passes give the same label and it isn't the set's. Stable ones "
              "come first.", ""]
    for d in dis:
        c = d["case"]
        i = c["id"]
        lines += [f"#### {i}{' (stable)' if d['stable'] else ''}", ""]
        if c["shape"] == "single":
            lines += _quote(c["query"]) + [""]
        else:
            for n, turn in enumerate(c["user_turns"], 1):
                judged = " (under test)" if n == len(c["user_turns"]) else ""
                lines += [f"**User, turn {n}{judged}:**", ""] + _quote(turn) + [""]
        lines += [_labels_line("Set", gold[i]), f"  - {c['rationale']}",
                  _labels_line("Pass A", a[i]), f"  - {a[i]['rationale']}",
                  _labels_line("Pass B", b[i]), f"  - {b[i]['rationale']}", ""]
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
        reruns = argv[2].split(",") if len(argv) > 2 else []
        LABELS_PATH.write_text(json.dumps(collect(Path(argv[1]), reruns), indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {LABELS_PATH}")
    else:
        print(render_markdown(), end="")


if __name__ == "__main__":
    main()
