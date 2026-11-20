"""G43 exploration 3 on spent data: a Jev decision tree and a value-of-information model.

Plan fixed before any run: docs/v3_spike.md, "G43 exploration 3".

    python -m eval.g43_explore3 --run
    python -m eval.g43_explore3 --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st

from app.pipeline import jev_ground as jg
from eval import g43_explore as x
from eval import g43_explore2 as y

OUT = x.OUT
REPEATS = x.REPEATS
R, R_O = 0.8, 0.9          # chance an answer / an objection exposes a wrong plan
COSTS = (0.05, 0.1, 0.25, 0.5)
PRIOR = 0.5                # P(wrong | no stated evidence); 0.25 reported as sensitivity
UNIFORM_L = 3.0


async def run(concurrency: int) -> None:
    cases = x.pool()
    sem = asyncio.Semaphore(concurrency)

    async def one(arm, c, rep):
        conv = c["shape"] == "conversation"
        qs = jg.g43_tree_battery(conv) if arm == "tree" else jg.g43_step4_battery(conv)
        async with sem:
            try:
                out = await x._ask(f"ground_jev_g43x3_{arm}", x.state(c, False), qs, rep)
                return {"arm": arm, "id": c["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": arm, "id": c["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(a, c, r) for a in ("tree", "step4") for c in cases
                                  for r in range(1, REPEATS + 1)))
    for arm in ("tree", "step4"):
        mine = [r for r in rows if r["arm"] == arm]
        (OUT / f"{arm}.json").write_text(json.dumps({"arm": arm, "repeats": REPEATS, "rows": mine}, indent=2))
        print(f"[{arm}] {sum('output' in r for r in mine)} answered, {sum('error' in r for r in mine)} failed")


def answers() -> dict[str, list[dict]]:
    base = y.answers()
    tree, step4 = x._load(OUT / "tree.json"), x._load(OUT / "step4.json")
    out = {}
    for cid, reps in base.items():
        t, s = tree.get(cid, []), step4.get(cid, [])
        out[cid] = [{**a, **t[i], **s[i]} for i, a in enumerate(reps) if i < len(t) and i < len(s)]
    return out


def _n(a, q):
    return a[q]["noul"]


# --------------------------------------------------------------------------- policies

def t1(a: dict, t4: float = 0.5) -> str:
    if _n(a, "problem_described") < 0.3 or _n(a, "plan_is_investigation") >= 0.5:
        return "none"
    if _n(a, "mechanism_stated") < 0.7:
        return "asked"
    if max(_n(a, "misses_stated_cause"), _n(a, "breaks_stated_requirement")) >= t4:
        return "objected"
    return "none"


def scope_cost(a: dict) -> float:
    p = a["plan_scope"]["probabilities"]
    return sum(jg.PLAN_SCOPE_COST[k] * v for k, v in p.items())


def p_wrong(a: dict, prior: float = PRIOR) -> float:
    if _n(a, "problem_described") < 0.3 or _n(a, "plan_is_investigation") >= 0.5:
        return 0.0
    m = _n(a, "mechanism_stated")
    q = max(_n(a, "misses_stated_cause"), _n(a, "breaks_stated_requirement"))
    return (1 - m) * prior + m * q


def v1(a: dict, c: float, prior: float = PRIOR) -> str:
    p, L, d = p_wrong(a, prior), scope_cost(a), 2 * c
    eu = {"none": -p * L, "asked": -c - p * (1 - R) * L}
    if _n(a, "mechanism_stated") >= 0.7:
        eu["objected"] = -c - (1 - p) * d - p * (1 - R_O) * L
    return max(eu, key=eu.get)


# --------------------------------------------------------------------------- utility scoring

def plan_wrong(c: dict) -> bool:
    if c["scenario"] in ("contradicted", "mismatch", "infeasible", "wrong_fix"):
        return True
    tail = c["id"].rsplit("/", 1)[-1]
    return c["id"].endswith("misses") or tail.startswith("mis-")


def utility(action: str, c: dict, L: float, cost: float) -> float:
    wrong = plan_wrong(c)
    if c["scenario"] == "late_answered" and action != "none":
        return -2 * cost - (L if wrong else 0.0)      # asking again teaches nothing
    if action == "none":
        return -L if wrong else 0.0
    if action == "asked":
        return -cost - ((1 - R) * L if wrong else 0.0)
    return -cost - ((1 - R_O) * L if wrong else 2 * cost)


def mean_utility(preds: dict, cases: list[dict], Ls: dict, cost: float) -> float:
    vals = []
    for c in cases:
        for i, act in enumerate(preds.get(c["id"], [])):
            vals.append(utility(act, c, Ls[c["id"]][i] if isinstance(Ls[c["id"]], list) else Ls[c["id"]], cost))
    return round(st.mean(vals), 3)


def summarize() -> dict:
    cases = x.pool()
    ans = answers()
    llm = x.llm_preds(cases)
    jev_L = {c["id"]: [scope_cost(a) for a in ans[c["id"]]] for c in cases}
    flat_L = {c["id"]: UNIFORM_L for c in cases}
    fixed = {
        "always quiet": {c["id"]: ["none"] * REPEATS for c in cases},
        "always ask": {c["id"]: ["asked"] * REPEATS for c in cases},
        "llm": llm,
        "R1": y._preds(ans, x.r1, cases),
        "S1": y._preds(ans, y.s1, cases),
        "T1": y._preds(ans, t1, cases),
        "T1@0.3 (reported only)": y._preds(ans, lambda a: t1(a, 0.3), cases),
        "T1@0.7 (reported only)": y._preds(ans, lambda a: t1(a, 0.7), cases),
    }
    report: dict = {"rates": {}, "utility": {}, "plan_scope": {}}
    parts = {"all": cases, **{p: [c for c in cases if c["part"] == p] for p in ("g42_dev", "g42_test")}}
    for pname, cs in parts.items():
        report["rates"][pname] = {k: x.rates(v, cs) for k, v in fixed.items()}
        for cost in COSTS:
            for prior in (PRIOR, 0.25):
                tag = f"V1(c={cost})" + ("" if prior == PRIOR else f" prior={prior}")
                report["rates"][pname][tag] = x.rates(y._preds(ans, lambda a, c=cost, p=prior: v1(a, c, p), cs), cs)
    for cost in COSTS:
        pols = {**fixed, "V1": y._preds(ans, lambda a, c=cost: v1(a, c), cases),
                "V1 prior=0.25": y._preds(ans, lambda a, c=cost: v1(a, c, 0.25), cases)}
        report["utility"][f"c={cost}"] = {
            k: {"jev_L": mean_utility(p, cases, jev_L, cost), "uniform_L": mean_utility(p, cases, flat_L, cost)}
            for k, p in pols.items()}
    for c in cases:
        g = x.group(c)
        report["plan_scope"].setdefault(g, []).extend(jev_L[c["id"]])
    report["plan_scope"] = {g: round(st.mean(v), 2) for g, v in report["plan_scope"].items()}
    (OUT / "summary3.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g43_explore3")
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
