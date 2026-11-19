"""G40: can Jev replace the grounding check's LLM classifier?

Scores the classifier alone, not the answer. Each case is exactly what the
classifier sees in the pipeline (the message, or for a late turn the
conversation view built from the frozen histories), and the expected action is
the one the scenario calls for:

  objected  a full proposal whose own facts contradict the plan (mismatch,
            infeasible), a late_flawed turn
  asked     a bare fix (wrong_fix, right_fix), a late_absent turn
  none      a sound full proposal, a bare diagnose, a late_sound or
            late_answered turn

Classifier-level scoring is a fair proxy for the answer here: in G37b every
answer the note told to ask did ask and wait, so the classifier's action is
what the user sees.

Split, fixed before Jev is run (see docs/v3_spike.md, G40):
  dev   the full and bare proposals and the main multi-turn set: the set the
        LLM classifier was written against, used to pick Jev's thresholds.
  test  the held-out multi-turn set (G37b), used once, to decide.

Usage:
    python -m eval.ground_classifier_eval --arm llm            # current classifier
    python -m eval.ground_classifier_eval --arm jev            # needs TYPESAFE_API_KEY
    python -m eval.ground_classifier_eval --summarize
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
from eval import cache
from eval import multiturn_dataset as mt
from eval import multiturn_heldout as mh
from eval import proposals_dataset as pd

load_dotenv()

OUT = Path("results/ground-classifier")
REPEATS = 3
ACTIONS = ("asked", "objected", "none")

# Fixed before the Jev run. Held-out late turns: Jev matches the current
# classifier if, averaged over the repeats, its quiet rate on sound turns and
# its ask rate on no-evidence turns are each no more than one conversation
# (1/14) below the LLM classifier's.
MATCH_TOLERANCE = 1 / 14
# The classifier model the G36-G37b results were measured with. Named here, not
# taken from .env, so the baseline is the classifier those results describe.
LLM_GROUND_MODEL = "anthropic/claude-sonnet-5-5"
# Threshold grid searched on dev for the yes/no rules.
GRID = {"fix": (0.3, 0.5, 0.7), "cause": (0.3, 0.5, 0.7), "contra": (0.3, 0.5, 0.7, 0.9)}

_MT_EXPECTED = {"late_absent": "asked", "late_flawed": "objected",
                "late_sound": "none", "late_answered": "none"}
_BARE_EXPECTED = {"wrong_fix": "asked", "right_fix": "asked", "diagnose": "none"}


# --------------------------------------------------------------------------- cases

def _late_cases(convs, hist_path: Path, split: str, group: str) -> list[dict]:
    if not hist_path.exists():
        raise SystemExit(f"{hist_path} missing: record the multi-turn histories first")
    histories = json.loads(hist_path.read_text())["histories"]
    out = []
    for c in convs:
        h = histories.get(c.id)
        if not h or not h["survived"]:
            continue  # the late turn was never reached: nothing to classify
        messages = c.messages(h["replies"])
        out.append({"id": c.id, "split": split, "group": group, "scenario": c.scenario,
                    "expected": _MT_EXPECTED[c.scenario], "query": messages[-1]["content"],
                    "context": assumptions.conversation_view(messages), "messages": messages})
    return out


def cases() -> list[dict]:
    out = []
    for p in pd.load():
        out.append({"id": f"full/{p.id}", "split": "dev", "group": "proposals_full",
                    "scenario": p.kind, "expected": "none" if p.kind == "sound" else "objected",
                    "query": pd.prompts(p)["owned_build"], "context": None,
                    "messages": [{"role": "user", "content": pd.prompts(p)["owned_build"]}]})
    for b in pd.bare_items():
        out.append({"id": f"bare/{b['id']}", "split": "dev", "group": "proposals_bare",
                    "scenario": b["bare_kind"], "expected": _BARE_EXPECTED[b["bare_kind"]],
                    "query": b["prompt"], "context": None,
                    "messages": [{"role": "user", "content": b["prompt"]}]})
    out += _late_cases(mt.load(), Path("results/multiturn/late_histories.json"), "dev", "multiturn_main")
    out += _late_cases(mh.load(), Path("results/multiturn-heldout/late_histories.json"), "test",
                       "multiturn_heldout")
    return out


# --------------------------------------------------------------------------- arms

async def classify_llm(case: dict, repeat: int) -> dict:
    model = LLM_GROUND_MODEL
    system = assumptions.GROUND_SYSTEM + (assumptions.CONVERSATION_RULE if case["context"] else "")
    return await cache.get_or_run(
        "ground_llm", {"model": model, "system": system, "query": case["query"],
                       "context": case["context"], "repeat": repeat},
        lambda: _llm(case, model))


async def _llm(case: dict, model: str) -> dict:
    r = await assumptions.classify_grounding(case["query"], model=model, context=case["context"])
    return {**r.model_dump(), "action": r.action}


async def classify_jev(case: dict, repeat: int) -> dict:
    conversation = case["context"] is not None
    return await cache.get_or_run(
        "ground_jev", {"model": settings.jev_model, "battery": jev_ground.battery(conversation),
                       "state": case["context"] or case["query"], "repeat": repeat},
        lambda: jev_ground.ask_jev(case["context"] or case["query"], conversation))


async def run_arm(arm: str, repeats: int, concurrency: int) -> None:
    fn = {"llm": classify_llm, "jev": classify_jev}[arm]
    sem = asyncio.Semaphore(concurrency)
    all_cases = cases()

    async def one(case, rep):
        async with sem:
            try:
                return {"id": case["id"], "repeat": rep, "output": await fn(case, rep)}
            except Exception as e:  # recorded, not fatal: a failed call is reported as failed
                return {"id": case["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(c, r) for c in all_cases for r in range(1, repeats + 1)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{arm}.json").write_text(json.dumps(
        {"arm": arm, "model": settings.jev_model if arm == "jev"
         else LLM_GROUND_MODEL,
         "repeats": repeats, "rows": rows}, indent=2))
    failed = sum("error" in r for r in rows)
    print(f"[{arm}] {len(rows) - failed} classified, {failed} failed. {cache.report()}")


# --------------------------------------------------------------------------- scoring

def rules() -> list[jev_ground.Rule]:
    out = []
    for noul in ("cause_stated", "evidence_beyond_plan"):
        for f, c, x in itertools.product(GRID["fix"], GRID["cause"], GRID["contra"]):
            out.append(jev_ground.Rule(fix=f, cause=c, contra=x, cause_noul=noul))
    return out


def jev_actions(answers: dict) -> dict[str, str]:
    """Every way of turning one Jev answer into an action, keyed by name."""
    acts = {"jev_choice": jev_ground.choice_action(answers)}
    for rule in rules():
        acts[rule.name] = jev_ground.route(answers, rule)
    # Combinations of the two question forms (decision by agreement).
    base = jev_ground.route(answers, jev_ground.DEFAULT_RULE)
    choice = acts["jev_choice"]
    acts["jev_both_ask"] = ("objected" if "objected" in (choice, base) else
                            "asked" if choice == base == "asked" else "none")
    acts["jev_either_ask"] = ("objected" if choice == base == "objected" else
                              "asked" if "asked" in (choice, base) else "none")
    return acts


def score(predictions: dict[str, list[str]], case_list: list[dict]) -> dict:
    """Per expected action: how many predictions matched, over cases x repeats.
    `balanced` is the mean of the per-action rates (each action counts equally)."""
    by_action: dict = defaultdict(lambda: [0, 0])
    by_group: dict = defaultdict(lambda: [0, 0])
    for c in case_list:
        for got in predictions.get(c["id"], []):
            hit = got == c["expected"]
            by_action[c["expected"]][0] += hit
            by_action[c["expected"]][1] += 1
            key = f"{c['group']}/{c['scenario']}"
            by_group[key][0] += hit
            by_group[key][1] += 1
    rates = {a: round(h / n, 3) for a, (h, n) in by_action.items() if n}
    return {"per_action": {a: {"hit": h, "n": n, "rate": rates[a]} for a, (h, n) in by_action.items()},
            "per_group": {g: f"{h}/{n}" for g, (h, n) in sorted(by_group.items())},
            "balanced": round(sum(rates.values()) / len(rates), 3) if rates else None}


def _load(arm: str) -> dict | None:
    path = OUT / f"{arm}.json"
    return json.loads(path.read_text()) if path.exists() else None


def summarize() -> dict:
    all_cases = cases()
    dev = [c for c in all_cases if c["split"] == "dev"]
    test = [c for c in all_cases if c["split"] == "test"]
    report: dict = {"cases": {"dev": len(dev), "test": len(test)}, "arms": {}}

    llm = _load("llm")
    if llm:
        preds: dict = defaultdict(list)
        for r in llm["rows"]:
            if "output" in r:
                preds[r["id"]].append(r["output"]["action"])
        report["arms"]["llm"] = {"dev": score(preds, dev), "test": score(preds, test),
                                 "failed": sum("error" in r for r in llm["rows"])}

    jev = _load("jev")
    if jev:
        variants: dict = defaultdict(lambda: defaultdict(list))
        for r in jev["rows"]:
            if "output" in r:
                for name, act in jev_actions(r["output"]).items():
                    variants[name][r["id"]].append(act)
        dev_scores = {name: score(p, dev)["balanced"] for name, p in variants.items()}
        standard = [n for n in variants if "evidence_beyond_plan" not in n]
        # Picked on dev only. Ties go to the earlier (simpler) variant in insertion order.
        pick = max(standard, key=lambda n: dev_scores[n])
        pick_changed = max(variants, key=lambda n: dev_scores[n])
        report["arms"]["jev"] = {
            "failed": sum("error" in r for r in jev["rows"]),
            "dev_balanced": {n: dev_scores[n] for n in ("jev_choice", "jev_both_ask", "jev_either_ask",
                                                        jev_ground.DEFAULT_RULE.name)},
            "picked_on_dev": pick,
            "picked": {"dev": score(variants[pick], dev), "test": score(variants[pick], test)},
            "choice": {"dev": score(variants["jev_choice"], dev),
                       "test": score(variants["jev_choice"], test)},
            "standard_changed_best": {"name": pick_changed,
                                      "dev": score(variants[pick_changed], dev),
                                      "test": score(variants[pick_changed], test)},
        }
        if llm:
            report["decision"] = decide(report["arms"]["llm"]["test"], report["arms"]["jev"]["picked"]["test"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(report, indent=2))
    return report


def decide(llm_test: dict, jev_test: dict) -> dict:
    """The rule fixed before the Jev run, on the held-out late turns."""
    def rate(s, a):
        return s["per_action"].get(a, {}).get("rate")
    out = {}
    for action, label in (("none", "quiet on sound"), ("asked", "asks on no evidence")):
        l, j = rate(llm_test, action), rate(jev_test, action)
        out[label] = {"llm": l, "jev": j, "met": j is not None and l is not None
                      and j >= l - MATCH_TOLERANCE}
    matches = all(v["met"] for v in out.values())
    return {"matches_current": matches, "detail": out,
            "reading": "Jev matches the current classifier" if matches else
            "Jev does not match the current classifier"}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.ground_classifier_eval")
    ap.add_argument("--arm", choices=("llm", "jev"))
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args(argv)
    if args.arm:
        asyncio.run(run_arm(args.arm, args.repeats, args.concurrency))
    if args.summarize or not args.arm:
        print(json.dumps(summarize(), indent=2))


if __name__ == "__main__":
    main()
