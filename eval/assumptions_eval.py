"""Assumptions evaluation harness (built as the G27 de-risk spike; kept and grown
from G28 on) — run the assumption extractor over the hand-labeled dataset and
report the two numbers that decide whether the input-layer direction holds:

  - detection rate  (LOADED): fraction where a questionable premise WAS surfaced
                              — recall on queries that genuinely have one.
  - false-positive  (CLEAN):  fraction where a questionable premise was WRONGLY
                              surfaced — the faithfulness metric (must stay low).

Both are broken out by group (G28): loaded by category (factual vs framing), clean
by kind (near_miss vs neutral), so we see whether detection generalizes from the
original factual-premise batch to the harder framing-bias batch, and whether false
positives concentrate on the near-misses.

Per-query output is printed so a human can eyeball whether the RIGHT premise was
caught (semantic matching is not automated — this is a probe, not a benchmark).

Live run (spends ~55 judge-model calls): `python -m eval.assumptions_eval`
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from dotenv import load_dotenv

from app.pipeline import assumptions
from app.pipeline.assumptions import AssumptionResult
from eval.assumptions_dataset import CLEAN, LOADED

load_dotenv()  # push .env keys into the environment where litellm reads them (matches eval/runner.py)


@dataclass
class QueryOutcome:
    query: str
    result: AssumptionResult
    group: str                    # category (loaded: factual|framing) or kind (clean: near_miss|neutral)
    intended: str | None = None   # the premise we hoped to surface (loaded only)

    @property
    def fired(self) -> bool:
        return bool(self.result.questionable)


def _rate(items: list[QueryOutcome]) -> tuple[int, int, float]:
    n = len(items) or 1
    fired = sum(o.fired for o in items)
    return fired, len(items), round(fired / n, 3)


def _grouped(items: list[QueryOutcome]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for g in sorted({o.group for o in items}):
        fired, n, rate = _rate([o for o in items if o.group == g])
        out[g] = {"fired": fired, "count": n, "rate": rate}
    return out


def summarize(loaded: list[QueryOutcome], clean: list[QueryOutcome]) -> dict:
    """Pure metric computation — no I/O, no live calls (unit-testable)."""
    detected, n_loaded, det_rate = _rate(loaded)
    false_pos, n_clean, fp_rate = _rate(clean)
    return {
        "loaded_count": n_loaded,
        "clean_count": n_clean,
        "detection_rate": det_rate,          # recall on loaded
        "false_positive_rate": fp_rate,      # faithfulness
        "detected": detected,
        "false_positives": false_pos,
        "detection_by_category": _grouped(loaded),   # factual vs framing
        "false_positive_by_kind": _grouped(clean),   # near_miss vs neutral
    }


async def run_eval(
    model: str | None = None,
    loaded_set: list[tuple[str, str, str]] = LOADED,
    clean_set: list[tuple[str, str]] = CLEAN,
) -> tuple[list[QueryOutcome], list[QueryOutcome], dict]:
    loaded = [
        QueryOutcome(q, await assumptions.extract(q, model=model), cat, intended=intended)
        for q, intended, cat in loaded_set
    ]
    clean = [
        QueryOutcome(q, await assumptions.extract(q, model=model), kind)
        for q, kind in clean_set
    ]
    return loaded, clean, summarize(loaded, clean)


def format_report(loaded: list[QueryOutcome], clean: list[QueryOutcome], summary: dict) -> str:
    lines = ["=== LOADED (want questionable premise surfaced) ==="]
    for o in loaded:
        mark = "✓" if o.fired else "✗ MISS"
        lines.append(f"[{mark}] ({o.group}) {o.query}")
        lines.append(f"      intended: {o.intended}")
        lines.append(f"      flagged:  {o.result.questionable or '(none)'}")
    lines.append("\n=== CLEAN (want EMPTY questionable list) ===")
    for o in clean:
        mark = "✗ FALSE-POS" if o.fired else "✓"
        lines.append(f"[{mark}] ({o.group}) {o.query}")
        if o.fired:
            lines.append(f"      wrongly flagged: {o.result.questionable}")

    lines.append(
        f"\ndetection rate (loaded): {summary['detection_rate']:.0%} "
        f"({summary['detected']}/{summary['loaded_count']})  |  "
        f"false-positive rate (clean): {summary['false_positive_rate']:.0%} "
        f"({summary['false_positives']}/{summary['clean_count']})"
    )
    lines.append("  detection by category:")
    for cat, d in summary["detection_by_category"].items():
        lines.append(f"    {cat:8} {d['rate']:.0%} ({d['fired']}/{d['count']})")
    lines.append("  false-positive by kind:")
    for kind, d in summary["false_positive_by_kind"].items():
        lines.append(f"    {kind:9} {d['rate']:.0%} ({d['fired']}/{d['count']})")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Assumptions extractor evaluation")
    p.add_argument("--heldout", action="store_true",
                   help="run the held-out adversarial set (eval/assumptions_heldout.py) "
                        "instead of the main dataset — a generalization test")
    args = p.parse_args()

    if args.heldout:
        from eval.assumptions_heldout import CLEAN as HELD_CLEAN, LOADED as HELD_LOADED
        loaded, clean, summary = asyncio.run(run_eval(loaded_set=HELD_LOADED, clean_set=HELD_CLEAN))
    else:
        loaded, clean, summary = asyncio.run(run_eval())
    print(format_report(loaded, clean, summary))
