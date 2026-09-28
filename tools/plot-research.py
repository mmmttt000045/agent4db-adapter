"""Plot measured research reports. No synthetic performance data or smoothing."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    modes = ["A", "B", "C", "D", "M"]
    colors = ["#64748b", "#0d9488", "#d97706", "#2563eb", "#9333ea"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), layout="constrained")
    for i, mode in enumerate(modes):
        runs = [r for r in report["runs"] if r["mode"] == mode]
        costs = [r["total_database"]["db_ms"] / 1000 for r in runs]
        axes[0, 0].bar(i, sum(costs) / len(costs), color=colors[i], alpha=.75)
        axes[0, 0].scatter([i] * len(costs), costs, color="#111827", s=16, zorder=3)
        stable = sum(r["stable"]["correct"] for r in runs) / sum(r["stable"]["tasks"] for r in runs) * 100
        shifted = sum(r["shifted"]["correct"] for r in runs) / sum(r["shifted"]["tasks"] for r in runs) * 100
        axes[0, 1].bar(i - .18, stable, width=.35, color=colors[i], label="Stable" if i == 0 else None)
        axes[0, 1].bar(i + .18, shifted, width=.35, color=colors[i], alpha=.4, label="Shifted" if i == 0 else None)
        for stage, marker in [("stable", "o"), ("shifted", "x")]:
            axes[1, 0].plot([r["round"] + 1 for r in runs], [r[stage]["p95_ms"] for r in runs],
                            color=colors[i], marker=marker, linestyle="-" if stage == "stable" else "--",
                            label=f"{mode} {stage}")
    axes[0, 0].set(title="Full adapter DB cost per round", ylabel="Sum of SQL durations (s)", xticks=range(5), xticklabels=modes)
    axes[0, 1].set(title="Main workload correctness (boundary tests separate)", ylabel="Correct tasks (%)", ylim=(0, 105), xticks=range(5), xticklabels=modes)
    axes[0, 1].legend(loc="lower right")
    axes[1, 0].set(title="Task P95 by stage and round", xlabel="Round", ylabel="Milliseconds")
    axes[1, 0].legend(fontsize=7, ncols=2)
    effects = [e for e in report["contrasts"]["paired"] if e["metric"] == "db_ms"]
    for i, effect in enumerate(effects):
        lo, hi = effect["bootstrap_interval_95"]
        axes[1, 1].plot([lo / 1000, hi / 1000], [i, i], color="#475569", linewidth=2)
        axes[1, 1].scatter(effect["mean_delta"] / 1000, i, color="#0d9488")
    axes[1, 1].axvline(0, color="#9ca3af", linestyle="--")
    axes[1, 1].set(title="Paired cost differences; negative is cheaper",
                   xlabel="Target minus baseline DB seconds (descriptive 95% bootstrap)",
                   yticks=range(len(effects)), yticklabels=[f'{e["target"]} - {e["baseline"]}' for e in effects])
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.15)
        ax.set_axisbelow(True)
    options = report["options"]
    note = '\nInterrupted/resumed run; descriptive comparisons; no real LLM' if report.get('resumed') else ''
    fig.suptitle(f'Synthetic adapter evaluation | {options["agents"]} scripted agents | {options["rounds"]} paired rounds\n'
                 'A local fixed · B shared fixed · C local feedback · D shared feedback · M shared Mock' + note, fontsize=13)
    fig.savefig(args.report.with_name("research-summary.png"), dpi=180)
    fig.savefig(args.report.with_name("research-summary.svg"))
    plt.close(fig)


if __name__ == "__main__":
    main()
