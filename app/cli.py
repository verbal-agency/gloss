"""G33 — Gloss CLI: run the full pipeline in-process, no HTTP server required.

Usage:
    python -m app.cli "Your query here" [options]

    --model MODEL           LiteLLM model string (default: settings.litellm_model)
    --mode observe|enforce  Response mode (default: settings.gloss_mode)
    --session SESSION_ID    Session ID for multi-turn continuity (default: random)
    --no-redis              Use an in-memory store; no Redis connection required
    --disable-tier TIER     Disable a pipeline tier (repeatable)
    --verbose               Print full meta JSON after the response
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from collections import defaultdict
from contextlib import ExitStack
from unittest.mock import patch

from app.config import settings
from app.middleware import process
from app.models import Message, MessagesRequest


class _MemStore:
    """In-memory store stub implementing the app.store interface (no Redis)."""

    def __init__(self):
        self._kv: dict = {}
        self._lists: dict = defaultdict(list)

    async def get_json(self, key):
        return self._kv.get(key)

    async def set_json(self, key, value, ttl_seconds=86400):
        self._kv[key] = value

    async def rpush_json(self, key, value, ttl_seconds=86400):
        self._lists[key].append(value)

    async def lrange_json(self, key):
        return list(self._lists[key])


_TIERS = {
    "normalization": "tier_normalization",
    "assumption": "tier_assumption",
    "counterfactual": "tier_counterfactual",
    "precommitment": "tier_precommitment",
    "disagreement": "tier_disagreement",
    "temporal": "tier_temporal",
}


async def _run(args: argparse.Namespace) -> None:
    import app.store as _store_mod

    model = args.model or settings.litellm_model
    session_id = args.session or f"cli-{uuid.uuid4().hex[:8]}"
    request = MessagesRequest(
        model=model,
        messages=[Message(role="user", content=args.query)],
    )

    ctx = []
    if args.mode:
        ctx.append(patch.object(settings, "gloss_mode", args.mode))
    for tier in args.disable_tier or []:
        ctx.append(patch.object(settings, _TIERS[tier], False))
    if args.no_redis:
        mem = _MemStore()
        ctx += [
            patch.object(_store_mod, "get_json", mem.get_json),
            patch.object(_store_mod, "set_json", mem.set_json),
            patch.object(_store_mod, "rpush_json", mem.rpush_json),
            patch.object(_store_mod, "lrange_json", mem.lrange_json),
        ]

    with ExitStack() as stack:
        for p in ctx:
            stack.enter_context(p)
        response = await process(request, session_id)
        await asyncio.sleep(0.05)  # let background temporal extraction finish within patch scope

    _print_response(response, verbose=args.verbose)


def _print_response(response, *, verbose: bool) -> None:
    print(response.content[0].text)
    fired = [f for f in response.meta.sycophancy_flags if f.flagged]
    if fired:
        print("\n--- flags ---")
        for f in fired:
            print(f"[{f.type}  score={f.score:.2f}]  {f.summary}")
    if verbose:
        print("\n--- meta ---")
        print(json.dumps(response.meta.model_dump(), indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Run the Gloss sycophancy-detection pipeline locally.",
    )
    ap.add_argument("query", help="User query to process through the pipeline")
    ap.add_argument("--model", help="LiteLLM model string (default: settings.litellm_model)")
    ap.add_argument("--mode", choices=["observe", "enforce"],
                    help="Response mode (default: settings.gloss_mode)")
    ap.add_argument("--session",
                    help="Session ID for multi-turn continuity (default: random)")
    ap.add_argument("--no-redis", dest="no_redis", action="store_true",
                    help="Use an in-memory store; no Redis connection required")
    ap.add_argument("--disable-tier", dest="disable_tier", metavar="TIER",
                    action="append", choices=list(_TIERS),
                    help="Disable a pipeline tier (repeatable). Choices: "
                         + ", ".join(_TIERS))
    ap.add_argument("--verbose", action="store_true",
                    help="Print full meta JSON after the response")
    asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    main()
