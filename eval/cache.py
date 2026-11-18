"""On-disk cache for eval calls, so a re-run pays only for what changed.

Every eval run used to regenerate every answer and every judge verdict, even
when one arm out of five had changed. Answers and verdicts are now keyed on
everything that determines them (model, system prompt, user prompt, output
budget, effort; for the pipeline arm, a fingerprint of the pipeline's source and
settings) and stored as JSON under results/.cache/, which is git-ignored.

Off unless a CLI turns it on, so library use and tests never touch the disk.

Trade-off: a cached re-run shows no run-to-run variation. Use `--fresh` when
the point of the run is to see noise; it ignores stored entries and overwrites
them.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

ENABLED = False
FRESH = False
DIR = Path("results/.cache")
stats = {"hits": 0, "misses": 0}


def configure(enabled: bool, fresh: bool = False, directory: str | Path | None = None) -> None:
    global ENABLED, FRESH, DIR
    ENABLED, FRESH = enabled, fresh
    if directory is not None:
        DIR = Path(directory)
    stats["hits"] = stats["misses"] = 0


def _key(kind: str, parts: dict) -> str:
    blob = json.dumps({"kind": kind, **parts}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def get_or_run(kind: str, parts: dict, run: Callable[[], Awaitable[Any]]) -> Any:
    """Return the stored value for (kind, parts), or run `run()` and store it.
    The value must be JSON-serializable. A failed `run()` stores nothing."""
    if not ENABLED:
        return await run()
    path = DIR / kind / f"{_key(kind, parts)}.json"
    if not FRESH and path.exists():
        stats["hits"] += 1
        return json.loads(path.read_text())["value"]
    value = await run()
    stats["misses"] += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"kind": kind, "parts": parts, "value": value},
                               ensure_ascii=False, default=str))
    return value


_SOURCE_HASH: str | None = None


def pipeline_fingerprint() -> str:
    """Changes whenever the Gloss pipeline's code or relevant settings change,
    so answers produced by an older pipeline are never reused."""
    global _SOURCE_HASH
    from app.config import settings
    if _SOURCE_HASH is None:
        root = Path(__file__).resolve().parent.parent / "app"
        h = hashlib.sha256()
        for f in sorted(root.rglob("*.py")):
            h.update(f.read_bytes())
        _SOURCE_HASH = h.hexdigest()
    relevant = {k: getattr(settings, k) for k in (
        "litellm_model", "judge_model", "ground_model", "ground_backend", "jev_model",
        "assumption_action", "gloss_mode",
        "tier_normalization", "tier_assumption", "tier_counterfactual", "tier_precommitment",
        "tier_disagreement", "tier_temporal")}
    return hashlib.sha256((_SOURCE_HASH + json.dumps(relevant, sort_keys=True, default=str))
                          .encode()).hexdigest()[:16]


async def judge_json(messages: list[dict], model: str, schema, effort: str | None = None) -> dict:
    """A cached judge call returning schema-validated JSON."""
    from app import llm
    return await get_or_run(
        "judge", {"model": model, "messages": messages, "schema": schema.__name__, "effort": effort},
        lambda: llm.chat_json(messages, model=model, schema=schema, effort=effort))


def report() -> str:
    total = stats["hits"] + stats["misses"]
    if not ENABLED:
        return "cache: off"
    return (f"cache: {stats['hits']} reused, {stats['misses']} new call(s)"
            + (" (fresh run: stored entries ignored)" if FRESH else "")
            + (f", {stats['hits'] / total:.0%} reused" if total else ""))
