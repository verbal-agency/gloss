"""E7h (exploratory, 2026-11-27): E7's candidate with an LLM fallback. No new calls.

A decision goes to the LLM classifier when any score the E7 table checked on the
way to its row is within BAND of that score's threshold (its margin). Everything
is replayed from answers E7 already recorded: the LLM's answer for the same case
and repeat stands in for the fallback call.

    python -m eval.e7_hybrid --dev        # the fallback curve and the margins of the misses, on dev
    python -m eval.e7_hybrid --heldout    # BAND, fixed on dev, on E7's saved held-out answers

G43 and G44 were spent by E7 on 2026-11-26, and their misses had been looked
at before BAND was fixed. So the held-out figures are a second look, not a
held-out result. A clean test needs a new held-out set. Output names rates only.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.pipeline import jev_ground as jg
from eval import e7_dev as d
from eval import g41_eval as g41
from eval import g43_eval as ge

OUT = Path("results/e7")
BANDS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3)
BAND = 0.10   # 2026-11-27: the smallest band in BANDS with every dev cell within tolerance, fixed before --heldout


def decide(a: dict, cfg: jg.E7Config, conversation: bool) -> tuple[int, str, float]:
    """E7's table (jg.e7_row) with its margin: the smallest |score - threshold|
    among the scores it checked on the way to its row."""
    def p(q):
        return a[q]["noul"]

    seen: list[float] = []

    def chk(q, t):
        seen.append(abs(p(q) - t))
        return p(q)

    t_ach = cfg.t_ach_conv if conversation else jg.E7_ACH_SINGLE_T
    if chk("investigation", jg.E7_INVESTIGATION_T) >= jg.E7_INVESTIGATION_T:
        return 1, "none", min(seen)
    if chk("conflicts_constraint", jg.E7_CONFLICT_T) >= jg.E7_CONFLICT_T:
        return 2, "objected", min(seen)
    if chk("problem_described", jg.E7_PROBLEM_T) < jg.E7_PROBLEM_T:
        return 3, ("objected" if chk("achieves_goal", t_ach) < t_ach else "none"), min(seen)
    fa, ro = chk("facts_against_cause", cfg.t_fa), chk("plan_ruled_out", cfg.t_ro)
    if fa >= cfg.t_fa or ro >= cfg.t_ro:
        return 4, ("objected" if ro >= cfg.t_ro else "asked"), min(seen)
    if chk("evidence_for_cause", cfg.t_ev) >= cfg.t_ev:
        return 5, ("objected" if chk("achieves_goal", t_ach) < t_ach else "none"), min(seen)
    if chk("link_stated", cfg.t_link) >= cfg.t_link:
        chk("plan_reversible", 0.5)
        chk("plan_large", 0.5)
        return 6, ("objected" if jg.plan_costly(a) else "none"), min(seen)
    return 7, "asked", min(seen)


def hybrid(jev: dict, llm_by_repeat: dict, cases: list[dict], band: float) -> tuple[dict, float]:
    """Per case, Jev's action or, inside the band, the LLM's for the same repeat
    (a failed LLM call counts as `none`). Returns the predictions and the share sent to the LLM."""
    preds, fell, total = {}, 0, 0
    for c in cases:
        conv = c["shape"] == "conversation"
        out = []
        for i, a in enumerate(jev.get(c["id"], [])):
            _, act, margin = decide(a, ge.E7_CONFIG, conv)
            total += 1
            if margin < band:
                fell += 1
                act = llm_by_repeat.get(c["id"], {}).get(i) or "none"
            out.append(act)
        preds[c["id"]] = out
    return preds, (fell / total if total else 0.0)


def _by_repeat(preds: dict[str, list[str]]) -> dict[str, dict[int, str]]:
    return {cid: dict(enumerate(acts)) for cid, acts in preds.items()}


def run_dev() -> dict:
    sets = d.dev_sets()
    ans = d.jev_answers()
    llm = d.llm_predictions(sets)
    labelled = [c for n in d.LABELLED for c in sets[n]]
    llm_cells = d.rates(llm, labelled)
    curve = []
    for band in BANDS:
        preds, rate = hybrid(ans, _by_repeat(llm), labelled, band)
        s = d.score(preds, llm_cells, labelled, sets["spent"])
        curve.append({"band": band, "fallback_rate": round(rate, 3), "cells_within": s["cells_within"],
                      "cells": s["cells"], "utility": s["utility"],
                      "misses": [k for k, v in s["detail"].items() if not v["met"]]})
    by: dict = defaultdict(lambda: {"right": [], "wrong": []})
    for c in labelled:
        for a in ans.get(c["id"], []):
            row, act, m = decide(a, ge.E7_CONFIG, c["shape"] == "conversation")
            by[row]["right" if act == c["expected"] else "wrong"].append(m)

    def within(xs, t):
        return round(sum(x < t for x in xs) / len(xs), 2) if xs else None

    margins = {f"row {r}": {"right": len(v["right"]), "wrong": len(v["wrong"]),
                            "wrong_within_0.1": within(v["wrong"], 0.1), "right_within_0.1": within(v["right"], 0.1),
                            "wrong_within_0.2": within(v["wrong"], 0.2), "right_within_0.2": within(v["right"], 0.2)}
               for r, v in sorted(by.items())}
    report = {"config": ge.E7_CONFIG.name, "llm_utility": d.weighted_utility(llm, sets["spent"], d.spent_p_wrong),
              "curve": curve, "margins": margins}
    _save("hybrid_dev.json", report)
    return report


def run_heldout() -> dict:
    cases = ge.e7_cases()
    jev = d._load_rows(ge.E7_ROWS["jev"])
    llm_rows = json.loads(ge.E7_ROWS["llm"].read_text())["rows"]
    llm_by_repeat: dict = defaultdict(dict)
    for r in llm_rows:
        llm_by_repeat[r["id"]][r["repeat"] - 1] = r["output"]["action"] if "output" in r else None
    llm = {cid: [o["action"] for o in outs] for cid, outs in d._load_rows(ge.E7_ROWS["llm"]).items()}
    plain = {c["id"]: [jg.e7_action(a, ge.E7_CONFIG, c["shape"] == "conversation") for a in jev.get(c["id"], [])]
             for c in cases}
    mixed, rate = hybrid(jev, llm_by_repeat, cases, BAND)
    arms = {"llm": llm, "jev": plain, "hybrid": mixed}
    cells = {k: g41._tally(v, cases, ge.e7_cell, d.REPEATS) for k, v in arms.items()}
    util = {k: d.weighted_utility(v, cases, ge.e7_p_wrong) for k, v in arms.items()}
    report = {"band": BAND, "fallback_rate": round(rate, 3), "utility": util,
              "jev": ge.e7_decide(cells["llm"], cells["jev"], util["llm"], util["jev"]),
              "hybrid": ge.e7_decide(cells["llm"], cells["hybrid"], util["llm"], util["hybrid"])}
    _save("hybrid_heldout.json", report)
    return report


def _save(name: str, report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(report, indent=2, default=str))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.e7_hybrid")
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--heldout", action="store_true")
    args = ap.parse_args(argv)
    if args.dev:
        r = run_dev()
        print(f"LLM utility {r['llm_utility']}")
        for row in r["curve"]:
            print(f"band {row['band']:.2f}: fallback {row['fallback_rate']:.3f}, cells {row['cells_within']}/"
                  f"{row['cells']}, utility {row['utility']}")
        for k, v in r["margins"].items():
            print(k, v)
    if args.heldout:
        r = run_heldout()
        print(f"band {r['band']}: fallback {r['fallback_rate']}, utility {r['utility']}")
        for arm in ("jev", "hybrid"):
            dec = r[arm]
            print(f"{arm}: utility met {dec['utility']['met']}, cells met {dec['cells_met']}")


if __name__ == "__main__":
    main()
