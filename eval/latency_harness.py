"""Latency/cost measurement harness — the source of the README's latency table.

Drives the real `process()` orchestrator with a constant-latency simulated LLM:
- upstream call counts are exact (the real pipeline structure executes)
- wall-clock multiples reflect sequential/parallel structure, free of provider variance

Run: python -m eval.latency_harness
"""
from __future__ import annotations
import asyncio
import time
from unittest.mock import AsyncMock

import numpy as np

from app import llm, store
from app.models import Message, MessagesRequest

UNIT = 0.20        # simulated seconds per LLM call
EMBED_UNIT = 0.05  # simulated seconds per embedding call

_counters = {"chat": 0, "chat_json": 0, "embed": 0}


def _reset() -> None:
    for k in _counters:
        _counters[k] = 0


async def _fake_chat(messages, **kwargs):
    _counters["chat"] += 1
    await asyncio.sleep(UNIT)
    return f"Simulated response #{_counters['chat']} with some substantive content."


async def _fake_chat_json(messages, **kwargs):
    _counters["chat_json"] += 1
    await asyncio.sleep(UNIT)
    system = messages[0]["content"]
    if "query preprocessor" in system:
        return {"normalized": messages[-1]["content"], "signals_removed": [], "was_modified": False}
    if "two variants" in system:
        return {"neutral": "neutral variant?", "inverted": "inverted variant?"}
    if "capitulated" in system:
        return {"classification": "HOLDS", "reasoning": "held"}
    if "Extract every factual claim" in system:
        return {"claims": ["claim one", "claim two"]}
    if "evaluation criteria" in system:
        return {"consistent": True, "dropped_standards": [], "score": 1.0, "reasoning": "ok"}
    if "drifted across a conversation" in system:
        return {"disappeared_claims": ["claim one"], "justified_by_new_info": False,
                "drift_score": 0.9, "reasoning": "unexplained drift"}
    raise AssertionError(f"unrouted chat_json system prompt: {system[:60]}")


async def _fake_embed(texts):
    _counters["embed"] += 1
    await asyncio.sleep(EMBED_UNIT)
    # Orthogonal embeddings -> maximal divergence -> worst-case (flagged) path
    return [np.eye(max(3, len(texts)))[i].tolist() for i in range(len(texts))]


_SIMILAR = {"turn": 1, "claims": ["claim one"], "embedding": [1.0, 0.0, 0.0],
            "user_message_preview": "u", "timestamp": 0.0}
_DRIFTED = {"turn": 5, "claims": ["claim two"], "embedding": [0.0, 1.0, 0.0],
            "user_message_preview": "u", "timestamp": 0.0}

_HISTORY = [Message(role="user", content="Tell me about the plan."),
            Message(role="assistant", content="It has risks."),
            Message(role="user", content="I hear you."),
            Message(role="assistant", content="Noted.")]


async def _run_scenario(name: str, content: str, history=None, snapshots=None) -> None:
    from app.middleware import process

    store.lrange_json = AsyncMock(return_value=snapshots or [])
    msgs = (history or []) + [Message(role="user", content=content)]
    request = MessagesRequest(model="claude-sonnet-4-6", messages=msgs)

    _reset()
    t0 = time.perf_counter()
    await process(request, f"sess-{name}")
    blocking_wall = time.perf_counter() - t0
    blocking = dict(_counters)
    await asyncio.sleep(UNIT * 2 + 0.1)  # let background extraction settle
    total = dict(_counters)

    bg_llm = (total["chat"] + total["chat_json"]) - (blocking["chat"] + blocking["chat_json"])
    llm_blocking = blocking["chat"] + blocking["chat_json"]
    print(f"{name:34s} | LLM calls: {llm_blocking:2d} blocking +{bg_llm:1d} bg "
          f"= {llm_blocking + bg_llm:2d} total | embed: {total['embed']} | "
          f"wall: {blocking_wall:.2f}s = {blocking_wall / UNIT:.1f}x baseline")


async def main() -> None:
    # Patch the LLM/store boundary; the real pipeline structure executes above it
    llm.chat = _fake_chat
    llm.chat_json = _fake_chat_json
    llm.embed = _fake_embed
    store.get_json = AsyncMock(return_value=None)
    store.set_json = AsyncMock()
    store.rpush_json = AsyncMock()

    print(f"baseline: single direct model call = 1 LLM call, 1.0x ({UNIT:.2f}s simulated)\n")
    await _run_scenario("neutral, general domain", "What is the boiling point of water?")
    await _run_scenario("high-stakes, no opinion (pc)", "Should I take ibuprofen for a fever?")
    await _run_scenario("opinion-primed, general (cf+dp)", "I'm convinced Rome fell in 476 AD. Right?")
    await _run_scenario("opinion + high-stakes (cf+pc+dp)",
                        "I'm convinced this supplement cures inflammation. Is it effective?")
    await _run_scenario("multi-turn, no drift", "And what about the timeline?",
                        history=_HISTORY, snapshots=[_SIMILAR, _SIMILAR])
    await _run_scenario("multi-turn, drift flagged", "And what about the timeline?",
                        history=_HISTORY, snapshots=[_SIMILAR, _DRIFTED])


if __name__ == "__main__":
    asyncio.run(main())
