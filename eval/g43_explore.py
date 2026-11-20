"""G43 exploration on spent data: user turns only, then a graded cause question.

Plan fixed before any run: docs/v3_spike.md, "G43 exploration". Nothing here is
a held-out result; it decides what the G43 held-out test should measure.

    python -m eval.g43_explore --run user      # step 1: G42's battery on user-only conversations
    python -m eval.g43_explore --run level     # step 2: cause_level on every case, both forms
    python -m eval.g43_explore --summarize
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from app.config import settings
from app.pipeline import jev_ground as jg
from eval import g41_eval as g41
from eval import g42_eval as g42

load_dotenv()

OUT = Path("results/g43_explore")
REPEATS = 3
# Owner ruling 1 (2026-11-18): a plan clause stating what is happening now is a stated cause.
RELABELLED = {"g42/single/absent/cold-starts-fits", "g42/late_absent/cold-starts-fits",
              "g42/single/absent/admin-page-fits", "g42/late_absent/admin-page-fits"}


# --------------------------------------------------------------------------- cases

def pool() -> list[dict]:
    out = []
    for part, cases in (("g42_dev", g42.dev_cases()), ("g42_test", g42.test_cases())):
        for c in cases:
            c = {**c, "part": part}
            if c["id"] in RELABELLED:
                c["expected"] = "none"
            out.append(c)
    return out


def group(c: dict) -> str:
    if c["scenario"] in ("task", "late_task"):
        return "task"
    if c["scenario"] == "late_answered":
        return "answered"
    return {"none": "quiet", "asked": "ask", "objected": "object"}[c["expected"]]


def state(c: dict, user_only: bool) -> str:
    if c["shape"] == "single":
        return c["query"]
    return jg.user_turns_view(c["messages"]) if user_only else c["context"]


# --------------------------------------------------------------------------- runs

async def _ask(kind: str, st_: str, questions: dict, repeat: int) -> dict:
    from eval import cache
    return await cache.get_or_run(
        kind, {"model": settings.jev_model, "battery": questions, "state": st_, "repeat": repeat},
        lambda: jg.ask_jev_questions(st_, questions))


async def run(step: str, concurrency: int) -> None:
    cases = pool()
    sem = asyncio.Semaphore(concurrency)
    jobs = []
    if step == "user":
        for c in cases:
            if c["shape"] == "conversation":
                jobs.append(("battery_user", c, jg.g43_battery(True, True), state(c, True)))
    else:
        for c in cases:
            conv = c["shape"] == "conversation"
            for user_only in ((False, True) if conv else (False,)):
                arm = "level_user" if user_only else "level_full"
                jobs.append((arm, c, jg.cause_level_question(conv, user_only), state(c, user_only)))

    async def one(arm, c, qs, s, rep):
        async with sem:
            try:
                return {"arm": arm, "id": c["id"], "repeat": rep,
                        "output": await _ask("ground_jev_g43x", s, qs, rep)}
            except Exception as e:
                return {"arm": arm, "id": c["id"], "repeat": rep, "error": repr(e)}

    rows = await asyncio.gather(*(one(*j, r) for j in jobs for r in range(1, REPEATS + 1)))
    OUT.mkdir(parents=True, exist_ok=True)
    for arm in sorted({r["arm"] for r in rows}):
        mine = [r for r in rows if r["arm"] == arm]
        (OUT / f"{arm}.json").write_text(json.dumps(
            {"arm": arm, "model": settings.jev_model, "repeats": REPEATS, "rows": mine}, indent=2))
        print(f"[{arm}] {sum('output' in r for r in mine)} answered, {sum('error' in r for r in mine)} failed")


# --------------------------------------------------------------------------- scoring

def _load(path: Path) -> dict[str, list[dict]]:
    out: dict = defaultdict(list)
    if path.exists():
        for r in json.loads(path.read_text())["rows"]:
            if "output" in r:
                out[r["id"]].append(r["output"])
    return out


def answers(user_only: bool) -> dict[str, list[dict]]:
    """Per case and repeat: the battery's answers merged with cause_level's.
    Single messages use G42's recorded battery answers in both forms."""
    full = _load(g42.OUT / "jev_g42_plain.json")
    user = _load(OUT / "battery_user.json")
    lvl_full, lvl_user = _load(OUT / "level_full.json"), _load(OUT / "level_user.json")
    out = {}
    for c in pool():
        conv = c["shape"] == "conversation"
        bat = user.get(c["id"], []) if (conv and user_only) else full.get(c["id"], [])
        lvl = (lvl_user if (conv and user_only) else lvl_full).get(c["id"], [])
        out[c["id"]] = [{**b, **(lvl[i] if i < len(lvl) else {})} for i, b in enumerate(bat)]
    return out


def _n(a: dict, q: str) -> float:
    return a[q]["noul"]


def _pcon(a: dict) -> float:
    return a["link"]["probabilities"]["contradicted"]


def r0(a: dict) -> str:
    if _n(a, "contradicted") >= 0.3:
        return "objected"
    return "asked" if _n(a, "problem_described") >= 0.3 and _n(a, "mechanism_stated") < 0.7 else "none"


def r1(a: dict) -> str:
    ev = _n(a, "mechanism_stated") >= 0.7
    if ev and _pcon(a) >= 0.2 and _n(a, "contradicted") >= 0.3:
        return "objected"
    return "asked" if _n(a, "problem_described") >= 0.3 and not ev else "none"


def l1(a: dict, t: float = 0.5) -> str | None:
    if "cause_level" not in a:
        return None
    ev = jg.stated_probability(a) >= t
    if ev and _pcon(a) >= 0.2 and _n(a, "contradicted") >= 0.3:
        return "objected"
    return "asked" if _n(a, "problem_described") >= 0.3 and not ev else "none"


def rates(preds: dict, cases: list[dict]) -> dict:
    return g41._tally(preds, cases, lambda c: f"{group(c)}/{c['shape']}", REPEATS)


def _preds(ans: dict, rule, cases) -> dict:
    return {c["id"]: [x for x in (rule(a) for a in ans.get(c["id"], [])) if x] for c in cases}


def llm_preds(cases) -> dict:
    data = _load(g42.OUT / "llm.json")
    return {c["id"]: [o["action"] for o in data.get(c["id"], [])] for c in cases}


def level_profile(ans: dict, cases: list[dict]) -> dict:
    """Mean probability of each level by group and shape, and how often the
    probabilities are unimodal along the order of the levels."""
    by: dict = defaultdict(lambda: defaultdict(list))
    ordered = total = 0
    for c in cases:
        for a in ans.get(c["id"], []):
            if "cause_level" not in a:
                continue
            p = [a["cause_level"]["probabilities"][k] for k in jg.CAUSE_LEVELS]
            for k, v in zip(jg.CAUSE_LEVELS, p):
                by[f"{group(c)}/{c['shape']}"][k].append(v)
            peak = p.index(max(p))
            ordered += all(p[i] >= p[i + 1] for i in range(peak, 3)) and all(
                p[i] <= p[i + 1] for i in range(peak))
            total += 1
    return {"mean_by_group": {g: {k: round(st.mean(v), 2) for k, v in d.items()}
                              for g, d in sorted(by.items())},
            "unimodal_share": round(ordered / total, 3) if total else None}


def summarize() -> dict:
    cases = pool()
    parts = {"all": cases, **{p: [c for c in cases if c["part"] == p] for p in ("g42_dev", "g42_test")}}
    report: dict = {"relabelled": sorted(RELABELLED), "cases": {k: len(v) for k, v in parts.items()}}
    llm = llm_preds(cases)
    for name, cs in parts.items():
        sec = {"llm": rates(llm, cs)}
        for form, user_only in (("full", False), ("user", True)):
            ans = answers(user_only)
            sec[f"R0/{form}"] = rates(_preds(ans, r0, cs), cs)
            sec[f"R1/{form}"] = rates(_preds(ans, r1, cs), cs)
            for t in (0.5, 0.3, 0.7):
                tag = "L1" if t == 0.5 else f"L1@{t} (reported only)"
                sec[f"{tag}/{form}"] = rates(_preds(ans, lambda a, t=t: l1(a, t), cs), cs)
            sec[f"cause_level profile/{form}"] = level_profile(ans, cs)
        report[name] = sec
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g43_explore")
    ap.add_argument("--run", choices=("user", "level"))
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args(argv)
    if args.run:
        asyncio.run(run(args.run, args.concurrency))
    if args.summarize:
        print(json.dumps(summarize(), indent=2))


if __name__ == "__main__":
    main()
