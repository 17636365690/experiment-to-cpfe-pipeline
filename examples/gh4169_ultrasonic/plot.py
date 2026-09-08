"""Export specimen-level signed errors from evaluation.json (requires matplotlib)."""

import argparse
import json
from pathlib import Path


def plot(evaluation_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(evaluation_path)
    result = json.loads(path.read_text(encoding="utf-8"))
    # Chart contract: compare errors at the original specimen grain (n=8+2).
    # Two color roots, distinct markers and open fill; zero is the ideal reference.
    styles = [("mean", "Mean", "#777777", "x", False),
              ("mlp", "MLP ensemble", "#2878B5", "o", False),
              ("ols", "Linear (OLS)", "#D17A22", "s", False),
              ("ridge", "Ridge", "#D17A22", "D", True)]
    identities = [f"NO.{i}" for i in range(1, 9)] + ["T1", "T2"]
    fig, ax = plt.subplots(figsize=(9.2, 7.4))
    for j, (model, label, color, marker, hollow) in enumerate(styles):
        values = [next(r["error"] for r in result["predictions"]
                       if r["model"] == model and r["specimen"] == identity) for identity in identities]
        ax.scatter(values, [i+(j-1.5)*.15 for i in range(10)], s=38,
                   facecolors="none" if hollow else color, edgecolors=color if marker != "x" else None,
                   marker=marker, linewidths=1.1, label=label, zorder=3)
    ax.axvline(0, color="#333333", linewidth=1)
    ax.axhline(7.5, color="#999999", linestyle="--", linewidth=.8)
    ax.set_yticks(range(10), identities[:8] + ["T1 (author test)", "T2 (author test)"])
    ax.invert_yaxis()
    ax.set_xlabel("Prediction minus metallographic mean grain diameter (μm)")
    ax.set_xlim(-120, 65)
    ax.grid(axis="x", color="#e4e4e4", linewidth=.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.015), ncol=4, frameon=False, fontsize=9)
    fig.suptitle("GH4169: specimen-level prediction errors", x=.04, y=.985, ha="left", fontsize=17)
    fig.text(.04, .94, "Eight nested development holdouts; two reserved author test specimens", fontsize=11)
    fig.text(.04, .035, "Inputs: mean attenuation and longitudinal velocity. Each mark is one specimen prediction.\n"
             "Source: Chen et al., Mendeley Data v1, DOI 10.17632/v487vwmd7r.1 · CC BY-NC 3.0", fontsize=9)
    fig.subplots_adjust(left=.20, right=.97, top=.83, bottom=.13)
    for suffix in ("png", "svg"):
        fig.savefig(path.parent/f"specimen-errors.{suffix}", dpi=180, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", required=True, type=Path)
    plot(parser.parse_args().evaluation)
