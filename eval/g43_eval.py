"""G43 (E6/E7): the held-out run. Specs: docs/v3_spike.md, "E6", and
docs/e7_heldout_run_goal.md, "The held-out run".

    python -m eval.g43_eval --record        # G43 histories, once, after the owner's review
    python -m eval.g43_eval --record-g44    # G44 (late-flaw) histories, once, after its review
    python -m eval.g43_eval --e7-arm llm    # E7, once, after the dev pick is committed
    python -m eval.g43_eval --e7-arm jev
    python -m eval.g43_eval --e7-summarize

The histories are the unaided model's answers to each conversation's earlier
turns. They are recorded once and frozen; they do not depend on any classifier
choice, so recording them before E7's plan is fixed does not spend the test set.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from eval import g41_eval as g41
from eval import g43_heldout as h
from eval import g44_heldout as h44
from eval import g43_explore as x

load_dotenv()

OUT = Path("results/g43")
HISTORIES = OUT / "late_histories.json"
# Fixed in the E6 spec before any recording: with fewer surviving late_flawed
# conversations than this, objection in conversations is reported only.
MIN_LATE_FLAWED = 4
HISTORIES_G44 = Path("results/g44/late_histories.json")


async def record(concurrency: int) -> None:
    h.ready()
    await g41.record_histories(h.load(), HISTORIES, concurrency)


async def record_g44(concurrency: int) -> None:
    """G44's earlier turns are all sound steps, so they are judged as sound."""
    h44.ready()
    await g41.record_histories(h44.history_view(), HISTORIES_G44, concurrency)


# --------------------------------------------------------------------------- E7: the held-out run
# Both arms on G43's single messages and surviving conversations and on G44's
# conversations, three repeats each, run once after the configuration picked
# on dev is committed. Nothing changes after the result. Output names ids and
# rates only: held-out texts are never printed.

E7_CONFIG = None     # a jev_ground.E7Config, set from `python -m eval.e7_dev --select` and committed first
E7_OUT = Path("results/e7")
E7_ROWS = {"llm": E7_OUT / "heldout_llm.json", "jev": E7_OUT / "heldout_jev.json"}
E7_SUMMARY = E7_OUT / "heldout_summary.json"
E7_UTILITY_MARGIN = 0.02     # utility no worse than the LLM's by more than this, per decision
E7_REPORTED_ONLY = "object/conversation, G43"    # E6's survival rule
# The owner's rulings on a held-out plan's chance of being wrong, where the
# frame alone doesn't settle it: case id -> probability, with the date.
E7_P_WRONG_RULINGS: dict[str, float] = {
    # owner, 2026-11-26: `asked` for a fact against its cause, like G44's late facts against the cause
    "g43/single/debatable/button-colour": 0.5,
}
_LATE = {"late_sound": "none", "late_absent": "asked", "late_answered": "none", "late_flawed": "objected"}


def e7_frames() -> list[dict]:
    """Every held-out case as E7 scores it, histories aside: id, set, shape,
    scenario, family and expected action. G43's conversations still unlabelled
    (none are) are left out, as E6 requires."""
    out = [{"id": c["id"], "set": "g43", "shape": "single", "scenario": c["scenario"], "family": c["family"],
            "expected": c["expected"]} for c in h.single_cases()]
    for c in h.load():
        if c.scenario not in _LATE:
            continue
        scenario = "late_task" if c.family.startswith("task-") else c.scenario
        out.append({"id": c.id, "set": "g43", "shape": "conversation", "scenario": scenario,
                    "family": c.family, "expected": _LATE[c.scenario]})
    for c in h44.load():
        out.append({"id": c.id, "set": "g44", "shape": "conversation", "scenario": c.scenario,
                    "family": c.family, "expected": h44.EXPECTED[c.scenario]})
    return out


def e7_p_wrong(c: dict) -> float:
    """The chance a held-out case's plan is wrong, from its recorded frame (the
    spec, "Utility"): an objected case's plan is wrong; a withheld-cause case
    takes its family's fits or misses; G44's late facts against the cause count
    as 0.5 (owner, 2026-11-25); every other plan is right."""
    if c["id"] in E7_P_WRONG_RULINGS:
        return E7_P_WRONG_RULINGS[c["id"]]
    if c["expected"] == "objected":
        return 1.0
    if c["scenario"] == "late_fact_against":
        return 0.5
    if c["scenario"] in ("absent", "late_absent"):
        return 1.0 if c["id"].endswith("-misses") else 0.0
    return 0.0


def e7_cell(c: dict) -> str:
    """The cell a case is scored in: expected action by shape, G43 and G44 together.
    G43's object/conversation cell is kept apart, reported only."""
    if c["set"] == "g43" and c["shape"] == "conversation" and c["expected"] == "objected":
        return E7_REPORTED_ONLY
    return f"{x.group(c)}/{c['shape']}"


def e7_cases() -> list[dict]:
    """The cases scored: G43's single messages, and the conversations whose
    frozen histories survived, with their messages."""
    from app.pipeline import assumptions

    convs = {c.id: c for c in h.load()} | {c.id: c for c in h44.load()}
    hist = {}
    for path in (HISTORIES, HISTORIES_G44):
        if not path.exists():
            raise SystemExit(f"{path} missing: the held-out histories are in results/")
        hist.update(json.loads(path.read_text())["histories"])
    singles = {c["id"]: c for c in h.single_cases()}
    out = []
    for f in e7_frames():
        if f["shape"] == "single":
            q = singles[f["id"]]["query"]
            out.append({**f, "query": q, "context": None, "messages": [{"role": "user", "content": q}]})
            continue
        rec = hist.get(f["id"])
        if not rec or not rec["survived"]:
            continue
        messages = convs[f["id"]].messages(rec["replies"])
        out.append({**f, "query": messages[-1]["content"], "context": assumptions.conversation_view(messages),
                    "messages": messages})
    return out


async def e7_run_arm(arm: str, concurrency: int) -> None:
    from app.pipeline import jev_ground as jg
    from eval import cache, e7_dev
    from eval import ground_classifier_eval as g

    if E7_CONFIG is None:
        raise SystemExit("E7_CONFIG is unset: commit the configuration picked on dev first")
    h.ready()
    h44.ready()
    if E7_ROWS[arm].exists():
        raise SystemExit(f"{E7_ROWS[arm]} exists: the held-out run happens once")
    cases = e7_cases()
    cache.configure(enabled=True)
    meta: dict = {"arm": arm, "config": E7_CONFIG.name}
    if arm == "jev":
        model = e7_dev._require_model()
        if not e7_dev.JEV_ROWS.exists():
            raise SystemExit(f"{e7_dev.JEV_ROWS} missing: the held-out run uses the dev run's model and release")
        release = await e7_dev._release_checked(*e7_dev.jev_files())   # the dev run's release, unchanged
        groups = e7_dev.apart_groups(e7_dev.APART) if e7_dev.APART else []
        meta.update(model=model, release=release, apart=list(e7_dev.APART))

        async def classify(c, r):
            conv = c["shape"] == "conversation"
            st = e7_dev.state(c)
            a = await e7_dev.ask_jev(st, jg.e7_battery(conv, e7_dev.APART), r, release["release_date"])
            for names in groups:
                a = {**a, **await e7_dev.ask_jev(st, jg.e7_questions(names, conv), r, release["release_date"])}
            return a
    else:
        meta.update(model=g.LLM_GROUND_MODEL)

        async def classify(c, r):
            return await g.classify_llm(c, r)

    rows = await e7_dev._gather([(c["id"], r, lambda c=c, r=r: classify(c, r))
                                 for c in cases for r in range(1, e7_dev.REPEATS + 1)], concurrency)
    if arm == "jev":
        after = await jg.jev_release(meta["model"])
        if after != meta["release"]:
            meta["release_changed_during_run"] = after
    E7_OUT.mkdir(parents=True, exist_ok=True)
    E7_ROWS[arm].write_text(json.dumps({**meta, "repeats": e7_dev.REPEATS, "rows": rows}, indent=2))
    print(f"[e7 held-out {arm}] {sum('output' in r for r in rows)} answered, "
          f"{sum('error' in r for r in rows)} failed")


def e7_decide(llm_cells: dict, jev_cells: dict, llm_u: float, jev_u: float) -> dict:
    """The rule fixed on 2026-11-19: utility no worse than the LLM's by more than
    0.02 per decision, and no gated cell more than max(0.07, one case) below it."""
    from eval import e7_dev

    cells = {k: v for k, v in e7_dev.within(jev_cells, llm_cells).items() if k != E7_REPORTED_ONLY}
    utility_ok = jev_u >= llm_u - E7_UTILITY_MARGIN - e7_dev.EPS
    cells_ok = bool(cells) and all(d["met"] for d in cells.values())
    return {"utility": {"llm": llm_u, "jev": jev_u, "margin": E7_UTILITY_MARGIN, "met": utility_ok},
            "cells": cells, "cells_met": cells_ok,
            "replaces_llm": utility_ok and cells_ok,
            "reading": ("Jev can replace the LLM classifier" if utility_ok and cells_ok
                        else "Jev cannot replace the LLM classifier")}


def e7_summarize() -> dict:
    from app.pipeline import jev_ground as jg
    from eval import e7_dev

    if E7_CONFIG is None:
        raise SystemExit("E7_CONFIG is unset")
    cases = e7_cases()
    preds = {}
    for arm, path in E7_ROWS.items():
        if not path.exists():
            raise SystemExit(f"{path} missing: run --e7-arm {arm} first")
        rows = e7_dev._load_rows(path)
        if arm == "llm":
            preds[arm] = {cid: [o["action"] for o in outs] for cid, outs in rows.items()}
        else:
            conv = {c["id"]: c["shape"] == "conversation" for c in cases}
            preds[arm] = {cid: [jg.e7_action(a, E7_CONFIG, conv[cid]) for a in outs] for cid, outs in rows.items()}
    report: dict = {"config": E7_CONFIG.name, "cases": {
        "single": sum(c["shape"] == "single" for c in cases),
        "conversations": {s: sum(c["shape"] == "conversation" and c["set"] == s for c in cases)
                          for s in ("g43", "g44")}}}
    jev_meta = json.loads(E7_ROWS["jev"].read_text())
    report["jev"] = {k: jev_meta.get(k) for k in ("model", "release", "apart", "release_changed_during_run")}
    cells = {arm: g41._tally(p, cases, e7_cell, e7_dev.REPEATS) for arm, p in preds.items()}
    util = {arm: e7_dev.weighted_utility(p, cases, e7_p_wrong) for arm, p in preds.items()}
    report["decision"] = e7_decide(cells["llm"], cells["jev"], util["llm"], util["jev"])
    report["reported_only"] = {
        "by_set": {arm: g41._tally(p, cases, lambda c: f"{c['set']} {e7_cell(c)}", e7_dev.REPEATS)
                   for arm, p in preds.items()},
        "by_kind": {arm: g41._tally(p, cases, lambda c: f"{c['set']} {c['scenario']}", e7_dev.REPEATS)
                    for arm, p in preds.items()},
        E7_REPORTED_ONLY: {arm: cells[arm].get(E7_REPORTED_ONLY) for arm in preds},
    }
    E7_OUT.mkdir(parents=True, exist_ok=True)
    E7_SUMMARY.write_text(json.dumps(report, indent=2, default=str))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g43_eval")
    ap.add_argument("--record", action="store_true", help="record and freeze the conversation histories")
    ap.add_argument("--record-g44", action="store_true", help="record and freeze the G44 histories")
    ap.add_argument("--e7-arm", choices=("llm", "jev"), help="E7's held-out run, once per arm")
    ap.add_argument("--e7-summarize", action="store_true")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args(argv)
    if args.record:
        asyncio.run(record(args.concurrency))
    elif args.record_g44:
        asyncio.run(record_g44(args.concurrency))
    elif args.e7_arm:
        asyncio.run(e7_run_arm(args.e7_arm, args.concurrency))
    elif args.e7_summarize:
        print(json.dumps(e7_summarize(), indent=2, default=str))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
