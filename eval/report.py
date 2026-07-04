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
