"""G17: per-request LLM-call budget — caps the ~11x fan-out so a client can't
amplify cost/load without limit. Exceed -> 429."""
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import app.llm as llm
from app.config import settings


async def _fake_acompletion(**kwargs):
    class _M:
        class choices_0:
            class message:
                content = "ok"
        choices = [choices_0]
    return _M()


# ---------------------------------------------------------------------------
# The budget mechanism
# ---------------------------------------------------------------------------

async def test_budget_trips_after_cap(monkeypatch):
    monkeypatch.setattr(settings, "max_llm_calls_per_request", 2)
    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=_fake_acompletion)):
        llm.reset_call_budget()
        await llm.chat([{"role": "user", "content": "1"}])   # 1
        await llm.chat([{"role": "user", "content": "2"}])   # 2 (at cap)
        with pytest.raises(llm.CallBudgetExceeded):
            await llm.chat([{"role": "user", "content": "3"}])  # 3 -> over


async def test_budget_counts_concurrent_gather_calls(monkeypatch):
    """The mutable-holder-in-ContextVar trick: calls made inside asyncio.gather
    (which copies the context per task) must still share one counter."""
    monkeypatch.setattr(settings, "max_llm_calls_per_request", 3)
    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=_fake_acompletion)):
        llm.reset_call_budget()
        with pytest.raises(llm.CallBudgetExceeded):
            await asyncio.gather(*[
                llm.chat([{"role": "user", "content": str(i)}]) for i in range(5)
            ])


async def test_budget_resets_per_request(monkeypatch):
    """Two sequential requests each get a fresh budget — no leak via the ContextVar."""
    monkeypatch.setattr(settings, "max_llm_calls_per_request", 2)
    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=_fake_acompletion)):
        llm.reset_call_budget()
        await llm.chat([{"role": "user", "content": "a"}])
        await llm.chat([{"role": "user", "content": "b"}])
        # New request: reset -> counter starts at 0 again, so 2 more succeed
        llm.reset_call_budget()
        await llm.chat([{"role": "user", "content": "c"}])
        await llm.chat([{"role": "user", "content": "d"}])  # would fail without reset


async def test_cap_zero_disables_budget(monkeypatch):
    monkeypatch.setattr(settings, "max_llm_calls_per_request", 0)
    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=_fake_acompletion)):
        llm.reset_call_budget()
        for i in range(50):
            await llm.chat([{"role": "user", "content": str(i)}])  # never trips


async def test_unbudgeted_when_never_reset(monkeypatch):
    """Composable stage endpoints don't reset -> no budget enforced."""
    monkeypatch.setattr(settings, "max_llm_calls_per_request", 1)
    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=_fake_acompletion)):
        llm._budget.set(None)  # simulate "no reset window"
        for i in range(5):
            await llm.chat([{"role": "user", "content": str(i)}])  # unbudgeted, fine


# ---------------------------------------------------------------------------
# Endpoint maps CallBudgetExceeded -> 429
# ---------------------------------------------------------------------------

async def test_endpoint_returns_429_on_budget_exceeded():
    import httpx
    from app.main import app
    from app.llm import CallBudgetExceeded

    async def boom(request, session_id):
        raise CallBudgetExceeded(20)

    with patch("app.main.process", AsyncMock(side_effect=boom)):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/v1/messages", json={
                "model": "claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "hi"}],
            })
    assert r.status_code == 429
    body = r.json()
    assert body["error"]["type"] == "rate_limit_error"
