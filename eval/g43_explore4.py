"""G43 exploration 4 on spent data: correctness and assumption questions, and a
split by what the plan can be checked against.

Plan fixed before any run: docs/v3_spike.md, "G43 exploration 4".

    python -m eval.g43_explore4 --run
    python -m eval.g43_explore4 --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st

from app.pipeline import jev_ground as jg
from eval import g43_explore as x
from eval import g43_explore2 as y
from eval import g43_explore3 as z

OUT = x.OUT
REPEATS = x.REPEATS


async def run(concurrency: int) -> None:
    cases = x.pool()
    sem = asyncio.Semaphore(concurrency)

    async def one(c, rep):
        conv = c["shape"] == "conversation"
        async with sem:
            try:
                out = await x._ask("ground_jev_g43x4", x.state(c, False), jg.g43_check_battery(conv), rep)
                return {"arm": "check", "id": c["id"], "repeat": rep, "output": out}
            except Exception as e:
                return {"arm": "check", "id": c["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(c, r) for c in cases for r in range(1, REPEATS + 1)))
    (OUT / "check.json").write_text(json.dumps({"arm": "check", "repeats": REPEATS, "rows": rows}, indent=2))
    print(f"[check] {sum('output' in r for r in rows)} answered, {sum('error' in r for r in rows)} failed")


def answers() -> dict[str, list[dict]]:
    base = z.answers()
    chk = x._load(OUT / "check.json")
    return {cid: [{**a, **chk[cid][i]} for i, a in enumerate(reps) if i < len(chk.get(cid, []))]
            for cid, reps in base.items()}


def _n(a, q):
    return a[q]["noul"]


def checkable(a: dict) -> bool:
    return _n(a, "mechanism_stated") >= 0.7 or _n(a, "goal_stated") >= 0.5


def conflict(a: dict, t: float = 0.5, pcon: float = 0.2) -> bool:
    return ((_n(a, "contradicted") >= t and x._pcon(a) >= pcon)
            or (_n(a, "mechanism_stated") >= 0.7 and _n(a, "plan_misses_cause") >= t)
            or (_n(a, "goal_stated") >= 0.5 and _n(a, "plan_breaks_requirement") >= t))


def asks(a: dict, assume: bool = False) -> bool:
    if _n(a, "problem_described") < 0.3 or _n(a, "plan_is_investigation") >= 0.5:
        return False
    return _n(a, "user_assuming") >= 0.5 if assume else _n(a, "mechanism_stated") < 0.7


def d(a: dict, t: float = 0.5, pcon: float = 0.2, correct: bool = False, assume: bool = False) -> str:
    if checkable(a) and (conflict(a, t, pcon) or (correct and _n(a, "plan_correct") < 0.3)):
        return "objected"
    return "asked" if asks(a, assume) else "none"


def hd(ans: dict, llm: dict, cases: list[dict]) -> tuple[dict, float]:
    preds, sent, total = {}, 0, 0
    for c in cases:
        out = []
        for i, a in enumerate(ans.get(c["id"], [])):
            total += 1
            if checkable(a):
                sent += 1
                got = llm.get(c["id"], [])
                if i < len(got):
                    out.append(got[i])
            else:
                out.append("asked" if asks(a) else "none")
        preds[c["id"]] = out
    return preds, round(sent / total, 3)


def _auc(pos, neg):
    return round(sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg)), 3)


def summarize() -> dict:
    cases = x.pool()
    ans = answers()
    llm = x.llm_preds(cases)
    flat = {c["id"]: z.UNIFORM_L for c in cases}
    hd_preds, hd_share = hd(ans, llm, cases)
    pols = {"llm": llm, "T2": y._preds(ans, z.t2, cases), "D": y._preds(ans, d, cases),
            "D@0.3": y._preds(ans, lambda a: d(a, 0.3, 0.1), cases),
            "D+correct": y._preds(ans, lambda a: d(a, correct=True), cases),
            "D+assume": y._preds(ans, lambda a: d(a, assume=True), cases), "HD": hd_preds}
    report = {"hd_sent_to_llm": hd_share,
              "rates": {k: x.rates(p, cases) for k, p in pols.items()},
              "utility": {f"c=0.25 wrong={s}": {k: z.weighted_utility(p, cases, flat, 0.25, s) for k, p in pols.items()}
                          for s in z.WRONG_SHARES}}
    wrong = [c for c in cases if z.plan_wrong(c)]
    right = [c for c in cases if not z.plan_wrong(c)]
    sep = {}
    for q, sign in (("plan_correct", -1), ("user_assuming", 1), ("bad_solution", 1), ("contradicted", 1),
                    ("goal_stated", 1)):
        pos = [sign * _n(a, q) for c in wrong for a in ans[c["id"]]]
        neg = [sign * _n(a, q) for c in right for a in ans[c["id"]]]
        sep[q] = _auc(pos, neg)
    report["auc_wrong_vs_right"] = sep
    means: dict = {}
    for c in cases:
        for a in ans[c["id"]]:
            g = means.setdefault(f"{x.group(c)}/{'wrong' if z.plan_wrong(c) else 'right'}", {})
            for q in ("goal_stated", "plan_correct", "user_assuming"):
                g.setdefault(q, []).append(_n(a, q))
    report["means"] = {g: {q: round(st.mean(v), 2) for q, v in d_.items()} for g, d_ in sorted(means.items())}
    report["mis-02"] = [{q: round(_n(a, q), 2) for q in ("goal_stated", "plan_correct", "user_assuming")}
                        | {"D": d(a)} for a in ans["full/mis-02"]]
    (OUT / "summary4.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g43_explore4")
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
