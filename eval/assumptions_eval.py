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

Live run (spends ~55 judge-model calls):    `python -m eval.assumptions_eval`
Frame-delta (~220 calls):                   `python -m eval.assumptions_eval --frame-delta`
Head-to-head both detectors (~275 calls):   `python -m eval.assumptions_eval --both`
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable

from dotenv import load_dotenv

from app.pipeline import assumptions
from app.pipeline.assumptions import AssumptionResult
from eval.assumptions_dataset import CLEAN, LOADED

load_dotenv()  # push .env keys into the environment where litellm reads them (matches eval/runner.py)

Detector = Callable[[str], Awaitable[AssumptionResult]]


@dataclass
class QueryOutcome:
    query: str
    result: AssumptionResult
    group: str                    # category (loaded: factual|framing) or kind (clean: near_miss|neutral)
    intended: str | None = None   # the premise we hoped to surface (loaded only)

    @property
    def fired(self) -> bool:
        return bool(self.result.questionable)

    @property
    def magnitude(self) -> int | None:
        """Magnitude scalar from generate-and-compare (stored in reasoning as 'magnitude=N')."""
        r = self.result.reasoning
        if r.startswith("magnitude="):
            try:
                return int(r.split("=")[1])
            except (ValueError, IndexError):
                pass
        return None


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
    detector: Detector | None = None,
) -> tuple[list[QueryOutcome], list[QueryOutcome], dict]:
    detect = detector or (lambda q: assumptions.extract(q, model=model))
    loaded = [
        QueryOutcome(q, await detect(q), cat, intended=intended)
        for q, intended, cat in loaded_set
    ]
    clean = [
        QueryOutcome(q, await detect(q), kind)
        for q, kind in clean_set
    ]
    return loaded, clean, summarize(loaded, clean)


def _magnitude_dist(outcomes: list[QueryOutcome]) -> dict[int, int] | None:
    mags = [o.magnitude for o in outcomes if o.magnitude is not None]
    if not mags:
        return None
    dist: dict[int, int] = defaultdict(int)
    for m in mags:
        dist[m] += 1
    return dict(dist)


def format_report(loaded: list[QueryOutcome], clean: list[QueryOutcome], summary: dict,
                  label: str = "") -> str:
    header = f"=== {label + ' — ' if label else ''}LOADED (want questionable premise surfaced) ==="
    lines = [header]
    for o in loaded:
        mark = "✓" if o.fired else "✗ MISS"
        mag_str = f" [mag={o.magnitude}]" if o.magnitude is not None else ""
        lines.append(f"[{mark}{mag_str}] ({o.group}) {o.query}")
        lines.append(f"      intended: {o.intended}")
        lines.append(f"      flagged:  {o.result.questionable or '(none)'}")
    lines.append(f"\n=== {label + ' — ' if label else ''}CLEAN (want EMPTY questionable list) ===")
    for o in clean:
        mark = "✗ FALSE-POS" if o.fired else "✓"
        mag_str = f" [mag={o.magnitude}]" if o.magnitude is not None else ""
        lines.append(f"[{mark}{mag_str}] ({o.group}) {o.query}")
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

    loaded_dist = _magnitude_dist(loaded)
    clean_dist = _magnitude_dist(clean)
    if loaded_dist is not None or clean_dist is not None:
        lines.append("\n  magnitude distribution (0=same, 1=minor, 2=material↑, 3=fundamentally different):")
        lines.append("    threshold=2 means magnitude≥2 → flagged")
        if loaded_dist is not None:
            lines.append(f"    loaded: { {k: loaded_dist.get(k, 0) for k in range(4)} }")
        if clean_dist is not None:
            lines.append(f"    clean:  { {k: clean_dist.get(k, 0) for k in range(4)} }")

    return "\n".join(lines)


def format_head_to_head(
    h_loaded: list[QueryOutcome], h_clean: list[QueryOutcome], h_sum: dict,
    g_loaded: list[QueryOutcome], g_clean: list[QueryOutcome], g_sum: dict,
) -> str:
    lines = ["=" * 60, "HEAD-TO-HEAD: HOLISTIC vs GENERATE-AND-COMPARE", "=" * 60]
    rows = [
        ("detection rate",    f"{h_sum['detection_rate']:.0%} ({h_sum['detected']}/{h_sum['loaded_count']})",
                              f"{g_sum['detection_rate']:.0%} ({g_sum['detected']}/{g_sum['loaded_count']})"),
        ("false-positive",    f"{h_sum['false_positive_rate']:.0%} ({h_sum['false_positives']}/{h_sum['clean_count']})",
                              f"{g_sum['false_positive_rate']:.0%} ({g_sum['false_positives']}/{g_sum['clean_count']})"),
    ]
    all_cats = sorted({o.group for o in h_loaded} | {o.group for o in g_loaded})
    for cat in all_cats:
        hd = h_sum["detection_by_category"].get(cat, {})
        gd = g_sum["detection_by_category"].get(cat, {})
        rows.append((f"  detect/{cat}", f"{hd.get('rate', 0):.0%} ({hd.get('fired',0)}/{hd.get('count',0)})",
                                        f"{gd.get('rate', 0):.0%} ({gd.get('fired',0)}/{gd.get('count',0)})"))
    all_kinds = sorted({o.group for o in h_clean} | {o.group for o in g_clean})
    for kind in all_kinds:
        hk = h_sum["false_positive_by_kind"].get(kind, {})
        gk = g_sum["false_positive_by_kind"].get(kind, {})
        rows.append((f"  FP/{kind}", f"{hk.get('rate', 0):.0%} ({hk.get('fired',0)}/{hk.get('count',0)})",
                                     f"{gk.get('rate', 0):.0%} ({gk.get('fired',0)}/{gk.get('count',0)})"))
    col_w = max(len(r[0]) for r in rows) + 2
    lines.append(f"{'metric':<{col_w}}  {'HOLISTIC':>22}  {'FRAME-DELTA':>22}")
    lines.append("-" * (col_w + 48))
    for metric, h_val, g_val in rows:
        lines.append(f"{metric:<{col_w}}  {h_val:>22}  {g_val:>22}")

    g_loaded_dist = _magnitude_dist(g_loaded)
    g_clean_dist = _magnitude_dist(g_clean)
    if g_loaded_dist is not None or g_clean_dist is not None:
        lines.append("\nFRAME-DELTA magnitude distribution (threshold=2 → flagged):")
        lines.append("  0=same substance  1=minor  2=material↑  3=fundamentally different")
        if g_loaded_dist is not None:
            lines.append(f"  loaded: { {k: g_loaded_dist.get(k, 0) for k in range(4)} }")
        if g_clean_dist is not None:
            lines.append(f"  clean:  { {k: g_clean_dist.get(k, 0) for k in range(4)} }")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Assumptions extractor evaluation")
    p.add_argument("--heldout", action="store_true",
                   help="run the held-out adversarial set instead of the main dataset")
    p.add_argument("--frame-delta", action="store_true",
                   help="use the frame-delta detector (~4× calls per query)")
    p.add_argument("--both", action="store_true",
                   help="run holistic AND generate-and-compare head-to-head (implies spending both)")
    p.add_argument("--model", default=None, help="override judge model")
    args = p.parse_args()

    if args.heldout:
        from eval.assumptions_heldout import CLEAN as HELD_CLEAN, LOADED as HELD_LOADED
        lo_set, cl_set = HELD_LOADED, HELD_CLEAN
    else:
        lo_set, cl_set = LOADED, CLEAN

    def _holistic(q: str) -> Awaitable[AssumptionResult]:
        return assumptions.extract(q, model=args.model)

    def _frame_delta(q: str) -> Awaitable[AssumptionResult]:
        return assumptions.extract_frame_delta(q, model=args.model)

    if args.both:
        print("Running HOLISTIC detector...")
        h_loaded, h_clean, h_sum = asyncio.run(
            run_eval(loaded_set=lo_set, clean_set=cl_set, detector=_holistic))
        print("Running GENERATE-AND-COMPARE detector...")
        g_loaded, g_clean, g_sum = asyncio.run(
            run_eval(loaded_set=lo_set, clean_set=cl_set, detector=_frame_delta))
        print(format_report(h_loaded, h_clean, h_sum, label="HOLISTIC"))
        print()
        print(format_report(g_loaded, g_clean, g_sum, label="FRAME-DELTA"))
        print()
        print(format_head_to_head(h_loaded, h_clean, h_sum, g_loaded, g_clean, g_sum))
    elif args.frame_delta:
        loaded, clean, summary = asyncio.run(
            run_eval(loaded_set=lo_set, clean_set=cl_set, detector=_frame_delta))
        print(format_report(loaded, clean, summary, label="FRAME-DELTA"))
    else:
        loaded, clean, summary = asyncio.run(
            run_eval(loaded_set=lo_set, clean_set=cl_set, detector=_holistic))
        print(format_report(loaded, clean, summary))
