"""G42: narrower cause questions, examples in the criteria, and objection only
with a stated cause, aimed at G41's misses.

Spec and rule: docs/v3_spike.md, G42 (fixed before any run). In short:

  dev   G40's 105 cases plus G41's 70 test cases (now spent), used to pick one
        Jev setup: which arm, which rule, shared or per-shape thresholds.
  test  eval/g42_heldout.py: 38 single messages and the conversations whose
        frozen earlier turns survive. Used once. Scored per group and per
        shape, against the LLM classifier, with G41's decision rule; a failed
        classification is a miss.

Order (each step refuses to run before the one it depends on):
    python -m eval.g42_eval --record      # histories, after the owner's review
    python -m eval.g42_eval --arm llm
    python -m eval.g42_eval --arm jev      # both Jev arms; needs TYPESAFE_API_KEY
    python -m eval.g42_eval --summarize
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
from app.pipeline import jev_ground
from app.pipeline.jev_ground import G41Rule, G42Rule
from eval import g41_eval as g41
from eval import g42_heldout as h
from eval import ground_classifier_eval as g

load_dotenv()

OUT = Path("results/g42")
HISTORIES = OUT / "late_histories.json"
REPEATS = 3
# arm -> whether the battery tells Jev to ignore how sure the user sounds
JEV_ARMS = {"jev_g42": True, "jev_g42_plain": False}
# G41's pick, applied to G42's test set for comparison (reported only).
G41_PICK = G41Rule(family="link", gate="problem_described", gate_t=0.3, cause_t=0.2, contra_t=0.3)


# --------------------------------------------------------------------------- cases

def dev_cases() -> list[dict]:
    g41_test = g41.held_out_cases(g41.h.single_cases(), g41.h.load(), g41.HISTORIES, split="dev")
    return g41.dev_cases() + [{**c, "group": "g41_heldout"} for c in g41_test]


def test_cases() -> list[dict]:
    return g41.held_out_cases(h.single_cases(), h.load(), HISTORIES)


def _guard() -> None:
    if h.REVIEW != "owner-checked":
        raise SystemExit("eval/g42_heldout.py is not owner-checked: no run before the review")


# --------------------------------------------------------------------------- runs

async def record(concurrency: int) -> None:
    _guard()
    await g41.record_histories(h.load(), HISTORIES, concurrency)


async def classify_jev(case: dict, ignore_confidence: bool, repeat: int) -> dict:
    from eval import cache
    conversation = case["context"] is not None
    state = case["context"] or case["query"]
    return await cache.get_or_run(
        "ground_jev_g42", {"model": settings.jev_model,
                           "battery": jev_ground.g42_battery(conversation, ignore_confidence),
                           "state": state, "repeat": repeat},
        lambda: jev_ground.ask_jev_g42(state, conversation, ignore_confidence))


async def run_arm(arm: str, repeats: int, concurrency: int) -> None:
    _guard()
    if not HISTORIES.exists():
        raise SystemExit("record the histories first (--record)")
    # The LLM's dev answers are cached from G40 and G41; only the test set is new.
    cases = dev_cases() + test_cases()
    sem = asyncio.Semaphore(concurrency)
    jobs = [("llm", None)] if arm == "llm" else list(JEV_ARMS.items())

    async def one(name, ignore, case, rep):
        async with sem:
            try:
                out = (await g.classify_llm(case, rep) if ignore is None
                       else await classify_jev(case, ignore, rep))
                return {"arm": name, "id": case["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": name, "id": case["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(n, i, c, r) for n, i in jobs for c in cases
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

EVIDENCE = (("cause_stated",), ("mechanism_stated",), ("cause_outside_plan",),
            ("mechanism_stated", "cause_outside_plan"), ("cause_stated", "cause_outside_plan"))


def rules() -> list[G42Rule]:
    """Every rule searched on dev."""
    evidence = [(("link",), t) for t in (0.2, 0.3, 0.4, 0.5)]
    evidence += [(e, t) for e in EVIDENCE for t in (0.3, 0.5, 0.7)]
    gates = [(None, 0.0)] + [("problem_described", t) for t in (0.3, 0.5, 0.7)]
    return [G42Rule(evidence=e, ev_t=et, gate=ga, gate_t=gt, contra_t=ct, contra_needs_evidence=ne)
            for (e, et), (ga, gt), ct, ne in itertools.product(evidence, gates, (0.3, 0.5, 0.7, 0.9),
                                                               (False, True))]


def _answers(arm: str) -> tuple[dict, int]:
    path = OUT / f"{arm}.json"
    if not path.exists():
        return {}, REPEATS
    data = json.loads(path.read_text())
    out: dict = defaultdict(list)
    for r in data["rows"]:
        if "output" in r:
            out[r["id"]].append(r["output"])
    return out, data["repeats"]


def pattern_rates(preds: dict, cases: list[dict], repeats: int) -> dict:
    """No-evidence cases by G41 miss pattern (reported only)."""
    absent = [c for c in cases if c["scenario"] in ("absent", "late_absent")]
    fam = {k: v for k, v in h.PATTERN.items()}
    return g41._tally(preds, absent, lambda c: f"{fam[c['family']]}/{c['shape']}", repeats)


def summarize() -> dict:
    dev, test = dev_cases(), test_cases()
    report: dict = {"cases": {"dev": len(dev), "test": len(test),
                              "test_conversations": sum(c["shape"] == "conversation" for c in test)}}
    llm_path = OUT / "llm.json"
    if llm_path.exists():
        data = json.loads(llm_path.read_text())
        preds: dict = defaultdict(list)
        for r in data["rows"]:
            if "output" in r:
                preds[r["id"]].append(r["output"]["action"])
        report["llm"] = {"dev": g.score(preds, dev)["balanced"],
                         "test": g41.group_rates(preds, test, data["repeats"]),
                         "by_pattern": pattern_rates(preds, test, data["repeats"]),
                         "by_family": g41.family_rates(preds, test, data["repeats"])}
    loaded = {arm: _answers(arm) for arm in JEV_ARMS}
    answers = {arm: a for arm, (a, _) in loaded.items() if a}
    if answers:
        reps = next(r for a, r in loaded.values() if a)
        candidates = rules()
        choice = g41.pick(answers, dev, candidates, jev_ground.g42_action)
        jev_preds = g41.predict(answers[choice["arm"]], test, choice["single"], choice["conversation"],
                                jev_ground.g42_action)
        report["jev"] = {**{k: v for k, v in choice.items() if k not in ("single", "conversation")},
                         "single_rule": choice["single"].name,
                         "conversation_rule": choice["conversation"].name if choice["conversation"] else None,
                         "test": g41.group_rates(jev_preds, test, reps),
                         "by_pattern": pattern_rates(jev_preds, test, reps),
                         "by_family": g41.family_rates(jev_preds, test, reps)}
        if "jev_g42_plain" in answers:
            # G41's pick on the same answers: what G42's changes add (reported only).
            old = g41.predict(answers["jev_g42_plain"], test, G41_PICK)
            report["g41_pick_on_g42_test"] = {"test": g41.group_rates(old, test, reps),
                                              "by_pattern": pattern_rates(old, test, reps)}
        if "llm" in report:
            report["decision"] = g41.decide(report["llm"]["test"], report["jev"]["test"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g42_eval")
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
