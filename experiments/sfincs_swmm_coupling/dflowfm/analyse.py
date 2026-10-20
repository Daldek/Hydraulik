"""Steady-state exchange per manhole in the D-Flow FM runs, next to SFINCS-SWMM.

Exchange at a manhole = discharge leaving it through the downstream pipe minus
discharge arriving through the upstream pipe (positive = surface -> network),
from the 1D link discharges in the map file. Statistics over the last
STEADY_WINDOW_S of each inflow step, as in the SFINCS-SWMM analysis.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import netCDF4
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import case_setup as cs  # noqa: E402

STEP_ENDS_S = (1200.0, 2400.0, 3600.0)
BRANCH_ORDER = ["C1", "C2", "C3"]  # J1 -> J2 -> J3 -> outfall


def manhole_exchange(run_dir: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    with netCDF4.Dataset(run_dir / "DFM_OUTPUT_case" / "case_map.nc") as dataset:
        time = dataset["time"][:]
        q = dataset["mesh1d_q1"][:]
        branch = dataset["mesh1d_edge_branch"][:]
        offset = dataset["mesh1d_edge_offset"][:]
    first, last = {}, {}
    for index, name in enumerate(BRANCH_ORDER):
        edges = np.where(branch == index)[0]
        first[name] = edges[np.argmin(offset[edges])]
        last[name] = edges[np.argmax(offset[edges])]
    exchange = {
        "J1": q[:, first["C1"]],
        "J2": q[:, first["C2"]] - q[:, last["C1"]],
        "J3": q[:, first["C3"]] - q[:, last["C2"]],
    }
    return np.asarray(time), {k: np.asarray(v) for k, v in exchange.items()}


def steady_states(time: np.ndarray, exchange: dict[str, np.ndarray]) -> list[dict]:
    result = []
    for t_end in STEP_ENDS_S:
        window = (time > t_end - cs.STEADY_WINDOW_S) & (time <= t_end)
        entry = {"t_end_s": t_end}
        for name, q in exchange.items():
            entry[name] = {
                "mean_m3s": float(q[window].mean()),
                "std_m3s": float(q[window].std()),
            }
        result.append(entry)
    return result


def main() -> None:
    sfincs = json.loads((HERE.parent / "results" / "summary.json").read_text())
    timings = json.loads((HERE / "results" / "timings.json").read_text())
    pairs = [
        ("DQ1", "Q1_rec"),
        ("DQ1_inlet", "Q1_rec"),
        ("DQ2", "Q2_rec_rs025"),
        ("DQ2_inlet", "Q2_rec_rs025"),
        ("DQ3", "Q3_rec"),
        ("DQ3_inlet", "Q3_rec"),
    ]
    summary = {}
    for dflow, coupled in pairs:
        time, exchange = manhole_exchange(HERE / "runs" / dflow)
        summary[dflow] = {
            "compared_with": coupled,
            "wall_time_s": timings[dflow]["wall_time_s"],
            "steady_states": steady_states(time, exchange),
        }
        print(f"== {dflow} (vs {coupled}), wall {timings[dflow]['wall_time_s']:.1f} s")
        for step, (d_state, s_state) in enumerate(
            zip(summary[dflow]["steady_states"], sfincs[coupled]["steady_states"])
        ):
            cells = []
            for name in ("J1", "J2", "J3"):
                d, s = d_state[name], s_state[name]
                cells.append(
                    f"{name} DFM {d['mean_m3s']:+.4f}±{d['std_m3s']:.4f} / "
                    f"SFINCS-SWMM {s['mean_m3s']:+.4f}"
                )
            print(f"  step {step + 1}: " + " | ".join(cells))
    (HERE / "results" / "dflowfm_summary.json").write_text(
        json.dumps(summary, indent=2)
    )


if __name__ == "__main__":
    main()
