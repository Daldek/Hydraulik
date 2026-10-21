"""Export one coupled scenario for the 3D viewer.

Re-runs the scenario with SFINCS map output every MAP_INTERVAL_S seconds (the
regular runs keep only maxima) and writes one JSON file with the bed, the
water depth and speed of every map time, and the node series of the coupler.

Usage: python export_3d.py <scenario> <run dir> <libsfincs.so> <output.json>
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import case_setup as cs  # noqa: E402
import coupler  # noqa: E402

MAP_INTERVAL_S = 10
SERIES_STEP_S = 5  # block means of the 1 s coupler series

_write_sfincs_case = cs.write_sfincs_case


def write_sfincs_case_with_maps(run_dir: Path, scenario: cs.Scenario) -> None:
    """Regular SFINCS input plus map output (levels and velocities)."""
    _write_sfincs_case(run_dir, scenario)
    path = run_dir / "sfincs.inp"
    text = re.sub(r"(?m)^dtout\s*=.*$", f"{'dtout':<16}= {MAP_INTERVAL_S}", path.read_text())
    path.write_text(text + f"{'storevel':<16}= 1\n")


def encode(values: np.ndarray, dtype: str) -> str:
    """Little-endian array as base64 text."""
    return base64.b64encode(np.ascontiguousarray(values, dtype=dtype).tobytes()).decode()


def block_mean(values: np.ndarray, size: int) -> np.ndarray:
    usable = len(values) // size * size
    return values[:usable].reshape(-1, size).mean(axis=1)


def main(name: str, run_dir: Path, library: str, output: Path) -> None:
    scenario = cs.SCENARIOS[name]
    cs.write_sfincs_case = write_sfincs_case_with_maps
    result = coupler.run(scenario, run_dir, library)

    with netCDF4.Dataset(run_dir / "sfincs_map.nc") as maps:
        bed = np.asarray(maps["zb"][:], dtype=float)
        levels = np.asarray(maps["zs"][:], dtype=float)
        u = np.asarray(maps["u"][:], dtype=float)
        v = np.asarray(maps["v"][:], dtype=float)
        time_s = np.asarray(maps["time"][:], dtype=float)
    depth = np.nan_to_num(np.maximum(levels - bed[None], 0.0))
    speed = np.nan_to_num(np.hypot(u, v))
    rows, cols = bed.shape

    series = np.load(run_dir / "series.npz")
    t = series["t"]
    nodes = cs.exchange_nodes(scenario)
    stage = np.interp(t, *zip(*scenario.outfall_stage)) if scenario.outfall_stage else None
    inflow = np.interp(t, *zip(*cs.inflow_hydrograph(scenario)))

    data = {
        "scenario": name,
        "description": scenario.description,
        "grid": {
            "rows": rows,
            "cols": cols,
            "cell_m": cs.CELL_SIZE_M,
            "bed_m": np.round(bed, 3).ravel().tolist(),
        },
        "maps": {
            "time_s": time_s.tolist(),
            # depth in mm (uint16), speed in mm/s (uint16), row-major (row = y)
            "depth_mm": encode(np.clip(np.round(depth * 1000), 0, 65535), "<u2"),
            "speed_mm_s": encode(np.clip(np.round(speed * 1000), 0, 65535), "<u2"),
        },
        "network": {
            "nodes": {
                n: {
                    "x_m": x,
                    "y_m": y,
                    "ground_m": cs.surface_elevation_m(x, y),
                    "invert_m": cs.surface_elevation_m(x, y) - scenario.node_depth_m,
                }
                for n, (x, y) in nodes.items()
            },
            "outfall": {
                "x_m": cs.OUTFALL_X_M,
                "y_m": cs.DRAINAGE_LINE_Y_M,
                "invert_m": cs.surface_elevation_m(cs.OUTFALL_X_M, cs.DRAINAGE_LINE_Y_M)
                - scenario.node_depth_m,
            },
            "pipes": [
                {"name": c, "from": a, "to": b, "diameter_m": scenario.pipe_diameters_m[c]}
                for c, a, b in cs.pipes(scenario)
            ],
        },
        "series": {
            "time_s": block_mean(t, SERIES_STEP_S).round(1).tolist(),
            "inflow_m3s": block_mean(inflow, SERIES_STEP_S).round(4).tolist(),
            "outflow_m3s": block_mean(series["sink_q"], SERIES_STEP_S).round(4).tolist(),
            "outfall_stage_m": (
                block_mean(stage, SERIES_STEP_S).round(3).tolist() if stage is not None else None
            ),
            "exchange_m3s": {
                n: block_mean(series[f"q_{n}"], SERIES_STEP_S).round(4).tolist() for n in nodes
            },
            "head_m": {
                n: block_mean(series[f"head_{n}"], SERIES_STEP_S).round(3).tolist() for n in nodes
            },
        },
        "balance": {
            "inflow_m3": result["surface_inflow_m3"],
            "exchanged_m3": result["exchanged_per_node_m3"],
            "swmm_flooded_m3": result["swmm_flooded_m3"],
            "mass_error_pct": result["mass_error_pct_of_inflow"],
        },
    }
    output.write_text(json.dumps(data, separators=(",", ":")))
    print(f"{output}: {output.stat().st_size / 1e6:.2f} MB, {len(time_s)} maps of {rows}x{cols}")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3], Path(sys.argv[4]).resolve())
