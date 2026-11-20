"""G41: Jev with structured state, a plain problem question and probability rules.

Spec and rule: docs/v3_spike.md, G41 (fixed before any run). In short:

  dev   all 105 G40 cases (eval/ground_classifier_eval.py), used to pick one
        Jev setup: which state, which rule, shared or per-shape thresholds.
  test  eval/g41_heldout.py: 38 single messages and the conversations whose
        frozen earlier turns survive. Used once. Scored per group and per
        shape; a failed classification is a miss.

Order (each step refuses to run before the one it depends on):
    python -m eval.g41_eval --record      # histories, after the owner's review
    python -m eval.g41_eval --arm llm
    python -m eval.g41_eval --arm jev      # both Jev states; needs TYPESAFE_API_KEY
    python -m eval.g41_eval --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from app.config import settings
from app.pipeline import assumptions, jev_ground
from app.pipeline.jev_ground import G41Rule
from eval import g41_heldout as h
from eval import ground_classifier_eval as g
from eval import multiturn_eval as me
from eval import proposals_eval as pe

load_dotenv()

OUT = Path("results/g41")
HISTORIES = OUT / "late_histories.json"
REPEATS = 3
TOLERANCE = 0.07          # about one case in 14, as in G40
PER_SHAPE_MARGIN = 0.02   # per-shape thresholds must beat shared ones by this on dev
JEV_ARMS = ("jev_text", "jev_json")
HISTORY_MODEL = "anthropic/claude-sonnet-5-5"   # the unaided model, as in G37 and G37b
HISTORY_JUDGE = "anthropic/claude-sonnet-5-5"

_LATE_EXPECTED = {"late_sound": "none", "late_absent": "asked", "late_answered": "none"}
# The groups the decision is made on. Contradiction is reported only.
GATED = ("sound", "task", "absent", "answered")


# --------------------------------------------------------------------------- cases

def _group(case: dict) -> str:
    """The test group a case is scored in."""
    s = case["scenario"]
    if s in ("task", "late_task"):
        return "task"
    if s in ("sound", "late_sound"):
        return "sound"
    if s in ("absent", "late_absent"):
        return "absent"
    if s == "late_answered":
        return "answered"
    return "contradicted"


def dev_cases() -> list[dict]:
    return [{**c, "split": "dev", "shape": "conversation" if c["context"] else "single"}
            for c in g.cases()]


def test_cases() -> list[dict]:
    return held_out_cases(h.single_cases(), h.load(), HISTORIES)


def held_out_cases(singles: list[dict], convs: list, histories_path: Path,
                   split: str = "test") -> list[dict]:
    """Single messages plus the conversations whose frozen histories survived."""
    out = []
    for c in singles:
        out.append({**c, "split": split, "shape": "single", "context": None,
                    "messages": [{"role": "user", "content": c["query"]}]})
    if not histories_path.exists():
        return out
    histories = json.loads(histories_path.read_text())["histories"]
    for c in convs:
        rec = histories.get(c.id)
        if not rec or not rec["survived"]:
            continue
        messages = c.messages(rec["replies"])
        scenario = "late_task" if c.family.startswith("task-") else c.scenario
        out.append({"id": c.id, "split": split, "shape": "conversation", "scenario": scenario,
                    "family": c.family,
                    "expected": _LATE_EXPECTED[c.scenario], "query": messages[-1]["content"],
                    "context": assumptions.conversation_view(messages), "messages": messages})
    return out


# --------------------------------------------------------------------------- histories

async def record(concurrency: int) -> None:
    if h.REVIEW != "owner-checked":
        raise SystemExit("eval/g41_heldout.py is not owner-checked: no run before the review")
    await record_histories(h.load(), HISTORIES, concurrency)


async def record_histories(convs: list, path: Path, concurrency: int) -> None:
    """Record the conversations' earlier answers once and freeze them."""
    if path.exists():
        raise SystemExit(f"{path} exists: histories are recorded once and frozen")
    pe.JUDGE_EFFORT = "low"
    # late_answered's turn 1 is answered by the grounding check. Pin the check's
    # classifier to the model the baseline is measured on; .env's default
    # (sonnet-4-6) never asks, so no answered conversation would survive.
    settings.ground_model = g.LLM_GROUND_MODEL
    sem = asyncio.Semaphore(concurrency)

    async def one(c):
        async with sem:
            try:
                return c.id, await me.record_history(c, HISTORY_MODEL, HISTORY_JUDGE), None
            except Exception as e:
                return c.id, None, repr(e)

    results = await asyncio.gather(*(one(c) for c in convs))
    histories = {cid: rec for cid, rec, err in results if err is None}
    failed = [f"{cid}: {err}" for cid, _, err in results if err is not None]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": HISTORY_MODEL, "judge": HISTORY_JUDGE,
                                     "failed": failed, "histories": histories}, indent=2))
    by = defaultdict(lambda: [0, 0])
    for c in convs:
        if c.id in histories:
            key = "late_task" if c.family.startswith("task-") else c.scenario
            by[key][0] += histories[c.id]["survived"]
            by[key][1] += 1
    print(f"[{path.parent.name}] histories: {len(histories)} recorded, {len(failed)} failed")
    for k, (s, n) in sorted(by.items()):
        print(f"    {k}: {s} of {n} survived")


# --------------------------------------------------------------------------- arms

async def classify_jev(case: dict, form: str, repeat: int) -> dict:
    conversation = case["context"] is not None
    state = jev_ground.json_state(case["messages"]) if form == "json" else (case["context"] or case["query"])
    from eval import cache
    return await cache.get_or_run(
        "ground_jev_g41", {"model": settings.jev_model, "form": form,
                           "battery": jev_ground.g41_battery(form, conversation),
                           "state": state, "repeat": repeat},
        lambda: jev_ground.ask_jev_g41(state, form, conversation))


async def run_arm(arm: str, repeats: int, concurrency: int) -> None:
    if h.REVIEW != "owner-checked":
        raise SystemExit("eval/g41_heldout.py is not owner-checked: no run before the review")
    if not HISTORIES.exists():
        raise SystemExit("record the histories first (--record)")
    cases = dev_cases() + test_cases()
    sem = asyncio.Semaphore(concurrency)
    jobs = ([("llm", None)] if arm == "llm" else [(a, a.split("_")[1]) for a in JEV_ARMS])

    async def one(name, form, case, rep):
        async with sem:
            try:
                out = (await g.classify_llm(case, rep) if form is None
                       else await classify_jev(case, form, rep))
                return {"arm": name, "id": case["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": name, "id": case["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(n, f, c, r) for n, f in jobs for c in cases
                                  for r in range(1, repeats + 1)))
    OUT.mkdir(parents=True, exist_ok=True)
    for name, _ in jobs:
        mine = [r for r in rows if r["arm"] == name]
        (OUT / f"{name}.json").write_text(json.dumps(
            {"arm": name, "model": g.LLM_GROUND_MODEL if name == "llm" else settings.jev_model,
             "repeats": repeats, "rows": mine}, indent=2))
        print(f"[{name}] {sum('output' in r for r in mine)} classified, "
              f"{sum('error' in r for r in mine)} failed")


# --------------------------------------------------------------------------- rules and scoring

def rules() -> list[G41Rule]:
    out = [G41Rule(family="choice")]
    contra = (0.3, 0.5, 0.7, 0.9)
    for gate, gt, ct, xt in itertools.product(("is_fix", "problem_described"), (0.3, 0.5, 0.7),
                                              (0.3, 0.5, 0.7), contra):
        out.append(G41Rule(family="route", gate=gate, gate_t=gt, cause_t=ct, contra_t=xt))
    for ct, xt in itertools.product((0.2, 0.3, 0.4, 0.5), contra):
        out.append(G41Rule(family="link", gate=None, gate_t=0.0, cause_t=ct, contra_t=xt))
        for gt in (0.3, 0.5, 0.7):
            out.append(G41Rule(family="link", gate="problem_described", gate_t=gt, cause_t=ct, contra_t=xt))
    return out


def _answers(arm: str) -> dict[str, list[dict]]:
    path = OUT / f"{arm}.json"
    if not path.exists():
        return {}
    out: dict = defaultdict(list)
    for r in json.loads(path.read_text())["rows"]:
        if "output" in r:
            out[r["id"]].append(r["output"])
    return out


def predict(answers: dict[str, list[dict]], cases: list[dict], single,
            conversation=None, action=jev_ground.g41_action) -> dict[str, list[str]]:
    """Actions per case; `conversation` (if given) is the rule for conversations."""
    out = {}
    for c in cases:
        rule = conversation if (conversation and c["shape"] == "conversation") else single
        out[c["id"]] = [action(a, rule) for a in answers.get(c["id"], [])]
    return out


def pick(answers_by_arm: dict[str, dict], dev: list[dict], candidates: list | None = None,
         action=jev_ground.g41_action) -> dict:
    """The one Jev setup, chosen on dev only (spec: shared thresholds unless
    per-shape ones beat them by PER_SHAPE_MARGIN balanced accuracy)."""
    candidates = rules() if candidates is None else candidates
    singles = [c for c in dev if c["shape"] == "single"]
    convs = [c for c in dev if c["shape"] == "conversation"]
    shared, per_shape = [], []

    def bal(ans, cases, r, conv=None):
        return g.score(predict(ans, cases, r, conv, action), cases)["balanced"]

    for arm, ans in answers_by_arm.items():
        scored = [(bal(ans, dev, r), r) for r in candidates]
        best_score, best_rule = max(scored, key=lambda x: x[0])
        shared.append((best_score, arm, best_rule, None))
        best_single = max(candidates, key=lambda r: bal(ans, singles, r))
        best_conv = max(candidates, key=lambda r: bal(ans, convs, r))
        both = bal(ans, dev, best_single, best_conv)
        per_shape.append((both, arm, best_single, best_conv))
    top_shared = max(shared, key=lambda x: x[0])
    top_split = max(per_shape, key=lambda x: x[0])
    chosen = top_split if top_split[0] >= top_shared[0] + PER_SHAPE_MARGIN else top_shared
    return {"arm": chosen[1], "single": chosen[2], "conversation": chosen[3],
            "dev_balanced": chosen[0],
            "shared_best": {"arm": top_shared[1], "rule": top_shared[2].name, "dev": top_shared[0]},
            "per_shape_best": {"arm": top_split[1], "single": top_split[2].name,
                               "conversation": top_split[3].name, "dev": top_split[0]},
            "per_arm_shared": {arm: {"rule": r.name, "dev": s} for s, arm, r, _ in shared}}


def _tally(preds: dict[str, list[str]], cases: list[dict], key, repeats: int) -> dict:
    """Hits per `key(case)`. Every case counts `repeats` times: a classification
    that failed or is missing is a miss, so a backend cannot raise its rate by
    failing on hard cases."""
    by: dict = defaultdict(lambda: [0, 0, 0, set()])
    for c in cases:
        got = preds.get(c["id"], [])[:repeats]
        cell = by[key(c)]
        cell[0] += sum(a == c["expected"] for a in got)
        cell[1] += repeats
        cell[2] += repeats - len(got)
        cell[3].add(c["id"])
    return {k: {"hit": hit, "n": n, "missing": miss, "cases": len(ids),
                "rate": round(hit / n, 3) if n else None}
            for k, (hit, n, miss, ids) in sorted(by.items())}


def group_rates(preds: dict[str, list[str]], cases: list[dict], repeats: int = REPEATS) -> dict:
    """Rates per group and per shape within it, e.g. "sound/single"."""
    return _tally(preds, cases, lambda c: f"{_group(c)}/{c['shape']}", repeats)


def family_rates(preds: dict[str, list[str]], cases: list[dict], repeats: int = REPEATS) -> dict:
    """Rates per underlying context (reported only)."""
    return _tally(preds, cases, lambda c: c["family"], repeats)


def decide(llm: dict, jev: dict) -> dict:
    """The rule fixed before the run. For every gated group, in each shape it
    has (single message, conversation), Jev's rate is no more than the
    tolerance below the LLM's. The tolerance is TOLERANCE or one case in that
    cell, whichever is larger, since a cell of eight cases cannot resolve 0.07."""
    detail = {}
    for cell in sorted(set(llm) | set(jev)):
        if cell.split("/")[0] not in GATED:
            continue
        l, j = llm.get(cell, {}), jev.get(cell, {})
        lr, jr = l.get("rate"), j.get("rate")
        n = max(l.get("cases", 0), j.get("cases", 0))
        tol = max(TOLERANCE, 1 / n) if n else TOLERANCE
        detail[cell] = {"llm": lr, "jev": jr, "tolerance": round(tol, 3),
                        "met": lr is not None and jr is not None and jr >= lr - tol}
    matches = bool(detail) and all(d["met"] for d in detail.values())
    return {"matches_current": matches, "detail": detail,
            "reading": "Jev matches the current classifier" if matches
            else "Jev does not match the current classifier"}


def summarize() -> dict:
    dev, test = dev_cases(), test_cases()
    report: dict = {"cases": {"dev": len(dev), "test": len(test),
                              "test_conversations": sum(c["shape"] == "conversation" for c in test)}}
    llm_rows = (OUT / "llm.json")
    if llm_rows.exists():
        data = json.loads(llm_rows.read_text())
        preds: dict = defaultdict(list)
        for r in data["rows"]:
            if "output" in r:
                preds[r["id"]].append(r["output"]["action"])
        report["llm"] = {"dev": g.score(preds, dev)["balanced"],
                         "test": group_rates(preds, test, data["repeats"]),
                         "by_family": family_rates(preds, test, data["repeats"])}
    answers = {arm: _answers(arm) for arm in JEV_ARMS}
    answers = {k: v for k, v in answers.items() if v}
    if answers:
        reps = json.loads((OUT / f"{JEV_ARMS[0]}.json").read_text())["repeats"] \
            if (OUT / f"{JEV_ARMS[0]}.json").exists() else REPEATS
        choice = pick(answers, dev)
        jev_preds = predict(answers[choice["arm"]], test, choice["single"], choice["conversation"])
        report["jev"] = {**{k: v for k, v in choice.items() if k not in ("single", "conversation")},
                         "single_rule": choice["single"].name,
                         "conversation_rule": choice["conversation"].name if choice["conversation"] else None,
                         "test": group_rates(jev_preds, test, reps),
                         "by_family": family_rates(jev_preds, test, reps)}
        # The state change alone: each arm's own best shared rule, on test (reported, not decisive).
        report["jev_by_state"] = {}
        for arm, ans in answers.items():
            best = max(rules(), key=lambda r: g.score(predict(ans, dev, r), dev)["balanced"])
            report["jev_by_state"][arm] = {"rule": best.name,
                                           "test": group_rates(predict(ans, test, best), test, reps)}
        if "llm" in report:
            report["decision"] = decide(report["llm"]["test"], report["jev"]["test"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g41_eval")
    ap.add_argument("--record", action="store_true", help="record and freeze the conversation histories")
    ap.add_argument("--arm", choices=("llm", "jev"))
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args(argv)
    if args.record:
        asyncio.run(record(args.concurrency))
    if args.arm:
        asyncio.run(run_arm(args.arm, args.repeats, args.concurrency))
    if args.summarize:
        print(json.dumps(summarize(), indent=2))


if __name__ == "__main__":
    main()
