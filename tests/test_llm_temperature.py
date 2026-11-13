"""Newer models reject `temperature`; the wrapper drops it after the first refusal."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from app import llm


def _ok(text="hi"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _refusal():
    return litellm.BadRequestError(
        message="`temperature` is deprecated for this model.", model="m", llm_provider="anthropic")


async def test_retries_without_temperature_and_remembers(monkeypatch):
    monkeypatch.setattr(llm, "_NO_TEMPERATURE", set())
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        if "temperature" in kwargs:
            raise _refusal()
        return _ok()

    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=fake)):
        assert await llm.chat([{"role": "user", "content": "x"}], model="anthropic/new", temperature=0.0) == "hi"
        assert await llm.chat([{"role": "user", "content": "x"}], model="anthropic/new", temperature=0.0) == "hi"

    assert ["temperature" in c for c in calls] == [True, False, False]  # refused once, then never sent


async def test_other_bad_requests_still_raise(monkeypatch):
    monkeypatch.setattr(llm, "_NO_TEMPERATURE", set())
    err = litellm.BadRequestError(message="max_tokens too large", model="m", llm_provider="anthropic")
    with patch("app.llm.litellm.acompletion", AsyncMock(side_effect=err)):
        with pytest.raises(litellm.BadRequestError):
            await llm.chat([{"role": "user", "content": "x"}], model="anthropic/new", temperature=0.0)


def test_extract_json_tolerates_prose_around_the_object():
    text = 'The prompt signals no firm belief.\n\n{"view": ""}'
    assert llm._extract_json(text) == {"view": ""}
    assert llm._extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_still_raises_when_there_is_no_object():
    import json
    with pytest.raises(json.JSONDecodeError):
        llm._extract_json("no json here")
    with pytest.raises(json.JSONDecodeError):
        llm._extract_json("broken {not: json}")
