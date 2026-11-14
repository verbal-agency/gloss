"""The eval cache: a re-run pays only for what changed, and never reuses an
answer that something upstream has invalidated."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from app import llm
from eval import cache, proposals_eval, proxy_eval


@pytest.fixture
def on(tmp_path):
    cache.configure(enabled=True, directory=tmp_path)
    yield tmp_path
    cache.configure(enabled=False, directory="results/.cache")


async def test_off_by_default_and_touches_no_disk(tmp_path):
    assert cache.ENABLED is False
    run = AsyncMock(return_value="v")
    assert await cache.get_or_run("answer", {"k": 1}, run) == "v"
    assert await cache.get_or_run("answer", {"k": 1}, run) == "v"
    assert run.call_count == 2 and cache.report() == "cache: off"


async def test_second_call_with_the_same_inputs_is_reused(on):
    run = AsyncMock(return_value={"text": "v"})
    assert await cache.get_or_run("answer", {"model": "m", "prompt": "p"}, run) == {"text": "v"}
    assert await cache.get_or_run("answer", {"model": "m", "prompt": "p"}, run) == {"text": "v"}
    assert run.call_count == 1
    assert cache.stats == {"hits": 1, "misses": 1}
    assert "1 reused, 1 new call(s)" in cache.report()


@pytest.mark.parametrize("changed", [
    {"model": "other"}, {"prompt": "different"}, {"system": "an instruction"}, {"max_tokens": 9},
])
async def test_any_change_to_the_inputs_is_a_new_call(on, changed):
    base = {"model": "m", "prompt": "p", "system": None, "max_tokens": 8000}
    run = AsyncMock(return_value="v")
    await cache.get_or_run("answer", base, run)
    await cache.get_or_run("answer", {**base, **changed}, run)
    assert run.call_count == 2


async def test_fresh_ignores_stored_entries_and_overwrites_them(on):
    await cache.get_or_run("answer", {"p": 1}, AsyncMock(return_value="old"))
    cache.configure(enabled=True, fresh=True, directory=on)
    assert await cache.get_or_run("answer", {"p": 1}, AsyncMock(return_value="new")) == "new"
    cache.configure(enabled=True, directory=on)
    untouched = AsyncMock(return_value="never")
    assert await cache.get_or_run("answer", {"p": 1}, untouched) == "new"
    untouched.assert_not_called()


async def test_a_failed_call_stores_nothing(on):
    with pytest.raises(RuntimeError):
        await cache.get_or_run("answer", {"p": 1}, AsyncMock(side_effect=RuntimeError("boom")))
    assert await cache.get_or_run("answer", {"p": 1}, AsyncMock(return_value="ok")) == "ok"


async def test_direct_and_instructed_answers_are_keyed_apart(on):
    chat = AsyncMock(side_effect=["plain", "instructed"])
    with patch("eval.proxy_eval.llm.chat", chat), patch("eval.proposals_eval.llm.chat", chat):
        assert await proxy_eval._direct("same prompt", "m") == "plain"
        assert await proposals_eval._instructed("same prompt", "m") == "instructed"
        assert await proxy_eval._direct("same prompt", "m") == "plain"         # reused
        assert await proposals_eval._instructed("same prompt", "m") == "instructed"
    assert chat.call_count == 2


async def test_pipeline_answers_are_invalidated_when_the_pipeline_changes(on):
    calls = []

    async def fake_process(request, session_id):
        calls.append(1)
        return SimpleNamespace(content=[SimpleNamespace(text="y")],
                               meta=SimpleNamespace(normalized_query=None, signals_removed=[], assumptions=None))

    with patch("eval.proxy_eval.process", AsyncMock(side_effect=fake_process)):
        with patch("eval.cache.pipeline_fingerprint", return_value="v1"):
            assert await proxy_eval._through_proxy("q", "m") == ("y", {
                "normalized_query": None, "signals_removed": [], "assumptions": None})
            await proxy_eval._through_proxy("q", "m")                  # same pipeline: reused
            await proxy_eval._through_proxy("q", "m", action="ground")  # a different mode: new
        with patch("eval.cache.pipeline_fingerprint", return_value="v2"):
            await proxy_eval._through_proxy("q", "m")                  # pipeline changed: new
    assert len(calls) == 3


def test_pipeline_fingerprint_follows_settings(monkeypatch):
    from app.config import settings
    before = cache.pipeline_fingerprint()
    monkeypatch.setattr(settings, "assumption_action", "ground")
    assert cache.pipeline_fingerprint() != before


async def test_judges_run_at_low_effort_and_the_effort_is_part_of_the_key(on):
    seen = []

    async def fake_json(messages, **kwargs):
        seen.append(kwargs.get("effort"))
        return {"reasoning": "r", "objected": False, "built": True, "asks": False}

    sound = next(p for p in proposals_eval.load() if not p.flaw)
    with patch("app.llm.chat_json", AsyncMock(side_effect=fake_json)):
        assert proposals_eval.JUDGE_EFFORT == "low"
        await proposals_eval._judge(sound, "a response", "judge")
        await proposals_eval._judge(sound, "a response", "judge")      # reused
        with patch.object(proposals_eval, "JUDGE_EFFORT", None):
            await proposals_eval._judge(sound, "a response", "judge")  # different effort: new
    assert seen == ["low", None]


# ---------------------------------------------------------------------------
# effort in the model wrapper
# ---------------------------------------------------------------------------

def _ok(text="hi"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


async def test_effort_is_sent_as_output_config(monkeypatch):
    monkeypatch.setattr(llm, "_NO_EFFORT", set())
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return _ok()

    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=fake)):
        await llm.chat([{"role": "user", "content": "x"}], model="anthropic/new", effort="low")
        await llm.chat([{"role": "user", "content": "x"}], model="anthropic/new")
    assert calls[0]["output_config"] == {"effort": "low"}
    assert "output_config" not in calls[1]


async def test_a_model_that_refuses_effort_is_retried_without_it_and_remembered(monkeypatch):
    monkeypatch.setattr(llm, "_NO_EFFORT", set())
    monkeypatch.setattr(llm, "_NO_TEMPERATURE", set())
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        if "output_config" in kwargs:
            raise litellm.BadRequestError(message="This model does not support the effort parameter.",
                                          model="m", llm_provider="anthropic")
        if "temperature" in kwargs:
            raise litellm.BadRequestError(message="`temperature` is deprecated for this model.",
                                          model="m", llm_provider="anthropic")
        return _ok()

    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=fake)):
        # refuses both in turn; the third attempt succeeds
        assert await llm.chat([{"role": "user", "content": "x"}], model="anthropic/old",
                              effort="low", temperature=0.0) == "hi"
        assert await llm.chat([{"role": "user", "content": "x"}], model="anthropic/old",
                              effort="low", temperature=0.0) == "hi"
    assert len(calls) == 4                                   # 3 for the first call, 1 for the second
    assert "output_config" not in calls[-1] and "temperature" not in calls[-1]
