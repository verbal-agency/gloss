"""G27 spike harness — run the assumption extractor over the hand fixture and
report the two numbers that decide go/no-go on the v2 direction:

  - detection rate  (LOADED): fraction where a questionable premise WAS surfaced
                              — recall on queries that genuinely have one.
  - false-positive  (CLEAN):  fraction where a questionable premise was WRONGLY
                              surfaced — the faithfulness metric (must stay low).

Per-query output is printed so a human can eyeball whether the RIGHT premise was
caught (semantic matching is not automated — this is a probe, not a benchmark).

Live run (spends ~20 judge-model calls): `python -m eval.assumptions_spike`
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from dotenv import load_dotenv

from app.pipeline import assumptions
from app.pipeline.assumptions import AssumptionResult
from eval.assumptions_fixture import CLEAN, LOADED

load_dotenv()  # push .env keys into the environment where litellm reads them (matches eval/runner.py)


@dataclass
class QueryOutcome:
    query: str
    result: AssumptionResult
    intended: str | None = None  # the premise we hoped to surface (loaded only)

    @property
    def fired(self) -> bool:
        return bool(self.result.questionable)


def summarize(loaded: list[QueryOutcome], clean: list[QueryOutcome]) -> dict:
    """Pure metric computation — no I/O, no live calls (unit-testable)."""
    n_loaded = len(loaded) or 1
    n_clean = len(clean) or 1
    detected = sum(o.fired for o in loaded)
    false_pos = sum(o.fired for o in clean)
    return {
        "loaded_count": len(loaded),
        "clean_count": len(clean),
        "detection_rate": round(detected / n_loaded, 3),   # recall on loaded
        "false_positive_rate": round(false_pos / n_clean, 3),  # faithfulness
        "detected": detected,
        "false_positives": false_pos,
    }


async def run_spike(model: str | None = None) -> tuple[list[QueryOutcome], list[QueryOutcome], dict]:
    loaded = [
        QueryOutcome(q, await assumptions.extract(q, model=model), intended=premise)
        for q, premise in LOADED
    ]
    clean = [QueryOutcome(q, await assumptions.extract(q, model=model)) for q in CLEAN]
    return loaded, clean, summarize(loaded, clean)


def format_report(loaded: list[QueryOutcome], clean: list[QueryOutcome], summary: dict) -> str:
    lines = ["=== LOADED (want questionable premise surfaced) ==="]
    for o in loaded:
        mark = "✓" if o.fired else "✗ MISS"
        lines.append(f"[{mark}] {o.query}")
        lines.append(f"      intended: {o.intended}")
        lines.append(f"      flagged:  {o.result.questionable or '(none)'}")
    lines.append("\n=== CLEAN (want EMPTY questionable list) ===")
    for o in clean:
        mark = "✗ FALSE-POS" if o.fired else "✓"
        lines.append(f"[{mark}] {o.query}")
        if o.fired:
            lines.append(f"      wrongly flagged: {o.result.questionable}")
    lines.append(
        f"\ndetection rate (loaded): {summary['detection_rate']:.0%} "
        f"({summary['detected']}/{summary['loaded_count']})  |  "
        f"false-positive rate (clean): {summary['false_positive_rate']:.0%} "
        f"({summary['false_positives']}/{summary['clean_count']})"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    loaded, clean, summary = asyncio.run(run_spike())
    print(format_report(loaded, clean, summary))
