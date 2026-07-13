from __future__ import annotations
from pathlib import Path


def generate(summary: dict, output_dir: Path) -> Path:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    results = summary["results"]
    domains = sorted(set(r["domain"] for r in results))
    domain_scores: dict[str, list[float]] = {d: [] for d in domains}
    for r in results:
        domain_scores[r["domain"]].append(r["divergence_score"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f"Sycophancy Eval — {summary['model']}", fontsize=13, fontweight="bold")

    # Chart 1: divergence score per question
    ax1 = axes[0]
    ids = [r["id"] for r in results]
    scores = [r["divergence_score"] for r in results]
    colors = ["#e05252" if r["flagged"] else "#5b9bd5" for r in results]
    bars = ax1.barh(ids, scores, color=colors)
    ax1.axvline(summary["threshold"], color="#333", linestyle="--", linewidth=1, label=f"Threshold ({summary['threshold']})")
    ax1.set_xlabel("Divergence score")
    ax1.set_title("Divergence by question")
    flagged_patch = mpatches.Patch(color="#e05252", label="Flagged (sycophantic)")
    clean_patch   = mpatches.Patch(color="#5b9bd5", label="Clean")
    ax1.legend(handles=[flagged_patch, clean_patch, ax1.lines[0]], fontsize=8)

    # Chart 2: sycophancy rate by domain
    ax2 = axes[1]
    domain_rates = []
    domain_labels = []
    for d in domains:
        d_results = [r for r in results if r["domain"] == d]
        rate = sum(1 for r in d_results if r["flagged"]) / len(d_results)
        domain_rates.append(rate)
        domain_labels.append(d)
    bar_colors = ["#e05252" if r > summary["threshold"] else "#5b9bd5" for r in domain_rates]
    ax2.bar(domain_labels, domain_rates, color=bar_colors)
    ax2.set_ylabel("Sycophancy rate")
    ax2.set_ylim(0, 1.05)
    ax2.set_title("Sycophancy rate by domain")
    for i, v in enumerate(domain_rates):
        ax2.text(i, v + 0.02, f"{v:.0%}", ha="center", fontsize=9)

    fig.text(
        0.5, 0.01,
        f"Overall: {summary['flagged_count']}/{summary['question_count']} flagged "
        f"({summary['sycophancy_rate']:.0%}) · mean divergence {summary['mean_divergence']:.4f}",
        ha="center", fontsize=10,
    )

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    chart_path = output_dir / "sycophancy_report.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    return chart_path


def generate_accuracy(summary: dict, output_dir: Path) -> Path | None:
    """Accuracy-by-framing chart. Returns None when the eval ran without
    ground-truth grading (no 'accuracy' key in the summary)."""
    accuracy = summary.get("accuracy")
    if not accuracy:
        return None

    import matplotlib.pyplot as plt

    framings = ["neutral", "agree", "disagree"]
    rates = [accuracy[f] for f in framings]
    labels = ["Neutral", "Agree-primed", "Disagree-primed"]
    colors = ["#5b9bd5", "#e0a052", "#e05252"]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(labels, rates, color=colors)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Accuracy vs. ground truth")
    ax.set_title(f"Accuracy by framing — {summary['model']}", fontweight="bold")
    for i, v in enumerate(rates):
        ax.text(i, v + 0.02, f"{v:.0%}", ha="center", fontsize=10)

    pier = summary.get("priming_induced_error_rate")
    if pier is not None:
        fig.text(
            0.5, 0.01,
            f"Priming-induced error rate: {pier:.0%} — correct when asked neutrally, "
            f"wrong under social pressure",
            ha="center", fontsize=10,
        )

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    chart_path = output_dir / "accuracy_report.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    return chart_path


def generate_divergence_breakdown(summary: dict, output_dir: Path) -> Path | None:
    """Raw vs. substantive divergence for one model — the shrinkage from the
    embedding screen to judge-confirmed shifts IS the phrasing-variance story.
    Returns None if the run didn't judge divergence (no substantive rate)."""
    if "substantive_divergence_rate" not in summary:
        return None

    import matplotlib.pyplot as plt

    raw = summary.get("sycophancy_rate", 0.0)
    sub = summary["substantive_divergence_rate"]
    labels = ["Raw divergence\n(embedding screen)", "Substantive\n(judge-confirmed)"]

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.bar(labels, [raw, sub], color=["#9db8d2", "#e05252"])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Flagged rate")
    ax.set_title(f"Divergence: screen vs. confirmed — {summary['model']}", fontweight="bold")
    for i, v in enumerate([raw, sub]):
        ax.text(i, v + 0.02, f"{v:.0%}", ha="center", fontsize=10)
    fig.text(0.5, 0.01,
             f"Gap = {(raw - sub):.0%} phrasing variance (false positives the raw metric would report)",
             ha="center", fontsize=9)

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    chart_path = output_dir / "divergence_breakdown.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    return chart_path


def generate_comparison(summaries: list[dict], output_dir: Path) -> Path:
    """Side-by-side model comparison: sycophancy rate and priming-induced error
    rate per model. `summaries` is a list of eval-run summary dicts."""
    import matplotlib.pyplot as plt
    import numpy as np

    models = [s["model"] for s in summaries]
    syco = [s.get("sycophancy_rate", 0.0) for s in summaries]
    # priming-induced error rate is present only when accuracy grading ran
    pier = [s.get("priming_induced_error_rate") for s in summaries]
    has_pier = all(p is not None for p in pier)

    x = np.arange(len(models))
    width = 0.38

    fig, ax = plt.subplots(figsize=(max(7, 2 * len(models)), 5))
    ax.bar(x - width / 2, syco, width, label="Sycophancy rate (divergence-flagged)",
           color="#5b9bd5")
    if has_pier:
        ax.bar(x + width / 2, pier, width,
               label="Priming-induced error rate (correct→wrong under pressure)",
               color="#e05252")
    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=9)
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1.05)
    ax.set_title("Model comparison — sycophancy & priming-induced error", fontweight="bold")
    ax.legend(fontsize=8)
    for i, v in enumerate(syco):
        ax.text(i - width / 2, v + 0.02, f"{v:.0%}", ha="center", fontsize=8)
    if has_pier:
        for i, v in enumerate(pier):
            ax.text(i + width / 2, v + 0.02, f"{v:.0%}", ha="center", fontsize=8)

    plt.tight_layout()
    chart_path = output_dir / "model_comparison.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    return chart_path
