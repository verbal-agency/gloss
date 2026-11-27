"""E9 (dev only): narrower questions after E7. Spec: docs/e9_redesign_goal.md.

    python -m eval.e9_dev --run       # E9's three questions on every dev case, three repeats
    python -m eval.e9_dev --score     # each change alone and together, Jev alone and with the fallback band

The three questions go in a request of their own. Their answers are merged
with E7's dev answers (results/e7/jev_dev.json, with E7's moved question),
repeat i with repeat i, so E7's own answers are reused unchanged. Every
response's `model` field is stored, and the run stops if the version changes
from E7's dev run's alias resolution to something else mid-run.

Dev only: G43 and G44 are spent, and the next held-out set is written before
any tuning on E9.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from app.config import settings
from app.pipeline import jev_ground as jg
from eval import e7_dev as d
from eval import g43_eval as ge

OUT = Path("results/e9")
ROWS = OUT / "jev_dev.json"
BANDS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3)
UTILITY_MARGIN = 0.02          # parity: E7's decision rule, on dev
APPROVED: str | None = None    # the date the owner approved the three wordings; None refuses the run


async def ask(st: str, conversation: bool, repeat: int, release: str) -> dict:
    from eval import cache
    questions = jg.e9_battery(conversation)
    return await cache.get_or_run(
        "ground_jev_e9", {"model": settings.jev_model, "release": release, "battery": questions,
                          "state": st, "repeat": repeat},
        lambda: jg.ask_jev_full(st, questions))


async def run(concurrency: int) -> None:
    if APPROVED is None:
        raise SystemExit("the owner approves E9's wordings first (APPROVED)")
    if ROWS.exists():
        raise SystemExit(f"{ROWS} exists")
    model = d._require_model()
    release = await d._release_checked()           # E7's dev release, unchanged
    cases = d.unique_cases(d.dev_sets())
    jobs = [(c["id"], r, lambda c=c, r=r: ask(d.state(c), c["shape"] == "conversation", r,
                                               release["release_date"]))
            for c in cases for r in range(1, d.REPEATS + 1)]
    rows = await d._gather(jobs, concurrency)
    versions = Counter(r["output"].get("model") for r in rows if "output" in r)
    OUT.mkdir(parents=True, exist_ok=True)
    ROWS.write_text(json.dumps({"arm": "e9", "model": model, "release": release, "approved": APPROVED,
                                "versions": dict(versions), "repeats": d.REPEATS, "rows": rows}, indent=2))
    print(f"[e9] {sum('output' in r for r in rows)} answered, {sum('error' in r for r in rows)} failed; "
          f"versions {dict(versions)}")
    if len(versions) > 1:
        raise SystemExit(f"more than one Jev version answered: {dict(versions)}. Stop and ask the owner.")


def merged_answers() -> dict[str, list[dict]]:
    """E7's dev answers with E9's three merged in, repeat i with repeat i."""
    e7 = d.jev_answers()
    e9: dict = {}
    for r in sorted(json.loads(ROWS.read_text())["rows"], key=lambda r: r["repeat"]):
        if "output" in r:
            e9.setdefault(r["id"], []).append(r["output"]["answers"])
    return merge(e7, e9)


def merge(e7: dict, e9: dict) -> dict[str, list[dict]]:
    out = {}
    for cid, reps in e7.items():
        extra = e9.get(cid, [])
        out[cid] = [{**a, **extra[i]} for i, a in enumerate(reps) if i < len(extra)]
    return out


def predictions(ans: dict, cases: list[dict], changes: str, band: float, llm: dict) -> tuple[dict, float]:
    """Each case's actions under `changes`, with decisions inside `band` given to the LLM."""
    preds, fell, total = {}, 0, 0
    for c in cases:
        conv = c["shape"] == "conversation"
        out = []
        for i, a in enumerate(ans.get(c["id"], [])):
            _, act, margin = jg.e9_decide(a, changes, ge.E7_CONFIG, conv)
            total += 1
            if margin < band:
                fell += 1
                ls = llm.get(c["id"], [])
                act = ls[i] if i < len(ls) else "none"
            out.append(act)
        preds[c["id"]] = out
    return preds, (fell / total if total else 0.0)


def score() -> dict:
    sets = d.dev_sets()
    ans = merged_answers()
    llm = d.llm_predictions(sets)
    labelled = [c for n in d.LABELLED for c in sets[n]]
    llm_cells = d.rates(llm, labelled)
    llm_u = d.weighted_utility(llm, sets["spent"], d.spent_p_wrong)
    report: dict = {"llm_utility": llm_u, "config": ge.E7_CONFIG.name, "variants": {}}
    for name, changes in jg.E9_VARIANTS.items():
        curve = []
        for band in BANDS:
            preds, rate = predictions(ans, labelled, changes, band, llm)
            s = d.score(preds, llm_cells, labelled, sets["spent"])
            parity = s["cells_within"] == s["cells"] and s["utility"] >= llm_u - UTILITY_MARGIN - d.EPS
            curve.append({"band": band, "fallback_rate": round(rate, 3), "cells_within": s["cells_within"],
                          "cells": s["cells"], "utility": s["utility"], "parity": parity,
                          "misses": [k for k, v in s["detail"].items() if not v["met"]]})
        first = next((r for r in curve if r["parity"]), None)
        report["variants"][name] = {"changes": changes, "curve": curve,
                                    "parity_at": None if first is None else {"band": first["band"],
                                                                             "fallback_rate": first["fallback_rate"]}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary_dev.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    from eval import cache

    ap = argparse.ArgumentParser(prog="python -m eval.e9_dev")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args(argv)
    cache.configure(enabled=True)
    if args.run:
        asyncio.run(run(args.concurrency))
    if args.score:
        r = score()
        print(f"LLM utility {r['llm_utility']}")
        for name, v in r["variants"].items():
            alone = v["curve"][0]
            print(f"{name:4s} alone: cells {alone['cells_within']}/{alone['cells']}, utility {alone['utility']}; "
                  f"parity at {v['parity_at']}")


if __name__ == "__main__":
    main()
