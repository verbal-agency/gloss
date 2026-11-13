"""G36: the grounding check (ASSUMPTION_ACTION=ground) — quiet when the message
links the plan to the cause, one question when it does not, objection first
when the message's own facts contradict the plan."""
from __future__ import annotations
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from app import llm
from app.config import settings
from app.middleware import ASSUMPTION_ACTION_OVERRIDE, process
from app.models import Message, MessagesRequest
from app.pipeline import assumptions
from app.pipeline.assumptions import GroundResult

_PROMPT = "Our page is slow. I've decided to migrate to Svelte. Can you outline the phases?"


async def _run(ground, *, action="ground", override=None, system=None, premise=("a doubtful premise",)):
    """Run the middleware with only the assumption tier on. `ground` is what the
    classifier returns (a GroundResult, or an exception to raise). Returns
    (response, messages the answering model saw, classifier mock, extractor mock)."""
    chat_received: list[list[dict]] = []

    async def fake_chat(messages, **kwargs):
        chat_received.append(messages)
        return "model response"

    classify = AsyncMock(side_effect=ground) if isinstance(ground, Exception) else AsyncMock(return_value=ground)
    extract = AsyncMock(return_value=assumptions.AssumptionResult(
        premises=[], questionable=list(premise), reasoning="r", reposed_query=None))
    with ExitStack() as stack:
        for tier in ("tier_counterfactual", "tier_precommitment", "tier_disagreement", "tier_temporal"):
            stack.enter_context(patch.object(settings, tier, False))
        stack.enter_context(patch.object(settings, "assumption_action", action))
        stack.enter_context(patch("app.llm.chat", AsyncMock(side_effect=fake_chat)))
        stack.enter_context(patch("app.llm.chat_json", AsyncMock(
            return_value={"normalized": _PROMPT, "signals_removed": [], "was_modified": False})))
        stack.enter_context(patch("app.pipeline.assumptions.classify_grounding", classify))
        stack.enter_context(patch("app.pipeline.assumptions.extract", extract))
        token = ASSUMPTION_ACTION_OVERRIDE.set(override)
        try:
            response = await process(
                MessagesRequest(model="claude-sonnet-4-6", system=system,
                                messages=[Message(role="user", content=_PROMPT)]), "sess-ground")
        finally:
            ASSUMPTION_ACTION_OVERRIDE.reset(token)
    return response, chat_received[-1], classify, extract


def _system(messages):
    return "\n".join(m["content"] for m in messages if m["role"] == "system")


def _g(request, link, **kw):
    return GroundResult(request=request, link=link, reasoning="because", **kw)


@pytest.mark.parametrize("request_kind,link,expected", [
    ("fix", "stated", "none"),          # the user said what causes it: stay quiet
    ("fix", "absent", "asked"),         # symptom + plan, no cause: ask
    ("fix", "contradicted", "objected"),
    ("task", "stated", "none"),
    ("task", "absent", "none"),         # a task has no cause to ask about
    ("task", "contradicted", "objected"),  # the plan cannot meet a stated requirement
    ("other", "stated", "none"),
])
def test_action_for_each_classifier_outcome(request_kind, link, expected):
    assert _g(request_kind, link).action == expected


async def test_quiet_when_the_link_is_stated_and_nothing_is_questionable():
    response, messages, classify, extract = await _run(
        _g("fix", "stated", evidence="Profiling shows X."), premise=())
    assert _system(messages) == ""                      # nothing added to the prompt
    assert [m["content"] for m in messages if m["role"] == "user"] == [_PROMPT]
    found = response.meta.assumptions
    assert (found.action, found.request, found.link) == ("none", "fix", "stated")
    assert found.evidence == "Profiling shows X." and found.questionable == []
    extract.assert_called_once()                        # the premise check is the fall-through


async def test_falls_through_to_the_premise_check_when_it_neither_asks_nor_objects():
    """A flaw that takes engineering knowledge to see (hiding a button is not
    access control) is not a contradiction with the message's own words, so the
    grounding check stays out of it and the premise check raises it first."""
    response, messages, classify, extract = await _run(
        _g("task", "stated"), premise=("hiding the button does not restrict the endpoint",))
    assert "hiding the button does not restrict the endpoint" in _system(messages)
    assert "Do not build anything yet" not in _system(messages)
    found = response.meta.assumptions
    assert (found.action, found.request, found.link) == ("annotated", "task", "stated")


async def test_asking_and_objecting_skip_the_premise_check():
    for ground in (_g("fix", "absent"), _g("fix", "contradicted", contradiction="c")):
        _, _, _, extract = await _run(ground)
        extract.assert_not_called()


async def test_asks_one_question_when_the_link_is_absent():
    response, messages, *_ = await _run(_g("fix", "absent"), system="Be concise.")
    systems = [m for m in messages if m["role"] == "system"]
    assert len(systems) == 1 and systems[0]["content"].startswith("Be concise.")
    assert "Do not build anything yet" in systems[0]["content"]
    assert "Ask one short question" in systems[0]["content"]
    assert [m["content"] for m in messages if m["role"] == "user"] == [_PROMPT]   # question never rewritten
    assert response.meta.assumptions.action == "asked"


async def test_objects_first_when_the_facts_contradict_the_plan():
    response, messages, *_ = await _run(
        _g("fix", "contradicted", contradiction="the time is in the database query, not the bundle"))
    assert "the time is in the database query, not the bundle" in _system(messages)
    assert "Do not build anything yet" not in _system(messages)     # it objects, it does not withhold
    found = response.meta.assumptions
    assert found.action == "objected"
    assert found.questionable == ["the time is in the database query, not the bundle"]


async def test_malformed_classifier_output_passes_the_request_through():
    with patch("app.pipeline.assumptions.classify_grounding",
               AsyncMock(side_effect=llm.JsonParseError("not json"))):
        assert await assumptions.run_ground("q") is None
    # The classifier failing must not fail the request. It then behaves as the
    # default tier would: nothing added when the premise check finds nothing...
    response, messages, *_ = await _run(llm.JsonParseError("not json"), premise=())
    assert response.content[0].text == "model response"
    assert _system(messages) == "" and response.meta.assumptions is None
    # ...and the usual annotation when it finds something.
    response, messages, *_ = await _run(llm.JsonParseError("not json"))
    assert response.meta.assumptions.action == "annotated"
    assert response.meta.assumptions.request is None


async def test_default_mode_is_unchanged_and_never_calls_the_classifier():
    response, messages, classify, extract = await _run(_g("fix", "absent"), action="annotate")
    classify.assert_not_called()
    extract.assert_called_once()
    assert response.meta.assumptions.action == "annotated"
    assert "a doubtful premise" in _system(messages)


async def test_per_request_override_selects_ground_without_changing_the_setting():
    response, _, classify, extract = await _run(_g("fix", "absent"), action="annotate", override="ground")
    classify.assert_called_once()
    extract.assert_not_called()                         # it asked, so no fall-through
    assert response.meta.assumptions.action == "asked"
    assert settings.assumption_action == "annotate"


async def test_classifier_uses_ground_model_when_set(monkeypatch):
    monkeypatch.setattr(settings, "ground_model", "anthropic/strong")
    seen = {}

    async def fake_json(messages, **kwargs):
        seen.update(kwargs)
        return {"request": "fix", "link": "absent", "evidence": "", "contradiction": "", "reasoning": "r"}

    with patch("app.pipeline.assumptions.llm.chat_json", AsyncMock(side_effect=fake_json)):
        result = await assumptions.classify_grounding("q")
    assert seen["model"] == "anthropic/strong" and result.action == "asked"
