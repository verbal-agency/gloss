"""E5 on spent data: one critical question per kind of doubt, and a decision table.

Plan fixed before the run: docs/v3_spike.md, "Next experiments" and "E5 details".

    python -m eval.e5_critical --run e5
    python -m eval.e5_critical --run e5b
    python -m eval.e5_critical --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.pipeline import jev_ground as jg
from eval import g43_explore as x
from eval import g43_explore2 as y
from eval import g43_explore3 as z
from eval import g43_explore4 as w

OUT = x.OUT
REPEATS = x.REPEATS


async def run(concurrency: int, variant: str = "e5") -> None:
    cases = x.pool()
    battery = jg.e5_battery if variant == "e5" else jg.e5b_battery
    sem = asyncio.Semaphore(concurrency)

    async def one(c, rep):
        conv = c["shape"] == "conversation"
        async with sem:
            try:
                out = await x._ask(f"ground_jev_{variant}", x.state(c, False), battery(conv), rep)
                return {"arm": variant, "id": c["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": variant, "id": c["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(c, r) for c in cases for r in range(1, REPEATS + 1)))
    (OUT / f"{variant}.json").write_text(json.dumps({"arm": variant, "repeats": REPEATS, "rows": rows}, indent=2))
    print(f"[{variant}] {sum('output' in r for r in rows)} answered, {sum('error' in r for r in rows)} failed")


def summarize() -> dict:
    cases = x.pool()
    e5 = x._load(OUT / "e5.json")
    ans4 = w.answers()
    llm = x.llm_preds(cases)
    flat = {c["id"]: z.UNIFORM_L for c in cases}
    pols = {"llm": llm,
            "D": y._preds(ans4, w.d, cases),
            "D@0.3": y._preds(ans4, lambda a: w.d(a, 0.3, 0.1), cases),
            "D+correct": y._preds(ans4, lambda a: w.d(a, correct=True), cases),
            "E5": {c["id"]: [jg.e5_action(a) for a in e5.get(c["id"], [])] for c in cases},
            "E5@0.3": {c["id"]: [jg.e5_action(a, 0.3) for a in e5.get(c["id"], [])] for c in cases}}
    e5b = x._load(OUT / "e5b.json")
    if e5b:
        pols["E5b"] = {c["id"]: [jg.e5b_action(a) for a in e5b.get(c["id"], [])] for c in cases}
    report = {"rates": {k: x.rates(p, cases) for k, p in pols.items()},
              "utility": {f"c=0.25 wrong={s}": {k: z.weighted_utility(p, cases, flat, 0.25, s) for k, p in pols.items()}
                          for s in z.WRONG_SHARES}}
    wrong = [c for c in cases if z.plan_wrong(c)]
    right = [c for c in cases if not z.plan_wrong(c)]
    auc = {}
    for q, f in (("achieves_goal (reversed)", lambda a: -a["achieves_goal"]["noul"]),
                 ("conflicts_constraint", lambda a: a["conflicts_constraint"]["noul"]),
                 ("link_stated", lambda a: a["link_stated"]["noul"]),
                 ("P(goal)", lambda a: 1 - a["goal_type"]["probabilities"]["neither"])):
        auc[q] = w._auc([f(a) for c in wrong for a in e5[c["id"]]], [f(a) for c in right for a in e5[c["id"]]])
    report["auc_wrong_vs_right"] = auc
    ask = [c for c in cases if x.group(c) == "ask"]
    quiet = [c for c in cases if x.group(c) in ("quiet", "answered")]
    report["auc_link_quiet_vs_ask"] = w._auc([a["link_stated"]["noul"] for c in quiet for a in e5[c["id"]]],
                                             [a["link_stated"]["noul"] for c in ask for a in e5[c["id"]]])
    from collections import Counter
    report["goal_type_by_group"] = {g: dict(Counter(a["goal_type"]["choice"] for c in cases if x.group(c) == g
                                                    for a in e5[c["id"]]))
                                    for g in ("quiet", "ask", "object", "task", "answered")}
    report["mis-02"] = [jg.e5_action(a) for a in e5["full/mis-02"]]
    (OUT / "summary_e5.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.e5_critical")
    ap.add_argument("--run", choices=("e5", "e5b"))
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args(argv)
    if args.run:
        asyncio.run(run(args.concurrency, args.run))
    if args.summarize:
        print(json.dumps(summarize(), indent=2))


if __name__ == "__main__":
    main()
