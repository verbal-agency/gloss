"""G43 exploration 2 on spent data: split contradiction, risk questions, a cascade.

Plan fixed before any run: docs/v3_spike.md, "G43 exploration 2". Full
conversation state; the same pool and relabels as exploration 1.

    python -m eval.g43_explore2 --run
    python -m eval.g43_explore2 --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
from collections import defaultdict

from app.pipeline import jev_ground as jg
from eval import g42_eval as g42
from eval import g43_explore as x

OUT = x.OUT
REPEATS = x.REPEATS


async def run(concurrency: int) -> None:
    cases = x.pool()
    sem = asyncio.Semaphore(concurrency)

    async def one(c, rep):
        conv = c["shape"] == "conversation"
        async with sem:
            try:
                out = await x._ask("ground_jev_g43x2", x.state(c, False), jg.g43_risk_battery(conv), rep)
                return {"arm": "risk", "id": c["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": "risk", "id": c["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(c, r) for c in cases for r in range(1, REPEATS + 1)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "risk.json").write_text(json.dumps({"arm": "risk", "repeats": REPEATS, "rows": rows}, indent=2))
    print(f"[risk] {sum('output' in r for r in rows)} answered, {sum('error' in r for r in rows)} failed")


# --------------------------------------------------------------------------- answers and rules

def answers() -> dict[str, list[dict]]:
    """Per case and repeat: G42's battery, cause_level (full form) and the risk questions."""
    base = x.answers(False)
    risk = x._load(OUT / "risk.json")
    out = {}
    for cid, reps in base.items():
        rk = risk.get(cid, [])
        out[cid] = [{**a, **rk[i]} for i, a in enumerate(reps) if i < len(rk)]
    return out


def _n(a, q):
    return a[q]["noul"]


def s1(a: dict, t: float = 0.5) -> str:
    ev = _n(a, "mechanism_stated") >= 0.7
    if (ev and _n(a, "plan_misses_cause") >= t) or _n(a, "plan_breaks_requirement") >= t:
        return "objected"
    return "asked" if _n(a, "problem_described") >= 0.3 and not ev else "none"


def k1(a: dict, t: float = 0.5) -> str:
    if x.r1(a) == "objected":
        return "objected"
    return "asked" if _n(a, "problem_described") >= 0.3 and _n(a, "wasted_effort") >= t else "none"


def _in(v, lo, hi):
    return lo <= v < hi


def uncertain(a: dict, rule: str) -> bool:
    """Whether a score the rule decides on lies in its band (fixed in the plan)."""
    mech = _n(a, "mechanism_stated")
    if _in(mech, 0.55, 0.85):
        return True
    if mech >= 0.7:
        if rule == "R1" and (_in(_n(a, "contradicted"), 0.2, 0.45) or _in(x._pcon(a), 0.1, 0.3)):
            return True
        if rule == "S1" and _in(_n(a, "plan_misses_cause"), 0.3, 0.7):
            return True
    if rule == "S1" and _in(_n(a, "plan_breaks_requirement"), 0.3, 0.7):
        return True
    return False


def cascade(ans: dict, llm: dict, rule: str, cases: list[dict]) -> tuple[dict, float]:
    f = x.r1 if rule == "R1" else s1
    preds, deferred, total = {}, 0, 0
    for c in cases:
        out = []
        for i, a in enumerate(ans.get(c["id"], [])):
            total += 1
            if uncertain(a, rule):
                deferred += 1
                got = llm.get(c["id"], [])
                if i < len(got):
                    out.append(got[i])
            else:
                out.append(f(a))
        preds[c["id"]] = out
    return preds, round(deferred / total, 3) if total else 0.0


def _preds(ans, rule, cases):
    return {c["id"]: [rule(a) for a in ans.get(c["id"], [])] for c in cases}


def _auc(pos, neg):
    if not pos or not neg:
        return None
    return round(sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg)), 3)


def descriptive(ans: dict, cases: list[dict]) -> dict:
    by: dict = defaultdict(lambda: defaultdict(list))
    for c in cases:
        for a in ans.get(c["id"], []):
            for q in ("stakes", "bad_solution", "wasted_effort", "plan_misses_cause", "plan_breaks_requirement"):
                by[f"{x.group(c)}/{c['shape']}"][q].append(_n(a, q))
    absent = [c for c in cases if c["scenario"] in ("absent", "late_absent") and "family" in c]
    fits = [_n(a, "bad_solution") for c in absent if c["family"].endswith("fits") or c["id"].endswith("fits")
            for a in ans.get(c["id"], [])]
    misses = [_n(a, "bad_solution") for c in absent if c["id"].endswith("misses") for a in ans.get(c["id"], [])]
    ask = [c for c in cases if x.group(c) == "ask"]
    quiet = [c for c in cases if x.group(c) in ("quiet", "answered")]
    sep = {}
    for q, sign in (("mechanism_stated", 1), ("wasted_effort", -1), ("bad_solution", -1)):
        pos = [sign * _n(a, q) for c in quiet for a in ans.get(c["id"], [])]
        neg = [sign * _n(a, q) for c in ask for a in ans.get(c["id"], [])]
        sep[q] = _auc(pos, neg)
    return {"mean_by_group": {g: {q: round(st.mean(v), 2) for q, v in d.items()} for g, d in sorted(by.items())},
            "bad_solution_misses_vs_fits_auc": _auc(misses, fits),
            "auc_quiet_vs_ask": sep}


def summarize() -> dict:
    cases = x.pool()
    ans = answers()
    llm = x.llm_preds(cases)
    parts = {"all": cases, **{p: [c for c in cases if c["part"] == p] for p in ("g42_dev", "g42_test")}}
    report: dict = {}
    for name, cs in parts.items():
        sec = {"llm": x.rates(llm, cs), "R1": x.rates(_preds(ans, x.r1, cs), cs)}
        for t in (0.5, 0.3, 0.7):
            tag = "" if t == 0.5 else f"@{t} (reported only)"
            sec[f"S1{tag}"] = x.rates(_preds(ans, lambda a, t=t: s1(a, t), cs), cs)
            sec[f"K1{tag}"] = x.rates(_preds(ans, lambda a, t=t: k1(a, t), cs), cs)
        for rule in ("R1", "S1"):
            p, share = cascade(ans, llm, rule, cs)
            sec[f"C1({rule})"] = x.rates(p, cs)
            sec[f"C1({rule}) deferred"] = share
        sec["descriptive"] = descriptive(ans, cs)
        report[name] = sec
    (OUT / "summary2.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g43_explore2")
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
