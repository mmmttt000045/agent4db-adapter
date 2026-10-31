"""Compact Fig.6 from the complete published-baseline cohort only."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/figures"))
from matplotlib.patches import Patch
import mplstyle
import style

NAME = "two-schemas"
W, H = style.COLUMN, 55.0
ARMS = ["ace", "awm", "gmemory", "mavra"]
GROUPS = ["holdout", "benign", "modeled", "all"]
HATCHES = dict(zip(ARMS, ["////", r"\\", "xx", "...."]))
PREFIX = {"synthetic": "PubSynth", "tpch": "PubTpch"}
LABEL = {"ace": "ACE", "awm": "AWM", "gmemory": "G-Memory", "mavra": "MAVRA"}
for key, color in zip(ARMS, ["mACE", "mAWM", "mGMem", "mCond"]):
    style.METHODS[key] = (LABEL[key], LABEL[key], color)
TEXT = {
    "en": {"groups": ["Held-\nout", "Non-\nbreaking", "Covered\nbreaks", "All\nsettings"],
           "panels": ["(a) Synthetic retail", "(b) TPC-H SF1"], "y": "Accuracy (%)"},
    "zh": {"groups": ["留出题", "正常\n更新", "覆盖的\n破坏", "全部\n情形"],
           "panels": ["(a) 合成零售数据", "(b) TPC-H SF1"], "y": "正确率（%）"},
}


def load():
    data = json.loads((ROOT / "exp/2026-10-30-published-scenarios/study-stats.json").read_text(encoding="utf-8"))
    printed = style.macros("published-scenarios")
    for ds, prefix in PREFIX.items():
        for arm in ARMS:
            for group in GROUPS:
                row = data["datasets"][ds]["arms"][arm]["groups"][group]
                values = row["run_values_pct"]
                assert len(values) == len(data["complete_repeats"]) and all(0 <= x <= 100 for x in values)
                assert abs(sum(values) / len(values) - row["accuracy_pct"]) < 1e-9
                macro = prefix + LABEL[arm].replace("-", "") + group.capitalize()
                style.agree(macro, f"{row['accuracy_pct']:.1f}", printed[macro])
    return data


def figure(lang):
    t, data = TEXT[lang], load()
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 2, sharey=True, gridspec_kw=dict(left=.12, right=.99, top=.80, bottom=.24, wspace=.20))
    handles = [Patch(**mplstyle.bar_style(arm, HATCHES[arm]), label=LABEL[arm]) for arm in ARMS]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.53, .975), ncol=4,
               handlelength=1.15, columnspacing=.8, fontsize=7)
    for col, (ax, ds) in enumerate(zip(axes, PREFIX)):
        width = .78 / len(ARMS)
        for mi, arm in enumerate(ARMS):
            groups = data["datasets"][ds]["arms"][arm]["groups"]
            values = [groups[g]["accuracy_pct"] for g in GROUPS]
            xs = [i + (mi - (len(ARMS)-1)/2) * width for i in range(len(GROUPS))]
            ax.bar(xs, values, width=width, **mplstyle.bar_style(arm, HATCHES[arm]), zorder=2)
            for x, value in zip(xs, values):
                if value == 0:
                    ax.text(x, 1.5, "0", ha="center", va="bottom", fontsize=6, zorder=4)
            if len(data["complete_repeats"]) > 1:
                lo = [groups[g]["range_pct"][0] for g in GROUPS]
                hi = [groups[g]["range_pct"][1] for g in GROUPS]
                ax.errorbar(xs, values, yerr=[[v-l for v,l in zip(values,lo)], [h-v for h,v in zip(hi,values)]],
                            fmt="none", ecolor="black", elinewidth=.4, capsize=.7, capthick=.4, zorder=3)
        ax.set(xlim=(-.55, 3.55), ylim=(0,105), yticks=[0,25,50,75,100])
        ax.set_xticks(range(4), t["groups"])
        ax.tick_params(axis="x", length=0, labelsize=6.5)
        ax.yaxis.grid(True)
        box = ax.get_position()
        fig.text((box.x0+box.x1)/2, .025, t["panels"][col], ha="center", va="bottom", fontsize=7.5)
    axes[0].set_ylabel(t["y"], fontsize=7.5)
    return fig


if __name__ == "__main__":
    for path in style.build(sys.modules[__name__]):
        print(path)
