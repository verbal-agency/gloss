import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.precommitment import run, classify_domain


def test_domain_classification():
    assert classify_domain("Should I take ibuprofen for a fever?") == "medical"
    assert classify_domain("Is this SQL query safe from injection?") == "technical"
    assert classify_domain("Should I invest in index funds?") == "financial"
    assert classify_domain("Can I break this contract?") == "legal"
    assert classify_domain("What time does the sun set?") == "general"


def test_domain_classification_word_boundaries():
    """G6 regressions: substrings must not match inside larger words."""
    assert classify_domain("Which author wrote this novel?") == "general"       # not "auth"
    assert classify_domain("What color should I paint my house?") == "general"  # not "pain"
    assert classify_domain("How rapid is the population growth?") == "general"  # not "api"


def test_domain_classification_hit_count_beats_dict_order():
    """'risks' alone is financial, but two technical hits must win."""
    assert classify_domain("What are the security risks of this architecture?") == "technical"


def test_domain_classification_plurals_and_expanded_keywords():
    assert classify_domain("Are these investments safe?") == "financial"
    assert classify_domain("How should authentication tokens be stored?") == "technical"
    assert classify_domain("Is this database scalable?") == "technical"


@pytest.mark.asyncio
async def test_flags_inconsistency():
    criteria = "Medical claims require RCT evidence, replication, and absence of conflicts of interest."
    judge_result = {
        "consistent": False,
        "dropped_standards": ["RCT evidence requirement", "conflict of interest check"],
        "score": 0.3,
        "reasoning": "Response endorsed an anecdote without applying stated evidentiary standards.",
    }

    with (
        patch("app.pipeline.precommitment.store.get_json", AsyncMock(return_value={"criteria": criteria})),
        patch("app.pipeline.precommitment.llm.chat", AsyncMock(return_value="That sounds right to me!")),
        patch("app.pipeline.precommitment.llm.chat_json", AsyncMock(return_value=judge_result)),
    ):
        result = await run(
            query="I'm certain this supplement cures inflammation. Is it effective?",
            conversation_messages=[{"role": "user", "content": "I'm certain this supplement cures inflammation. Is it effective?"}],
            domain="medical",
            session_id="test-session",
        )

    assert result.flagged is True
    assert result.consistency_score == 0.3
    assert "RCT evidence requirement" in result.dropped_standards


@pytest.mark.asyncio
async def test_criteria_cache_shared_across_sessions():
    """G13: criteria are domain-generic — a second request with a DIFFERENT
    (generated) session id must hit the cache, paying zero extraction calls."""
    storage: dict = {}

    async def fake_get(key):
        return storage.get(key)

    async def fake_set(key, value, ttl_seconds=86400):
        storage[key] = value

    extraction_calls = []

    async def fake_chat(messages, **kwargs):
        if "Before I ask my question" in messages[-1]["content"]:
            extraction_calls.append(messages)
            return "Criteria: RCT evidence, replication."
        return "a response"

    judge = {"consistent": True, "dropped_standards": [], "score": 1.0, "reasoning": "ok"}
    msgs = [{"role": "user", "content": "Is this supplement effective?"}]

    with (
        patch("app.pipeline.precommitment.store.get_json", AsyncMock(side_effect=fake_get)),
        patch("app.pipeline.precommitment.store.set_json", AsyncMock(side_effect=fake_set)),
        patch("app.pipeline.precommitment.llm.chat", AsyncMock(side_effect=fake_chat)),
        patch("app.pipeline.precommitment.llm.chat_json", AsyncMock(return_value=judge)),
    ):
        await run(query="q", conversation_messages=msgs, domain="medical", session_id="sess-a")
        await run(query="q", conversation_messages=msgs, domain="medical", session_id="sess-b")

    assert len(extraction_calls) == 1, "second session should hit the shared criteria cache"

    # Key is domain-only — no session fragment
    assert "criteria:medical" in storage
    assert not any(k.startswith("session:") for k in storage), f"session-scoped key found: {list(storage)}"
