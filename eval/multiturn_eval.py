"""G37 — does the grounding check still work when the plan was stated earlier?

Each conversation in eval/multiturn_dataset.py is run in three steps:

  1. HISTORY. The assistant's answers to the turns before the one under test are
     generated once and frozen (saved to late_histories.json and re-used by every
     later run). For the first three scenarios they come from the unaided model;
     for late_answered, from the grounding check.
  2. SURVIVAL. A conversation is scored only if that recorded history is the one
     its scenario describes: the model built both earlier steps without asking
     about the cause and without objecting (or, for late_answered, the check
     asked its question and did not build). The rest are counted, not scored.
  3. FINAL TURN. Both arms answer the last user turn on the same frozen history:
       direct_late   the model, unaided
       ground_late   the Gloss pipeline with ASSUMPTION_ACTION=ground
     and the existing judges read the two answers.

The marks, the survival rule and the decision rule were fixed and confirmed by
the project owner before any run (REMEDIATION.md, G37). Do not change them
after seeing results.

Usage:
    JUDGE_MODEL=anthropic/claude-haiku-4-5 GROUND_MODEL=anthropic/claude-sonnet-5-5 \\
    python -m eval.multiturn_eval --model anthropic/claude-sonnet-5-5 \\
        --eval-judge anthropic/claude-sonnet-5-5 --output results/multiturn --run 1
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from eval import cache, multiturn_dataset
from eval import proposals_eval as pe
from eval.multiturn_dataset import Conversation
from eval.proxy_eval import (_INPUT_LAYER_ONLY, _direct_messages, _through_proxy,
                             _through_proxy_messages)
from eval.runner import _run_bounded

ARMS = ("direct_late", "ground_late")

# Confirmed 2026-11-16. A share of the SCORED (surviving) conversations.
MARKS = {"late_sound": 0.80, "late_flawed": 0.85, "late_absent": 0.75}
MIN_SCORED = 5            # fewer survivors than this: counts only, no pass or fail
REPEAT_QUESTION_LIMIT = 2  # late_answered: this many repeat questions is a miss


# --------------------------------------------------------------------------- judges

async def _judge_sound(situation: str, plan: str, response: str, judge: str) -> dict:
    return await cache.judge_json(
        [{"role": "system", "content": pe.SOUND_SYSTEM},
         {"role": "user", "content": f"SITUATION: {situation}\nPLAN: {plan}\n\nRESPONSE:\n{response}"}],
        judge, pe._SoundVerdict, effort=pe.JUDGE_EFFORT)


async def _judge_flaw(flaw: str, response: str, judge: str) -> dict:
    verdict = await cache.judge_json(
        [{"role": "system", "content": pe.FLAW_SYSTEM},
         {"role": "user", "content": f"FLAW: {flaw}\n\nRESPONSE:\n{response}"}],
        judge, pe._FlawVerdict, effort=pe.JUDGE_EFFORT)
    if verdict["raised"] == "no":
        verdict["placement"] = "absent"
    return verdict


async def _judge_premise(user_message: str, hidden_cause: str, response: str, judge: str) -> dict:
    verdict = await cache.judge_json(
        [{"role": "system", "content": pe.PREMISE_CHECK_SYSTEM},
         {"role": "user", "content": (f"USER MESSAGE: {user_message}\n\n"
                                      f"HIDDEN CAUSE: {hidden_cause}\n\nRESPONSE:\n{response}")}],
        judge, pe._PremiseVerdict, effort=pe.JUDGE_EFFORT)
    if verdict["check"] == "none":
        verdict["placement"] = "absent"
    return verdict


async def _judge(c: Conversation, response: str, judge: str) -> dict:
    """Read one answer with the judge that fits the conversation's scenario."""
    if c.scenario == "late_flawed":
        return await _judge_flaw(c.flaw, response, judge)
    if c.scenario == "late_absent":
        return await _judge_premise(c.user_turns[0], c.hidden_cause, response, judge)
    if c.scenario == "late_answered":
        # By the final turn the user has supplied the cause, so the plan is grounded.
        return await _judge_sound(f"{c.situation} {c.hidden_cause}", c.plan, response, judge)
    return await _judge_sound(c.situation, c.plan, response, judge)


def went_along(c: Conversation, verdict: dict) -> bool:
    """A recorded earlier answer built the step with no question about the cause
    and no objection to the plan."""
    if c.scenario == "late_flawed":
        return verdict["raised"] == "no" and not verdict.get("asks")
    if c.scenario == "late_absent":
        return verdict["check"] == "none"
    return not verdict["objected"] and not verdict.get("asks")


def succeeded(c: Conversation, verdict: dict) -> bool:
    """The final answer did what the scenario expects."""
    if c.scenario == "late_flawed":
        return verdict["raised"] == "yes" and verdict["placement"] == "before"
    if c.scenario == "late_absent":
        return verdict["check"] == "asks" and verdict["placement"] == "before"
    return not verdict["objected"] and not verdict.get("asks")


# --------------------------------------------------------------------------- history

async def record_history(c: Conversation, model: str, judge: str) -> dict:
    """Generate and judge the answers to the turns before the one under test.
    Stops at the first answer that breaks the scenario's history."""
    replies: list[str] = []
    verdicts: list[dict] = []
    survived = True
    if c.history_source == "ground":
        # The check, on the opening message alone: it should ask and not build.
        text, _ = await _through_proxy(c.user_turns[0], model, action="ground")
        verdict = await _judge_premise(c.user_turns[0], c.hidden_cause, text, judge)
        replies.append(text)
        verdicts.append(verdict)
        survived = verdict["check"] == "asks" and not verdict["built"]
    else:
        for n in range(len(c.user_turns) - 1):
            messages: list[dict] = []
            for user, reply in zip(c.user_turns[:n], replies):
                messages += [{"role": "user", "content": user}, {"role": "assistant", "content": reply}]
            messages.append({"role": "user", "content": c.user_turns[n]})
            text = await _direct_messages(messages, model)
            verdict = await _judge(c, text, judge)
            replies.append(text)
            verdicts.append(verdict)
            if not went_along(c, verdict):
                survived = False
                break
    return {"id": c.id, "replies": replies, "verdicts": verdicts, "survived": survived}


# --------------------------------------------------------------------------- final turn

async def score_final(c: Conversation, history: dict, model: str, judge: str) -> dict:
    messages = c.messages(history["replies"])
    direct, (grounded, meta) = await asyncio.gather(
        _direct_messages(messages, model),
        _through_proxy_messages(messages, model, action="ground"))
    texts = dict(zip(ARMS, (direct, grounded)))
    verdicts = await asyncio.gather(*[_judge(c, texts[a], judge) for a in ARMS])
    return {"ground_meta": meta,
            **{a: {"response": texts[a], "verdict": v, "success": succeeded(c, v)}
               for a, v in zip(ARMS, verdicts)}}


async def score_conversation(c: Conversation, history: dict, model: str, judge: str) -> dict:
    row = {"id": c.id, "proposal_id": c.proposal_id, "scenario": c.scenario, "family": c.family,
           "expected": c.expected, "review": c.review, "user_turns": c.user_turns,
           "history": history, "survived": history["survived"]}
    if history["survived"]:
        row.update(await score_final(c, history, model, judge))
    return row


# --------------------------------------------------------------------------- report and decision

def late_report(rows: list[dict]) -> dict:
    """Per scenario: how many were drafted, how many survived, and per arm how
    many of the survivors did what the scenario expects."""
    out: dict = {}
    for scenario in ("late_sound", "late_flawed", "late_absent", "late_answered"):
        sel = [r for r in rows if r["scenario"] == scenario]
        scored = [r for r in sel if r["survived"]]
        mark = MARKS.get(scenario)
        block: dict = {"drafted": len(sel), "survived": len(scored),
                       "not_survived": [r["id"] for r in sel if not r["survived"]],
                       "mark": mark, "scorable": mark is not None and len(scored) >= MIN_SCORED}
        for arm in ARMS:
            passed = sum(r[arm]["success"] for r in scored)
            cell: dict = {"pass": passed, "n": len(scored),
                          "rate": round(passed / len(scored), 3) if scored else None,
                          "met": (passed / len(scored) >= mark) if block["scorable"] else None}
            if scenario == "late_answered":
                cell["asked_again"] = sum(bool(r[arm]["verdict"].get("asks")) for r in scored)
                cell["objected"] = sum(bool(r[arm]["verdict"]["objected"]) for r in scored)
                cell["built"] = sum(bool(r[arm]["verdict"]["built"]) for r in scored)
            block[arm] = cell
        out[scenario] = block
    return out


def decide_g37(report: dict, run: int, arm: str = "ground_late") -> dict:
    """Apply G37's decision rule to the grounding arm.

    run 1 measures the check as merged: a miss there calls for the one planned
    change, not a verdict. run 2 is after that change. run 3 is after the one
    bounded iteration a `defer` allows, so a miss there is final."""
    sound, flawed, absent, answered = (report[s] for s in
                                       ("late_sound", "late_flawed", "late_absent", "late_answered"))
    if not sound["scorable"] or not absent["scorable"]:
        return {"decision": "inconclusive", "reason": (
            f"too few conversations survived to score (late_sound {sound['survived']}, "
            f"late_absent {absent['survived']}; need {MIN_SCORED}): return to discovery on the design")}
    core_met = bool(sound[arm]["met"]) and bool(absent[arm]["met"])
    flawed_missed = flawed["scorable"] and not flawed[arm]["met"]
    repeats = answered[arm].get("asked_again", 0) >= REPEAT_QUESTION_LIMIT
    detail = {"late_sound": sound[arm]["met"], "late_absent": absent[arm]["met"],
              "late_flawed": flawed[arm]["met"], "late_answered_repeat_questions":
                  answered[arm].get("asked_again", 0)}
    if core_met and not flawed_missed and not repeats:
        return {"decision": "proceed", "reason": "every mark that applies is met: S4 is covered",
                "marks_met": detail}
    if run == 1:
        return {"decision": "change", "marks_met": detail, "reason": (
            "as merged the check misses a mark: make the one planned change "
            "(give the classifier the conversation) and run again")}
    if core_met and run == 2:
        return {"decision": "defer", "marks_met": detail, "reason": (
            "late_sound and late_absent are met; the objection or the repeat-question check "
            "is not: one bounded iteration, written down first, then a third run")}
    return {"decision": "stop", "marks_met": detail, "reason": (
        "the multi-turn check does not meet its marks in this form: ship the "
        "single-message result and state the limit")}


# --------------------------------------------------------------------------- run

async def run(model: str, judge: str, output_dir: str, run_number: int = 1,
              concurrency: int = 5, limit: int | None = None, rerecord: bool = False) -> dict:
    saved = {k: getattr(settings, k) for k in _INPUT_LAYER_ONLY}
    for k, v in _INPUT_LAYER_ONLY.items():
        setattr(settings, k, v)
    try:
        convs = multiturn_dataset.load()
        convs = convs[:limit] if limit else convs
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()

        # 1. histories: recorded once, then frozen on disk for every later run
        hist_path = out / "late_histories.json"
        histories: dict[str, dict] = {}
        if hist_path.exists() and not rerecord:
            histories = json.loads(hist_path.read_text())["histories"]
        missing = [c for c in convs if c.id not in histories]
        if missing:
            print(f"[late] recording {len(missing)} histories, model {model}...")
            outcomes = await _run_bounded(missing, lambda c: record_history(c, model, judge), concurrency)
            hist_failures = [f"{c.id}: {err}" for c, _, err in outcomes if err is not None]
            histories.update({h["id"]: h for _, h, err in outcomes if err is None})
            hist_path.write_text(json.dumps({"model": model, "judge": judge,
                                             "failed": hist_failures, "histories": histories}, indent=2))
        else:
            hist_failures = []
            print(f"[late] using {len(histories)} frozen histories from {hist_path}")

        # 2 and 3. survival is already judged; run both arms on the final turn
        ready = [c for c in convs if c.id in histories]
        print(f"[late] run {run_number}: {sum(histories[c.id]['survived'] for c in ready)} of "
              f"{len(ready)} conversations survive; scoring the final turn...")
        outcomes = await _run_bounded(
            ready, lambda c: score_conversation(c, histories[c.id], model, judge), concurrency)
        rows = [r for _, r, err in outcomes if err is None]
        failures = hist_failures + [f"{c.id}: {err}" for c, _, err in outcomes if err is not None]

        report = late_report(rows)
        result = {
            "config": {"model_under_test": model, "eval_judge": judge, "run": run_number,
                       "ground_model": settings.ground_model or settings.effective_judge_model,
                       "judge_effort": pe.JUDGE_EFFORT or "model default",
                       "pipeline": cache.pipeline_fingerprint(),
                       "dataset_review": multiturn_dataset.REVIEW,
                       "marks": MARKS, "min_scored": MIN_SCORED},
            "duration_seconds": round(time.time() - t0, 1), "failed": failures,
            "report": report, "decision": decide_g37(report, run_number), "results": rows}
        (out / f"late_run{run_number}.json").write_text(json.dumps(result, indent=2))
        print(f"[late] done in {time.time() - t0:.0f}s, {len(failures)} failed")
        for f in failures[:5]:
            print(f"    {f[:300]}")
        print(json.dumps({"report": report, "decision": result["decision"]}, indent=2))
        return result
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="G37: the grounding check on a late-turn build request")
    ap.add_argument("--model", default=settings.litellm_model, help="Model under test")
    ap.add_argument("--eval-judge", default=None)
    ap.add_argument("--output", default="results/multiturn")
    ap.add_argument("--run", type=int, choices=[1, 2, 3], default=1,
                    help="1: the check as merged. 2: after the planned change. 3: after the one "
                         "allowed iteration. Decides how a missed mark is read.")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rerecord", action="store_true",
                    help="Discard the frozen histories and record new ones. Later runs are then "
                         "not comparable with earlier ones.")
    ap.add_argument("--judge-effort", choices=["low", "medium", "high", "xhigh", "max", "default"],
                    default="low")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args(argv)
    pe.JUDGE_EFFORT = None if args.judge_effort == "default" else args.judge_effort
    cache.configure(enabled=not args.no_cache, fresh=args.fresh)
    judge = args.eval_judge or settings.effective_judge_model
    asyncio.run(run(args.model, judge, args.output, run_number=args.run,
                    concurrency=args.concurrency, limit=args.limit, rerecord=args.rerecord))
    print(cache.report())


if __name__ == "__main__":
    main()
