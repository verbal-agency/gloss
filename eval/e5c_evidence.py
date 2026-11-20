"""E5c on spent and dev data: does a question tell a claimed cause from evidence?

Plan fixed before the run: docs/v3_spike.md, "E5c".

    python -m eval.e5c_evidence --run
    python -m eval.e5c_evidence --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.pipeline import jev_ground as jg
from eval import evidence_dev as ev
from eval import g43_explore as x
from eval import g43_explore4 as w

OUT = x.OUT
REPEATS = x.REPEATS
FRENCH = ("g42/single/absent/french-tickets-fits", "g42/late_absent/french-tickets-fits",
          "g42/single/absent/french-tickets-misses")


def _state(c: dict) -> str:
    return c["query"] if c["shape"] == "single" else c["context"]


async def run(concurrency: int) -> None:
    cases = x.pool() + ev.cases()
    sem = asyncio.Semaphore(concurrency)

    async def one(c, rep):
        async with sem:
            try:
                out = await x._ask("ground_jev_e5c", _state(c), jg.e5c_battery(c["shape"] == "conversation"), rep)
                return {"arm": "e5c", "id": c["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": "e5c", "id": c["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(c, r) for c in cases for r in range(1, REPEATS + 1)))
    (OUT / "e5c.json").write_text(json.dumps({"arm": "e5c", "repeats": REPEATS, "rows": rows}, indent=2))
    print(f"[e5c] {sum('output' in r for r in rows)} answered, {sum('error' in r for r in rows)} failed")


def _vals(ans, cases, q):
    return [a[q]["noul"] for c in cases for a in ans.get(c["id"], [])]


def summarize() -> dict:
    ans = x._load(OUT / "e5c.json")
    dev = ev.cases()
    by = {v: [c for c in dev if c["variant"] == v] for v in ev.VARIANTS}
    implied = by["implied"] + by["symptom_measured"]
    qs = ("evidence_for_cause", "mechanism_stated", "cause_outside_plan", "cause_claimed")
    report: dict = {"dev_auc": {}, "dev_means": {}, "spent_auc_quiet_vs_ask": {}, "french": {}}
    for q in qs:
        report["dev_auc"][q] = {
            "evidenced vs asserted": w._auc(_vals(ans, by["evidenced"], q), _vals(ans, by["asserted"], q)),
            "evidenced vs implied": w._auc(_vals(ans, by["evidenced"], q), _vals(ans, implied, q)),
            "asserted vs implied": w._auc(_vals(ans, by["asserted"], q), _vals(ans, implied, q)),
            "evidenced vs symptom_measured": w._auc(_vals(ans, by["evidenced"], q), _vals(ans, by["symptom_measured"], q)),
        }
        report["dev_means"][q] = {v: round(sum(_vals(ans, by[v], q)) / len(_vals(ans, by[v], q)), 2)
                                  for v in ev.VARIANTS}
    pool = x.pool()
    quiet = [c for c in pool if x.group(c) in ("quiet", "answered")]
    ask = [c for c in pool if x.group(c) == "ask"]
    for q in qs[:3]:
        report["spent_auc_quiet_vs_ask"][q] = w._auc(_vals(ans, quiet, q), _vals(ans, ask, q))
    for cid in FRENCH:
        report["french"][cid] = {q: [round(a[q]["noul"], 2) for a in ans[cid]] for q in qs[:2]}
    # per-family view of evidenced vs asserted on dev
    report["dev_by_family"] = {
        f: {v: [round(a["evidence_for_cause"]["noul"], 2) for a in ans[f"{ev.TAG}/{v}/{f}"]] for v in ev.VARIANTS}
        for f in ev.SITUATIONS}
    (OUT / "summary_e5c.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.e5c_evidence")
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
