"""G43 (E6/E7): the held-out run. Spec: docs/v3_spike.md, "E6".

Only the first step exists so far. The arms and the summary are E7, and are
added after the E7 plan (questions, thresholds, decision rule) is fixed on dev.

    python -m eval.g43_eval --record        # G43 histories, once, after the owner's review
    python -m eval.g43_eval --record-g44    # G44 (late-flaw) histories, once, after its review

The histories are the unaided model's answers to each conversation's earlier
turns. They are recorded once and frozen; they do not depend on any classifier
choice, so recording them before E7's plan is fixed does not spend the test set.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from eval import g41_eval as g41
from eval import g43_heldout as h
from eval import g44_heldout as h44

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


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m eval.g43_eval")
    ap.add_argument("--record", action="store_true", help="record and freeze the conversation histories")
    ap.add_argument("--record-g44", action="store_true", help="record and freeze the G44 histories")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args(argv)
    if args.record:
        asyncio.run(record(args.concurrency))
    elif args.record_g44:
        asyncio.run(record_g44(args.concurrency))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
