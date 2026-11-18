"""G33 — CLI interface for local testing.

Tests verify the wrapper behavior: output formatting, --no-redis store patching,
and --disable-tier settings suppression. The pipeline itself is not re-tested here
(covered by test_integration.py and companions); process() is mocked at the
app.cli import level to isolate the CLI layer.
"""
from __future__ import annotations
import argparse
import json
from unittest.mock import AsyncMock, patch

import app.store as _store_mod
from app.cli import _run, _TIERS
from app.config import settings
from app.models import (
    ContentBlock, MessagesResponse, ResponseMeta, SycophancyFlag, Usage,
)


def _response(*, text="Response text.", flags=None):
    return MessagesResponse(
        content=[ContentBlock(text=text)],
        model="test-model",
        usage=Usage(input_tokens=10, output_tokens=20),
        meta=ResponseMeta(
            session_id="cli-test",
            mode="observe",
            sycophancy_flags=flags or [],
        ),
    )


def _args(**kwargs):
    defaults = dict(
        query="Test query",
        model=None,
        mode=None,
        session=None,
        no_redis=False,
        disable_tier=None,
        verbose=False,
        action=None,
        history=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

async def test_basic_run_prints_response_text(capsys):
    with patch("app.cli.process", AsyncMock(return_value=_response())):
        await _run(_args())
    assert "Response text." in capsys.readouterr().out


async def test_unflagged_run_prints_no_flags_section(capsys):
    unflagged = SycophancyFlag(
        type="counterfactual_divergence", flagged=False, score=0.1,
        summary="Stable."
    )
    with patch("app.cli.process", AsyncMock(return_value=_response(flags=[unflagged]))):
        await _run(_args())
    assert "--- flags ---" not in capsys.readouterr().out


async def test_flagged_response_prints_flag_section(capsys):
    flag = SycophancyFlag(
        type="counterfactual_divergence", flagged=True, score=0.82,
        summary="Position reversed under opinion framing.",
    )
    with patch("app.cli.process", AsyncMock(return_value=_response(flags=[flag]))):
        await _run(_args())
    out = capsys.readouterr().out
    assert "--- flags ---" in out
    assert "counterfactual_divergence" in out
    assert "score=0.82" in out
    assert "Position reversed under opinion framing." in out


async def test_verbose_prints_meta_json(capsys):
    with patch("app.cli.process", AsyncMock(return_value=_response())):
        await _run(_args(verbose=True))
    out = capsys.readouterr().out
    assert "--- meta ---" in out
    meta_json = out.split("--- meta ---")[1].strip()
    parsed = json.loads(meta_json)
    assert parsed["session_id"] == "cli-test"


# ---------------------------------------------------------------------------
# --no-redis: store patching
# ---------------------------------------------------------------------------

async def test_no_redis_patches_store_during_process():
    """--no-redis replaces app.store functions with _MemStore methods during process."""
    seen = {}
    original_get = _store_mod.get_json

    async def _spy(req, sess):
        seen["get_json"] = _store_mod.get_json
        return _response()

    with patch("app.cli.process", _spy):
        await _run(_args(no_redis=True))

    assert seen["get_json"] is not original_get, "store.get_json should be patched during process"
    assert _store_mod.get_json is original_get, "store.get_json should be restored after _run"


async def test_no_redis_restores_all_store_functions_after_run():
    """All four store functions are restored after the run completes."""
    originals = {
        "get_json": _store_mod.get_json,
        "set_json": _store_mod.set_json,
        "rpush_json": _store_mod.rpush_json,
        "lrange_json": _store_mod.lrange_json,
    }
    with patch("app.cli.process", AsyncMock(return_value=_response())):
        await _run(_args(no_redis=True))

    for name, fn in originals.items():
        assert getattr(_store_mod, name) is fn, f"store.{name} not restored"


# ---------------------------------------------------------------------------
# --disable-tier: settings suppression
# ---------------------------------------------------------------------------

async def test_disable_tier_suppresses_setting_during_process():
    """--disable-tier counterfactual: settings.tier_counterfactual is False inside process."""
    captured = {}

    async def _spy(req, sess):
        captured["tier_cf"] = settings.tier_counterfactual
        return _response()

    with patch("app.cli.process", _spy):
        await _run(_args(disable_tier=["counterfactual"]))

    assert captured["tier_cf"] is False


async def test_disable_tier_restores_setting_after_run():
    """Settings flags are restored after _run — no bleed between calls."""
    original = settings.tier_normalization
    with patch("app.cli.process", AsyncMock(return_value=_response())):
        await _run(_args(disable_tier=["normalization"]))
    assert settings.tier_normalization == original


async def test_disable_multiple_tiers():
    """Multiple --disable-tier flags each suppress their tier."""
    captured = {}

    async def _spy(req, sess):
        captured["cf"] = settings.tier_counterfactual
        captured["pc"] = settings.tier_precommitment
        return _response()

    with patch("app.cli.process", _spy):
        await _run(_args(disable_tier=["counterfactual", "precommitment"]))

    assert captured["cf"] is False
    assert captured["pc"] is False
    assert settings.tier_counterfactual is True
    assert settings.tier_precommitment is True


# ---------------------------------------------------------------------------
# --action and --history: a live multi-turn trial of the grounding check
# ---------------------------------------------------------------------------

async def test_action_sets_the_assumption_action_only_during_the_run():
    captured = {}

    async def _spy(req, sess):
        captured["action"] = settings.assumption_action
        return _response()

    original = settings.assumption_action
    with patch("app.cli.process", _spy):
        await _run(_args(action="ground"))
    assert captured["action"] == "ground"
    assert settings.assumption_action == original


async def test_history_sends_earlier_turns_and_appends_this_one(tmp_path):
    path = tmp_path / "chat.json"
    captured = {}

    async def _spy(req, sess):
        captured["roles"] = [m.role for m in req.messages]
        return _response(text="Reply two.")

    path.write_text(json.dumps([{"role": "user", "content": "One"},
                                {"role": "assistant", "content": "Reply one."}]))
    with patch("app.cli.process", _spy):
        await _run(_args(query="Two", history=str(path)))
    assert captured["roles"] == ["user", "assistant", "user"]
    saved = json.loads(path.read_text())
    assert [t["content"] for t in saved] == ["One", "Reply one.", "Two", "Reply two."]


async def test_missing_history_file_starts_a_new_conversation(tmp_path):
    path = tmp_path / "new.json"
    with patch("app.cli.process", AsyncMock(return_value=_response(text="Hi."))):
        await _run(_args(query="Start", history=str(path)))
    assert [t["role"] for t in json.loads(path.read_text())] == ["user", "assistant"]


async def test_malformed_history_is_refused(tmp_path):
    import pytest
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"role": "user", "content": "One"}]))
    with patch("app.cli.process", AsyncMock(return_value=_response())):
        with pytest.raises(SystemExit):
            await _run(_args(history=str(path)))


async def test_grounding_decision_is_printed(capsys):
    from app.models import AssumptionDisclosure as AssumptionsFound
    resp = _response(text="What makes you think that is the cause?")
    resp.meta.assumptions = AssumptionsFound(
        questionable=[], reasoning="", action="asked", request="fix", link="absent")
    with patch("app.cli.process", AsyncMock(return_value=resp)):
        await _run(_args())
    out = capsys.readouterr().out
    assert "grounding check: asked (request=fix, link=absent)" in out
