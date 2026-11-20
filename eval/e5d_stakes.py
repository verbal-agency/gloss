"""E5d on dev data: can Jev tell a costly plan from a cheap one?

Plan fixed before the run: docs/v3_spike.md, "E5d".

    python -m eval.e5d_stakes --run
    python -m eval.e5d_stakes --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.pipeline import jev_ground as jg
from eval import g43_explore as x
from eval import g43_explore4 as w
from eval import stakes_dev as sd

OUT = x.OUT
REPEATS = x.REPEATS


async def run(concurrency: int) -> None:
    cases = sd.cases()
    sem = asyncio.Semaphore(concurrency)

    async def one(c, rep):
        async with sem:
            try:
                out = await x._ask("ground_jev_e5d", c["query"], jg.e5d_battery(False), rep)
                return {"arm": "e5d", "id": c["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": "e5d", "id": c["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(c, r) for c in cases for r in range(1, REPEATS + 1)))
    (OUT / "e5d.json").write_text(json.dumps({"arm": "e5d", "repeats": REPEATS, "rows": rows}, indent=2))
    print(f"[e5d] {sum('output' in r for r in rows)} answered, {sum('error' in r for r in rows)} failed")


def summarize() -> dict:
    ans = x._load(OUT / "e5d.json")
    cases = sd.cases()
    paired = [c for c in cases if c["id"].startswith(sd.TAG)]
    extra = [c for c in cases if not c["id"].startswith(sd.TAG)]
    costly = [c for c in cases if c["cost"] == "costly"]
    cheap = [c for c in cases if c["cost"] == "cheap"]

    def vals(cs, f):
        return [f(a) for c in cs for a in ans.get(c["id"], [])]

    sig = {"1 - plan_reversible": lambda a: 1 - a["plan_reversible"]["noul"],
           "plan_large": lambda a: a["plan_large"]["noul"],
           "plan_scope expected cost": lambda a: sum(jg.PLAN_SCOPE_COST[k] * v
                                                     for k, v in a["plan_scope"]["probabilities"].items())}
    report: dict = {"auc_costly_vs_cheap": {k: w._auc(vals(costly, f), vals(cheap, f)) for k, f in sig.items()}}
    per_repeat_correct = []
    for r in range(REPEATS):
        per_repeat_correct.append(sum(jg.plan_costly(ans[c["id"]][r]) == (c["cost"] == "costly") for c in paired))
    tricky_ok = all(jg.plan_costly(a) == (c["cost"] == "costly") for c in paired if c["tricky"] for a in ans[c["id"]])
    extra_costly = [sum(jg.plan_costly(ans[c["id"]][r]) for c in extra) for r in range(REPEATS)]
    report["paired_correct_per_repeat"] = per_repeat_correct
    report["tricky_all_right"] = tricky_ok
    report["cheap_extra_called_costly_per_repeat"] = extra_costly
    report["passes"] = (min(per_repeat_correct) >= 18 and tricky_ok and max(extra_costly) <= 3)
    report["paired_detail"] = {c["id"]: {"rev": [round(a["plan_reversible"]["noul"], 2) for a in ans[c["id"]]],
                                         "large": [round(a["plan_large"]["noul"], 2) for a in ans[c["id"]]],
                                         "costly": [jg.plan_costly(a) for a in ans[c["id"]]]} for c in paired}
    (OUT / "summary_e5d.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.e5d_stakes")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args(argv)
    if args.run:
        asyncio.run(run(args.concurrency))
    if args.summarize:
        print(json.dumps(summarize(), indent=2))


if __name__ == "__main__":
    main()
