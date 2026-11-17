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


# --------------------------------------------------------------------------- G37: the conversation in view

_OK = {"request": "fix", "link": "absent", "evidence": "", "contradiction": "", "reasoning": "r"}
_CLEAN = {"premises": [], "questionable": [], "reasoning": "r", "reposed_query": None}


def test_a_single_message_has_no_conversation_view():
    assert assumptions.conversation_view([{"role": "user", "content": "q"}]) is None
    assert assumptions.conversation_view(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]) is None


def test_conversation_view_keeps_earlier_turns_in_order_and_marks_the_request():
    view = assumptions.conversation_view([
        {"role": "user", "content": "Our page is slow. I decided to add an index."},
        {"role": "assistant", "content": "Here is the size query."},
        {"role": "user", "content": "Can you write the migration?"},
    ])
    assert view.index("Our page is slow") < view.index("Here is the size query") < view.index("LATEST REQUEST")
    assert view.endswith("Can you write the migration?")
    assert "USER: Our page is slow" in view and "ASSISTANT: Here is the size query." in view


def test_long_assistant_turns_are_cut_but_user_turns_are_not():
    long_user, long_reply = "u" * 5000, "HEAD" + "x" * 5000 + "TAIL"
    view = assumptions.conversation_view([
        {"role": "user", "content": long_user}, {"role": "assistant", "content": long_reply},
        {"role": "user", "content": "next"}])
    assert long_user in view                       # the user's evidence is never cut
    assert long_reply not in view and "HEAD" in view and "TAIL" in view and "[...]" in view


async def test_single_message_classifier_call_is_exactly_as_before():
    seen = {}

    async def fake_json(messages, **kwargs):
        seen["messages"] = messages
        return _OK

    with patch("app.pipeline.assumptions.llm.chat_json", AsyncMock(side_effect=fake_json)):
        await assumptions.classify_grounding("q")
    assert seen["messages"] == [{"role": "system", "content": assumptions.GROUND_SYSTEM},
                                {"role": "user", "content": "q"}]


async def test_single_message_premise_check_call_is_exactly_as_before():
    seen = {}

    async def fake_json(messages, **kwargs):
        seen["messages"] = messages
        return _CLEAN

    with patch("app.pipeline.assumptions.llm.chat_json", AsyncMock(side_effect=fake_json)):
        await assumptions.extract("q")
    assert seen["messages"] == [{"role": "system", "content": assumptions.EXTRACT_SYSTEM},
                                {"role": "user", "content": "q"}]


async def test_with_a_conversation_both_checks_get_it_and_the_added_rule():
    seen = []

    async def fake_json(messages, **kwargs):
        seen.append(messages)
        return _OK if len(seen) == 1 else _CLEAN

    with patch("app.pipeline.assumptions.llm.chat_json", AsyncMock(side_effect=fake_json)):
        await assumptions.classify_grounding("latest", context="CONVERSATION SO FAR: ...")
        await assumptions.extract("latest", context="CONVERSATION SO FAR: ...")
    for messages, base in zip(seen, (assumptions.GROUND_SYSTEM, assumptions.EXTRACT_SYSTEM)):
        assert messages[0]["content"] == base + assumptions.CONVERSATION_RULE
        assert messages[1]["content"] == "CONVERSATION SO FAR: ..."
    assert "any earlier USER turn counts as stated" in assumptions.CONVERSATION_RULE


async def _run_conversation(action: str):
    classify = AsyncMock(return_value=_g("task", "stated"))
    extract = AsyncMock(return_value=assumptions.AssumptionResult(
        premises=[], questionable=[], reasoning="r", reposed_query=None))
    turns = [Message(role="user", content="Our page is slow. I decided to add an index. First, the size query?"),
             Message(role="assistant", content="SELECT pg_size_pretty(...)"),
             Message(role="user", content="Can you write the migration?")]
    with ExitStack() as stack:
        for tier in ("tier_counterfactual", "tier_precommitment", "tier_disagreement", "tier_temporal"):
            stack.enter_context(patch.object(settings, tier, False))
        stack.enter_context(patch.object(settings, "assumption_action", action))
        stack.enter_context(patch("app.llm.chat", AsyncMock(return_value="model response")))
        stack.enter_context(patch("app.llm.chat_json", AsyncMock(
            return_value={"normalized": "x", "signals_removed": [], "was_modified": False})))
        stack.enter_context(patch("app.pipeline.assumptions.classify_grounding", classify))
        stack.enter_context(patch("app.pipeline.assumptions.extract", extract))
        await process(MessagesRequest(model="claude-sonnet-4-6", messages=turns), "sess-late")
    return classify, extract


async def test_ground_mode_passes_the_earlier_turns_to_both_checks():
    classify, extract = await _run_conversation("ground")
    for mock in (classify, extract):
        assert mock.call_args.args[0] == "Can you write the migration?"
        context = mock.call_args.kwargs["context"]
        assert "I decided to add an index" in context and context.endswith("Can you write the migration?")


async def test_the_default_mode_still_reads_only_the_latest_message():
    classify, extract = await _run_conversation("annotate")
    classify.assert_not_awaited()
    assert extract.call_args.args[0] == "Can you write the migration?"
    assert extract.call_args.kwargs["context"] is None


async def test_ground_mode_on_a_single_message_passes_no_conversation():
    _, _, classify, extract = await _run(_g("task", "stated"))
    assert classify.call_args.kwargs["context"] is None
    assert extract.call_args.kwargs["context"] is None
