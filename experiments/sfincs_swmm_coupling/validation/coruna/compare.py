"""Compare the A Coruna runs with the measurements: tables and figures.

Writes results/calibration.md, results/validation.md, results/sensitivity.md,
results/metrics.json and figures/fig_coruna_*.png.

Usage: CORUNA_DATA=/path/to/dataset python compare.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import coruna_setup as cs  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RESULTS = HERE / "results"
FIGURES = HERE / "figures"

# Categorical slots 1-3 of the reference palette (as in the feasibility test).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK_MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
MEASURED_COLOR = INK_MUTED

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "font.size": 8,
        "axes.edgecolor": INK_MUTED,
        "axes.labelcolor": INK,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "lines.linewidth": 1.2,
        "legend.frameon": False,
    }
)

INLETS = ["IN1", "IN2", "IN3", "IN4"]
BASELINE_WINDOW_S = (20.0, 120.0)  # steady generator flow before the rain
PLATEAU_WINDOW_S = (300.0, 360.0)  # steady rain, H1-H3
FIT_WINDOW_S = (100.0, 600.0)  # NSE and volumes
SMOOTH_S = 5.0  # moving average before reading peaks


def window_mean(t: np.ndarray, q: np.ndarray, window: tuple[float, float]) -> float:
    inside = (t >= window[0]) & (t <= window[1])
    return float(np.nanmean(q[inside]))


def smooth(q: np.ndarray, dt: float) -> np.ndarray:
    n = max(int(round(SMOOTH_S / dt)), 1)
    return np.convolve(q, np.ones(n) / n, mode="same")


def model_on(t_measured: np.ndarray, t_model: np.ndarray, q: np.ndarray) -> np.ndarray:
    return np.interp(t_measured, t_model, q)


def centroid(t: np.ndarray, q: np.ndarray) -> float:
    weight = np.clip(np.nan_to_num(q), 0.0, None)
    return float(np.sum(t * weight) / np.sum(weight))


def nse(observed: np.ndarray, simulated: np.ndarray) -> float:
    ok = np.isfinite(observed)
    o, s = observed[ok], simulated[ok]
    return float(1.0 - np.sum((s - o) ** 2) / np.sum((o - o.mean()) ** 2))


def inlet_metrics(test: str, run: str, measured: dict) -> dict:
    """Volume, peak, peak time and NSE of IN1-IN4 for one run (L, L/s, s)."""
    series = np.load(RUNS / run / "series.npz")
    t = measured["Time[s]"]
    dt = t[1] - t[0]
    fit = (t >= FIT_WINDOW_S[0]) & (t <= FIT_WINDOW_S[1])
    runoff = cs.TESTS[test][2]
    metrics = {}
    for i, name in enumerate(INLETS, start=1):
        observed = measured[f"Inlet_{i}[m3/s]"] * 1000.0
        simulated = model_on(t, series["t"], series[f"q_{name}"]) * 1000.0
        entry = {}
        if runoff:
            base_o = window_mean(t, observed, BASELINE_WINDOW_S)
            base_s = window_mean(t, simulated, BASELINE_WINDOW_S)
            entry["baseline_measured_l_s"] = base_o
            entry["baseline_model_l_s"] = base_s
            observed_event, simulated_event = observed - base_o, simulated - base_s
        else:
            observed_event, simulated_event = observed, simulated
        vol_o = float(np.nansum(observed_event[fit]) * dt)
        vol_s = float(np.sum(simulated_event[fit]) * dt)
        smooth_o, smooth_s = smooth(observed_event, dt), smooth(simulated_event, dt)
        entry.update(
            {
                "volume_measured_l": vol_o,
                "volume_model_l": vol_s,
                "volume_ratio": vol_s / vol_o if vol_o > 0 else float("nan"),
                "peak_measured_l_s": float(np.nanmax(smooth_o)),
                "peak_model_l_s": float(np.max(smooth_s)),
                # Shift of the hydrograph centroid (a peak time is undefined on
                # the flat plateau of H1-H3).
                "centroid_shift_s": centroid(t[fit], simulated_event[fit])
                - centroid(t[fit], observed_event[fit]),
                # Shape of the response (for T07-T12 the rise above the
                # generator flow, so the baseline offset is not counted twice).
                "nse": nse(observed_event[fit], simulated_event[fit]),
            }
        )
        if test in ("T01", "T02", "T03"):
            entry["plateau_measured_l_s"] = window_mean(t, observed, PLATEAU_WINDOW_S)
            entry["plateau_model_l_s"] = window_mean(t, simulated, PLATEAU_WINDOW_S)
        metrics[name] = entry
    # IN5: measured only as one steady value (H1-H3).
    in5 = model_on(t, series["t"], series["q_IN5"]) * 1000.0
    metrics["IN5"] = {
        "plateau_model_l_s": window_mean(t, in5, PLATEAU_WINDOW_S),
        "baseline_model_l_s": window_mean(t, in5, BASELINE_WINDOW_S),
    }
    if np.isfinite(measured["Inlet_5[m3/s]"]).any():
        metrics["IN5"]["plateau_measured_l_s"] = float(
            np.nanmean(measured["Inlet_5[m3/s]"]) * 1000.0
        )
    # Depth gauges (mm): plateau (H1-H3) or generator baseline (T07-T12).
    window = BASELINE_WINDOW_S if runoff else PLATEAU_WINDOW_S
    if runoff or test in ("T01", "T02", "T03"):
        depths = {}
        for gauge in cs.depth_gauges():
            o = window_mean(t, measured[gauge] * 1000.0, window)
            s = window_mean(
                t, model_on(t, series["t"], series[f"depth_{gauge}"]) * 1000.0, window
            )
            depths[f"D_S{int(gauge[8:10])}"] = {"measured_mm": o, "model_mm": s}
        metrics["depths"] = depths
    # Outfall: only the steady generator flow (no roof water reaches it).
    if runoff:
        observed = measured["Outfall[m3/s]"] * 1000.0
        simulated = model_on(t, series["t_s"], series["outfall_q"]) * 1000.0
        metrics["outfall_baseline"] = {
            "measured_l_s": window_mean(t, observed, BASELINE_WINDOW_S),
            "model_l_s": window_mean(t, simulated, BASELINE_WINDOW_S),
        }
    return metrics


def measured_baseline() -> tuple[np.ndarray, np.ndarray]:
    """Mean and spread of the steady generator flows over T07-T12 (L/s).

    IN5 is not recorded in T07-T12; it is the outfall minus IN1-IN4.
    """
    rows = []
    for test in ("T07", "T08", "T09", "T10", "T11", "T12"):
        m = cs.load_measurements(test)
        t = m["Time[s]"]
        q = [
            window_mean(t, m[f"Inlet_{i}[m3/s]"] * 1000.0, BASELINE_WINDOW_S)
            for i in range(1, 5)
        ]
        outfall = window_mean(t, m["Outfall[m3/s]"] * 1000.0, BASELINE_WINDOW_S)
        rows.append(q + [outfall - sum(q)])
    rows = np.array(rows)
    return rows.mean(axis=0), rows.std(axis=0)


def model_baseline(run: str) -> np.ndarray:
    series = np.load(RUNS / run / "series.npz")
    return np.array(
        [
            window_mean(series["t"], series[f"q_IN{i}"] * 1000.0, BASELINE_WINDOW_S)
            for i in range(1, 6)
        ]
    )


def calibration_table() -> tuple[list[str], dict]:
    target, spread = measured_baseline()
    lines = [
        "| Mnożnik współczynników | IN1 | IN2 | IN3 | IN4 | IN5 | RMSE [L/s] |",
        "|---|---|---|---|---|---|---|",
        "| **pomiar (T07–T12, średnia ± odch. std.)** | "
        + " | ".join(f"{m:.3f} ± {s:.3f}" for m, s in zip(target, spread))
        + " | – |",
    ]
    scan = {}
    runs = [("T07", 1.0)] + [(f"cal_{s:g}", s) for s in cs.CALIBRATION_SCALES]
    for run, scale in runs:
        q = model_baseline(run)
        rmse = float(np.sqrt(np.mean((q - target) ** 2)))
        scan[scale] = {"flows_l_s": q.tolist(), "rmse_l_s": rmse}
        bold = "**" if scale == cs.CALIBRATED_SCALE else ""
        lines.append(
            f"| {bold}{scale:g}{bold} | "
            + " | ".join(f"{v:.3f}" for v in q)
            + f" | {rmse:.3f} |"
        )
    return lines, {"target_l_s": target.tolist(), "spread_l_s": spread.tolist(), "scan": scan}


def validation_tables(metrics: dict) -> list[str]:
    lines = [
        "### Kratki 1–4: objętość, szczyt, przesunięcie szczytu, NSE",
        "",
        "Seria 1 (T01–T06): cała odpowiedź na deszcz. Seria 2 (T07–T12): przyrost "
        "ponad przepływ ustalony z generatorów. Okno 100–600 s. Przesunięcie: "
        "środek ciężkości hydrogramu modelu minus pomiaru.",
        "",
        "| Test | Wariant | Objętość model/pomiar IN1 / IN2 / IN3 / IN4 | "
        "Szczyt model/pomiar | Przesunięcie [s] | NSE |",
        "|---|---|---|---|---|---|",
    ]
    for test in cs.TESTS:
        for label, run in (("bez kalibracji", test), ("skalibrowany", f"C_{test}")):
            if run not in metrics:
                continue
            m = metrics[run]
            ratios = " / ".join(f"{m[n]['volume_ratio']:.2f}" for n in INLETS)
            peaks = " / ".join(
                f"{m[n]['peak_model_l_s'] / m[n]['peak_measured_l_s']:.2f}"
                for n in INLETS
            )
            shifts = " / ".join(f"{m[n]['centroid_shift_s']:+.0f}" for n in INLETS)
            nses = " / ".join(f"{m[n]['nse']:.2f}" for n in INLETS)
            lines.append(f"| {test} | {label} | {ratios} | {peaks} | {shifts} | {nses} |")

    lines += [
        "",
        "### Podział wody między kratki w stanie ustalonym deszczu (T01–T03)",
        "",
        "Udział kratki w sumie przepływu przez kratki 1–5, okno 300–360 s "
        "(IN5 zmierzona tylko jako jedna wartość ustalona).",
        "",
        "| Test | Wariant | Suma [L/s] | IN1 | IN2 | IN3 | IN4 | IN5 | "
        "RMSE udziałów [p.p.] |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for test in ("T01", "T02", "T03"):
        m = metrics.get(f"C_{test}") or metrics.get(test)
        if m is None:
            continue
        measured = [m[n]["plateau_measured_l_s"] for n in INLETS]
        measured.append(m["IN5"]["plateau_measured_l_s"])
        rows = [("pomiar", measured)]
        for label, run in (("bez kalibracji", test), ("skalibrowany", f"C_{test}")):
            if run in metrics:
                mm = metrics[run]
                rows.append(
                    (
                        label,
                        [mm[n]["plateau_model_l_s"] for n in INLETS]
                        + [mm["IN5"]["plateau_model_l_s"]],
                    )
                )
        measured_shares = 100 * np.array(measured) / sum(measured)
        for label, values in rows:
            shares = 100 * np.array(values) / sum(values)
            rmse = np.sqrt(np.mean((shares - measured_shares) ** 2))
            lines.append(
                f"| {test} | {label} | {sum(values):.3f} | "
                + " | ".join(f"{s:.0f}%" for s in shares)
                + (" | – |" if label == "pomiar" else f" | {rmse:.1f} |")
            )

    lines += [
        "",
        "### Głębokości w punktach pomiarowych [mm]",
        "",
        "Stan ustalony: T03 (deszcz 80 mm/h, okno 300–360 s) i T07 (generatory, "
        "okno 20–120 s); wariant skalibrowany.",
        "",
        "| Punkt | T03 pomiar | T03 model | T07 pomiar | T07 model |",
        "|---|---|---|---|---|",
    ]
    if "C_T03" in metrics and "C_T07" in metrics:
        for gauge, value in metrics["C_T03"]["depths"].items():
            other = metrics["C_T07"]["depths"][gauge]
            lines.append(
                f"| {gauge} | {value['measured_mm']:.1f} | "
                f"{value['model_mm']:.1f} | {other['measured_mm']:.1f} | "
                f"{other['model_mm']:.1f} |"
            )

    lines += [
        "",
        "### Odpływ z sieci przy przepływie ustalonym z generatorów (2 L/s)",
        "",
        "| Test | Pomiar [L/s] | Model [L/s] |",
        "|---|---|---|",
    ]
    for test in ("T07", "T08", "T09", "T10", "T11", "T12"):
        run = f"C_{test}"
        if run in metrics:
            o = metrics[run]["outfall_baseline"]
            lines.append(f"| {test} | {o['measured_l_s']:.3f} | {o['model_l_s']:.3f} |")
    return lines


def sensitivity_table(metrics: dict, results: dict) -> list[str]:
    lines = [
        "| Przebieg | Zmiana | Suma IN1–4, stan ustalony [L/s] | IN5 [L/s] | "
        "Objętość model/pomiar (śr. IN1–4) | NSE (śr. IN1–4) | Błąd bilansu "
        "powierzchni [L] | Czas [s] |",
        "|---|---|---|---|---|---|---|---|",
    ]
    labels = {
        "": "wariant skalibrowany",
        "dx10": "oczko 10 cm",
        "n012": "n = 0,012",
        "n020": "n = 0,020",
        "hmax": "głębokość nad kratką: maksimum zamiast średniej",
        "hu1mm": "próg suchej komórki 1 mm",
        "rainmap": "zmierzona mapa deszczu",
        "dtx1": "krok wymiany 1 s",
    }
    for test in ("T03", "T09"):
        for key, label in labels.items():
            run = f"C_{test}" + (f"_{key}" if key else "")
            if run not in metrics:
                continue
            m = metrics[run]
            window = "plateau_model_l_s" if test == "T03" else "baseline_model_l_s"
            if test == "T03":
                total = sum(m[n]["plateau_model_l_s"] for n in INLETS)
            else:
                total = sum(m[n]["baseline_model_l_s"] for n in INLETS)
            ratio = np.mean([m[n]["volume_ratio"] for n in INLETS])
            mean_nse = np.mean([m[n]["nse"] for n in INLETS])
            r = results[run]
            lines.append(
                f"| {run} | {label} | {total:.3f} | {m['IN5'][window]:.3f} | "
                f"{ratio:.2f} | {mean_nse:.2f} | "
                f"{r['surface_side_error_m3'] * 1000:+.4f} | {r['wall_time_s']:.0f} |"
            )
    return lines


def hydrograph_figure(tests: list[str], path: Path, title: str) -> None:
    fig, axes = plt.subplots(len(tests), 4, figsize=(9.0, 1.45 * len(tests) + 0.8))
    for row, test in enumerate(tests):
        measured = cs.load_measurements(test)
        t = measured["Time[s]"]
        for col, name in enumerate(INLETS):
            ax = axes[row, col]
            ax.plot(
                t,
                measured[f"Inlet_{col + 1}[m3/s]"] * 1000.0,
                color=MEASURED_COLOR,
                linewidth=1.0,
            )
            for run, color, width in (
                (test, SERIES[1], 0.9),
                (f"C_{test}", SERIES[0], 1.2),
            ):
                if (RUNS / run / "series.npz").exists():
                    s = np.load(RUNS / run / "series.npz")
                    ax.plot(s["t"], s[f"q_{name}"] * 1000.0, color=color, linewidth=width)
            ax.set_xlim(0, 600)
            ax.tick_params(labelsize=7)
            if row == 0:
                ax.set_title(f"kratka {name}", loc="left", fontsize=8)
            if col == 0:
                ax.set_ylabel(f"{test}\n{cs.TESTS[test][1]}  [L/s]", fontsize=7.5)
            if row == len(tests) - 1:
                ax.set_xlabel("czas [s]", fontsize=7.5)
    handles = [
        plt.Line2D([], [], color=MEASURED_COLOR, linewidth=1.0),
        plt.Line2D([], [], color=SERIES[1], linewidth=0.9),
        plt.Line2D([], [], color=SERIES[0], linewidth=1.2),
    ]
    fig.legend(
        handles,
        ["pomiar", "model bez kalibracji", f"model skalibrowany (×{cs.CALIBRATED_SCALE:g})"],
        loc="lower center",
        ncol=3,
        fontsize=8,
    )
    fig.suptitle(title, x=0.01, ha="left", fontsize=9)
    fig.tight_layout(rect=(0, 0.035, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)


def calibration_figure(info: dict, path: Path) -> None:
    names = ["IN1", "IN2", "IN3", "IN4", "IN5"]
    target, spread = np.array(info["target_l_s"]), np.array(info["spread_l_s"])
    uncalibrated = np.array(info["scan"][1.0]["flows_l_s"])
    calibrated = np.array(info["scan"][cs.CALIBRATED_SCALE]["flows_l_s"])
    fig, ax = plt.subplots(figsize=(6.0, 3.0))
    positions = np.arange(len(names))
    width = 0.26
    for offset, values, color, label in (
        (-width, target, MEASURED_COLOR, "pomiar (T07–T12)"),
        (0.0, uncalibrated, SERIES[1], "model bez kalibracji"),
        (width, calibrated, SERIES[0], f"model skalibrowany (×{cs.CALIBRATED_SCALE:g})"),
    ):
        ax.bar(positions + offset, values, width=width - 0.03, color=color, label=label)
    ax.errorbar(
        positions - width, target, yerr=spread, fmt="none", ecolor=INK, linewidth=0.8
    )
    ax.set_xticks(positions, names)
    ax.set_ylabel("przepływ ustalony [L/s]")
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=7.5)
    ax.set_title(
        "Przepływ przez kratki przy dopływie 2 L/s z generatorów "
        "(IN5 z pomiaru = odpływ − suma IN1–4)",
        loc="left",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)
    results = json.loads((RESULTS / "summary.json").read_text())

    calibration_lines, calibration = calibration_table()
    (RESULTS / "calibration.md").write_text("\n".join(calibration_lines) + "\n")

    metrics = {}
    for run, config in cs.RUNS.items():
        if run.startswith("cal_") or not (RUNS / run / "series.npz").exists():
            continue
        metrics[run] = inlet_metrics(config.test, run, cs.load_measurements(config.test))
    (RESULTS / "metrics.json").write_text(
        json.dumps({"calibration": calibration, "runs": metrics}, indent=2)
    )
    (RESULTS / "validation.md").write_text("\n".join(validation_tables(metrics)) + "\n")
    (RESULTS / "sensitivity.md").write_text(
        "\n".join(sensitivity_table(metrics, results)) + "\n"
    )

    calibration_figure(calibration, FIGURES / "fig_coruna_calibration.png")
    hydrograph_figure(
        ["T01", "T02", "T03", "T04", "T05", "T06"],
        FIGURES / "fig_coruna_set1.png",
        "Seria 1 (sam deszcz): przepływ przez kratki 1–4",
    )
    hydrograph_figure(
        ["T07", "T08", "T09", "T10", "T11", "T12"],
        FIGURES / "fig_coruna_set2.png",
        "Seria 2 (deszcz + 2 × 1 L/s z generatorów): przepływ przez kratki 1–4",
    )
    print("\n".join(calibration_lines))
    print((RESULTS / "validation.md").read_text())
    print((RESULTS / "sensitivity.md").read_text())


if __name__ == "__main__":
    main()
