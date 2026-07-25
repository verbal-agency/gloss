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
