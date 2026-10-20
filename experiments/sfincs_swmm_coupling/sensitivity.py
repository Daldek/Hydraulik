"""Summarise the one-factor-at-a-time sensitivity runs (scenarios V_*, V3_*).

Writes results/sensitivity.md (table) and figures/fig7_sensitivity.png.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import case_setup as cs  # noqa: E402
from plots import INK_MUTED, SERIES  # noqa: E402

HERE = Path(__file__).resolve().parent
FACTOR_LABELS_PL = {
    "d3": "średnica ostatniego przewodu [m]",
    "nodes": "liczba węzłów wymiany",
    "depth": "głębokość posadowienia sieci [m]",
    "inflow": "mnożnik dopływu (głębokość wody)",
    "dtc": "krok wymiany Δt_c [s]",
    "swmm": "krok obliczeniowy SWMM [s]",
    "area": "powierzchnia odniesienia wpustu A [m²]",
    "coef": "mnożnik współczynników wpustu",
}


def metrics(result: dict) -> dict:
    """Steady-state metrics of the last two inflow steps plus run totals."""
    states = result["steady_states"][1:]  # steps 0.10 and 0.15 (scaled)
    nodes = [k for k in states[-1] if k.startswith("J")]
    last = states[-1]
    return {
        "inflow_m3s": last["inflow_m3s"],
        "exchange_m3s": sum(last[n]["mean_m3s"] for n in nodes),
        "spilling_nodes": sum(last[n]["mean_m3s"] < -1e-4 for n in nodes),
        "nodes": len(nodes),
        "max_std_m3s": max(s[n]["std_m3s"] for s in states for n in nodes),
        "sign_flips": sum(s[n]["sign_flips"] for s in states for n in nodes),
        "surface_side_error_m3": result["surface_side_error_m3"],
        "network_side_error_m3": result["network_side_error_m3"],
        "swmm_error_pct": result["swmm_routing_stats"]["routing_error"],
        "mass_error_pct": result["mass_error_pct_of_inflow"],
        "max_depth_m": result["max_depth_m"],
        "wall_time_s": result["wall_time_s"],
    }


def main() -> None:
    summary = json.loads((HERE / "results" / "summary.json").read_text())
    rows = []
    for name in cs.SENSITIVITY_RUNS:
        if name in summary:
            rows.append((name, metrics(summary[name])))

    lines = [
        "| Przebieg | Wymiana razem, ost. stopień [m³/s] | Węzły wybijające | "
        "Maks. odchylenie w stanie ustalonym [m³/s] | Zmiany znaku | "
        "Błąd po stronie powierzchni [m³] | Błąd ciągłości SWMM [%] | Czas [s] |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, m in rows:
        lines.append(
            f"| {name} | {m['exchange_m3s']:+.4f} | {m['spilling_nodes']}/{m['nodes']} | "
            f"{m['max_std_m3s']:.4f} | {m['sign_flips']} | "
            f"{m['surface_side_error_m3']:+.3f} | {m['swmm_error_pct']:+.2f} | "
            f"{m['wall_time_s']:.2f} |"
        )
    (HERE / "results" / "sensitivity.md").write_text("\n".join(lines) + "\n")

    fig, axes = plt.subplots(2, 4, figsize=(9.0, 5.0))
    table = dict(rows)
    width = 0.38
    for ax, (factor, (_, values)) in zip(axes.flat, cs.SENSITIVITY_FACTORS.items()):
        positions = np.arange(len(values))
        series = [("V", "sieć przeciążona (Q2)", SERIES[0])]
        if all(f"V1_{factor}_{v:g}" in table for v in values):
            series.append(("V1", "sieć swobodna (Q1)", SERIES[1]))
        offsets = [0.0] if len(series) == 1 else [-width / 2, width / 2]
        for (prefix, label, color), offset in zip(series, offsets):
            names = [f"{prefix}_{factor}_{v:g}" for v in values]
            exchange = [table[n]["exchange_m3s"] for n in names]
            std = [table[n]["max_std_m3s"] for n in names]
            ax.bar(
                positions + offset,
                exchange,
                width=width - 0.04,
                color=color,
                label=label,
            )
            for x, e, sd in zip(positions + offset, exchange, std):
                if sd >= 0.001:
                    ax.text(
                        x,
                        e,
                        f"σ {sd:.3f}",
                        ha="center",
                        va="bottom",
                        fontsize=6,
                        color=INK_MUTED,
                    )
        ax.set_xticks(positions, [f"{v:g}" for v in values], fontsize=7.5)
        ax.set_title(FACTOR_LABELS_PL[factor], loc="left", fontsize=7.5)
        ax.grid(axis="x", visible=False)
        ax.tick_params(axis="y", labelsize=7)
    axes[0, 0].set_ylabel("wymiana razem [m³/s]", fontsize=8)
    axes[1, 0].set_ylabel("wymiana razem [m³/s]", fontsize=8)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=SERIES[0]),
        plt.Rectangle((0, 0), 1, 1, color=SERIES[1]),
    ]
    fig.legend(
        handles,
        ["sieć przeciążona (Q2)", "sieć swobodna (Q1)"],
        loc="lower center",
        ncol=2,
        fontsize=8,
    )
    fig.suptitle(
        "Wrażliwość: suma wymiany w stanie ustalonym (ostatni stopień dopływu); "
        "σ = maks. odchylenie wymiany (pokazane, gdy ≥ 0,001 m³/s)",
        fontsize=8,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig(HERE / "figures" / "fig7_sensitivity.png", dpi=150)
    plt.close(fig)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
