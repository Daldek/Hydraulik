"""Figures for the SFINCS-SWMM coupling feasibility report."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import case_setup as cs  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
FIGURES = HERE / "figures"

# Categorical slots 1-3 of the reference palette (light mode), fixed order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK_MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "font.size": 9,
        "axes.edgecolor": INK_MUTED,
        "axes.labelcolor": INK,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "lines.linewidth": 1.4,
        "legend.frameon": False,
    }
)


def load(name: str) -> dict:
    return dict(np.load(RUNS / name / "series.npz"))


def exchange_comparison(
    case: str, node: str, runs: list[tuple[str, str]], window, path
):
    """Exchange discharge at one node for several schemes, full run + zoom."""
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 5.2), sharey=False)
    for (run, label), color in zip(runs, SERIES):
        d = load(run)
        for ax in axes:
            ax.plot(d["t"] / 60.0, d[f"q_{node}"], color=color, label=label)
    axes[0].set_title(
        f"{case}: wymiana w węźle {node} (dodatnia = powierzchnia → sieć)",
        loc="left",
        fontsize=9,
    )
    axes[1].set_xlim(window[0] / 60.0, window[1] / 60.0)
    axes[1].set_title("Powiększenie", loc="left", fontsize=9)
    limit = 0.4
    for ax in axes:
        ax.set_ylim(-limit, limit)
        ax.set_ylabel("Q [m³/s]")
        ax.axhline(0.0, color=INK_MUTED, linewidth=0.6)
    axes[1].set_xlabel("czas [min]")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def depth_maps(runs: list[tuple[str, str]], path):
    """Maximum water depth over the run for several scenarios."""
    fig, axes = plt.subplots(
        len(runs),
        1,
        figsize=(7.0, 1.45 * len(runs) + 0.6),
        sharex=True,
        gridspec_kw={"hspace": 0.45},
    )
    vmax = 0.5
    image = None
    for ax, (run, label) in zip(axes, runs):
        d = load(run)
        depth = (d["zs_max"] - d["zb"]).reshape(cs.N_CELLS_X, cs.N_CELLS_Y).T
        image = ax.imshow(
            np.clip(depth, 0.0, None),
            origin="lower",
            extent=(0, cs.N_CELLS_X * cs.CELL_SIZE_M, 0, cs.N_CELLS_Y * cs.CELL_SIZE_M),
            cmap="Blues",
            vmin=0.0,
            vmax=vmax,
            aspect="equal",
        )
        if run != "S0" and run != "S0K":
            for x, y in cs.EXCHANGE_NODES_XY.values():
                ax.plot(
                    x,
                    y,
                    marker="o",
                    markersize=4,
                    color="#eb6834",
                    markeredgecolor="white",
                    markeredgewidth=0.8,
                )
        ax.set_title(label, loc="left", fontsize=8.5)
        ax.grid(False)
        ax.set_yticks([0, 20, 40])
    axes[-1].set_xlabel("x [m]  (spadek w kierunku rosnącego x; ● = węzeł wymiany)")
    fig.colorbar(image, ax=axes, shrink=0.8, label="maks. głębokość [m]")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def interval_sensitivity(summary: dict, path):
    """Exchanged volume per node vs exchange interval (recommended scheme)."""
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8))
    nodes = list(cs.EXCHANGE_NODES_XY)
    intervals = [1, 5, 30]
    width = 0.26
    for ax, case in zip(axes, ["S2", "S3"]):
        for i, (dt, color) in enumerate(zip(intervals, SERIES)):
            values = [
                summary[f"{case}_rec_dt{dt}"]["exchanged_per_node_m3"][n] for n in nodes
            ]
            positions = np.arange(len(nodes)) + (i - 1) * width
            ax.bar(
                positions,
                values,
                width=width - 0.03,
                color=color,
                label=f"Δt_c = {dt} s",
            )
        ax.axhline(0.0, color=INK_MUTED, linewidth=0.6)
        ax.set_xticks(range(len(nodes)), nodes)
        ax.set_title(f"{case}: objętość wymiany [m³]", loc="left", fontsize=9)
        ax.grid(axis="x", visible=False)
    axes[0].legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    summary = json.loads((HERE / "results" / "summary.json").read_text())
    exchange_comparison(
        "S2 (przeciążenie)",
        "J3",
        [
            ("S2", "naiwne (EXTRAN)"),
            ("S2_slot", "SLOT"),
            ("S2_rec_dt1", "SLOT + relaksacja w = 0,1"),
        ],
        (1380, 1500),
        FIGURES / "fig1_s2_exchange_J3.png",
    )
    exchange_comparison(
        "S3 (cofka)",
        "J2",
        [
            ("S3_slot", "SLOT"),
            ("S3_slot_lim", "SLOT + ogranicznik wyrównania"),
            ("S3_rec_dt1", "SLOT + relaksacja w = 0,1"),
        ],
        (3100, 3220),
        FIGURES / "fig2_s3_exchange_J2.png",
    )
    depth_maps(
        [
            ("S0", "S0: bez odprowadzenia"),
            ("S0K", "S0K: koncepcyjny drenaż SFINCS (30 mm/h)"),
            ("S1", "S1: sprzężenie, swobodny odpływ"),
            ("S2_rec_dt1", "S2: sprzężenie, przeciążona sieć"),
            ("S3_rec_dt1", "S3: sprzężenie, cofka z wylotu"),
        ],
        FIGURES / "fig3_max_depth.png",
    )
    interval_sensitivity(summary, FIGURES / "fig4_interval_sensitivity.png")
    print("figures written to", FIGURES)


if __name__ == "__main__":
    main()
