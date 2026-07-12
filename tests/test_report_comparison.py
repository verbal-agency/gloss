"""G15: model-comparison chart renders from synthetic summaries (no live calls)."""
from __future__ import annotations
from pathlib import Path
import pytest


def test_generate_comparison_renders(tmp_path):
    pytest.importorskip("matplotlib")
    from eval.report import generate_comparison
    summaries = [
        {"model": "anthropic/claude-x", "sycophancy_rate": 0.30, "priming_induced_error_rate": 0.18},
        {"model": "openai/gpt-y", "sycophancy_rate": 0.45, "priming_induced_error_rate": 0.25},
    ]
    path = generate_comparison(summaries, tmp_path)
    assert Path(path).exists()


def test_generate_comparison_without_accuracy(tmp_path):
    pytest.importorskip("matplotlib")
    from eval.report import generate_comparison
    # divergence-only runs (no priming_induced_error_rate) must still render
    summaries = [
        {"model": "a", "sycophancy_rate": 0.3},
        {"model": "b", "sycophancy_rate": 0.4},
    ]
    assert Path(generate_comparison(summaries, tmp_path)).exists()
