"""Run one A Coruna configuration with the SFINCS-SWMM coupling.

Coupling as recommended for screening in the feasibility test, with one
addition needed at laboratory resolution: a grate covers many 5 cm cells, so
each inlet exchanges with all cells inside its outline (footprint).

Every exchange interval (0.2 s by default):
1. Depth over the grate = mean (or max) water depth of the footprint cells.
2. Inflow Q = inlet_discharge(...), limited to the water standing in the
   footprint over the longest possible SFINCS interval.
3. Q is taken out of the footprint cells (qext) in proportion to the water in
   each cell; with the measured rain map the rain is added through qext too.
4. SFINCS advances; the volume that left the surface is Q * actual interval.

Every second the volumes of the five intervals go to SWMM (generated inflow of
the manhole each grate drains into) and SWMM advances one second. Spills (SWMM flooding, SurDepth = 0) would return to the
footprint of the manhole's own inlet; none occur in these tests.

Usage: python run_coruna.py <run name> <run dir> <libsfincs.so>
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # experiments/sfincs_swmm_coupling
from coupler import SfincsBmi  # noqa: E402

import coruna_setup as cs  # noqa: E402

PRIMARY_INLET = {"MH_1": "IN1", "MH_2": "IN2", "MH_3": "IN3", "MH_4": "IN4"}


def run(config: cs.Config, run_dir: Path, library_path: str) -> dict:
    from pyswmm import Links, Nodes, Simulation, SystemStats

    run_dir.mkdir(parents=True, exist_ok=True)
    grid = cs.build_grid(config.cell_size_m)
    cs.write_sfincs_case(run_dir, config, grid)
    swmm_inp = cs.write_swmm_case(run_dir, config)
    os.chdir(run_dir)  # SFINCS reads sfincs.inp from the working directory

    sfincs = SfincsBmi(library_path)
    sfincs.initialize()
    sfincs.set_logical("qext", True)
    zs = sfincs.array("zs", ctypes.c_double)
    zb = sfincs.array("zb", ctypes.c_float)
    qext = sfincs.array("qext", ctypes.c_float)
    cell_area = grid.cell_size**2
    t_end = sfincs.end_time()

    footprints = {
        name: np.array([sfincs.cell_index(x, y) for x, y in grid.cells_in_box(box)])
        for name, (box, _) in cs.INLETS.items()
    }
    gauges = {
        name: sfincs.cell_index(x, y) for name, (x, y) in cs.depth_gauges().items()
    }

    # Rain through qext (measured map): per-cell rate for each nominal intensity.
    rain_rate = {}
    if config.rain == "map":
        x, y = grid.centres()
        order = np.array(
            [
                sfincs.cell_index(xc, yc)
                for xc, yc in zip(x[grid.active], y[grid.active])
            ]
        )
        for intensity in {b[2] for b in cs.rain_blocks(config)}:
            values = cs.rain_map_mm_h(grid, intensity)[grid.active]
            rate = np.zeros(len(zs))
            rate[order] = values / 1000.0 / 3600.0 * cell_area
            rain_rate[intensity] = rate
    rain_map_m3 = 0.0

    sim = Simulation(str(swmm_inp))
    sim.step_advance(1)
    sim.start()
    nodes = Nodes(sim)
    manholes = {name: nodes[name] for name in PRIMARY_INLET}
    outfall_link = Links(sim)[cs.OUTFALL_CONDUIT]
    links = [Links(sim)[name] for name in cs.CONDUITS]

    dt_x = config.exchange_interval_s
    substeps = round(1.0 / dt_x)
    window = dt_x + config.sfincs_dtmax_s  # longest SFINCS interval per exchange
    pending = {name: 0.0 for name in manholes}
    flooded = {name: 0.0 for name in manholes}
    exchanged = {name: 0.0 for name in cs.INLETS}
    outfall_m3 = 0.0
    outfall_flow = 0.0

    series = {"t": [], "outfall_q": [], "t_s": [], "surface_m3": [], "network_m3": []}
    for name in cs.INLETS:
        series[f"q_{name}"] = []
    for name in gauges:
        series[f"depth_{name}"] = []
    for name in manholes:
        series[f"head_{name}"] = []
        series[f"inflow_{name}"] = []

    wall_start = time.perf_counter()
    for second in range(int(round(t_end))):
        volume = {name: 0.0 for name in cs.INLETS}
        # Water flooded out of a manhole last second returns over this second.
        spill_rate = {name: pending[name] / 1.0 for name in manholes}
        for sub in range(substeps):
            t_target = second + (sub + 1) * dt_x
            t_old = sfincs.current_time()
            depth = np.maximum(np.asarray(zs) - np.asarray(zb), 0.0)
            if config.rain == "map":
                intensity = cs.rain_intensity_mm_h(config, t_old + 0.5 * dt_x)
                rate = rain_rate.get(intensity)
                qext[:] = rate if rate is not None else 0.0
            else:
                qext[:] = 0.0
            q_in = {}
            for name, (box, manhole) in cs.INLETS.items():
                cells = footprints[name]
                d = depth[cells]
                h = d.mean() if config.inlet_depth == "mean" else d.max()
                ground = float(np.mean(np.asarray(zb)[cells]))
                q = cs.inlet_discharge(
                    float(h),
                    manholes[manhole].head,
                    ground,
                    box,
                    config.inlet_coefficient_scale,
                )
                available = float(d.sum()) * cell_area
                q = min(q, available / window)
                q_in[name] = q
                if q > 0.0:
                    qext[cells] -= q * d / d.sum()
            for manhole, inlet in PRIMARY_INLET.items():
                if spill_rate[manhole] > 0.0:
                    # Spill back onto the grate of the manhole's own inlet.
                    cells = footprints[inlet]
                    qext[cells] += spill_rate[manhole] / len(cells)
            sfincs.update_until(t_target)
            t_new = sfincs.current_time()
            interval = t_new - t_old
            if config.rain == "map":
                intensity = cs.rain_intensity_mm_h(config, t_old + 0.5 * dt_x)
                if intensity in rain_rate:
                    rain_map_m3 += float(rain_rate[intensity].sum()) * interval
            for name, q in q_in.items():
                volume[name] += q * interval
                exchanged[name] += q * interval
                series[f"q_{name}"].append(q)
            for manhole, rate in spill_rate.items():
                spilled = rate * interval
                pending[manhole] -= spilled
                exchanged[PRIMARY_INLET[manhole]] -= spilled
            series["t"].append(t_target - cs.SPINUP_S)
            depth_now = np.maximum(np.asarray(zs) - np.asarray(zb), 0.0)
            for name, cell in gauges.items():
                series[f"depth_{name}"].append(float(depth_now[cell]))

        # SWMM: one second with the volumes collected above.
        inflow = {name: 0.0 for name in manholes}
        for name, (_, manhole) in cs.INLETS.items():
            inflow[manhole] += volume[name] / 1.0
        for name, node in manholes.items():
            node.generated_inflow(inflow[name])
        try:
            next(sim)
        except StopIteration:
            if second + 1 < int(round(t_end)):
                raise RuntimeError(f"SWMM stopped early at {second + 1} s")
        flow_new = outfall_link.flow
        outfall_m3 += 0.5 * (outfall_flow + flow_new) * 1.0
        outfall_flow = flow_new
        for name, node in manholes.items():
            total = node.statistics["flooding_volume"]
            pending[name] += total - flooded[name]
            flooded[name] = total
            series[f"head_{name}"].append(node.head)
            series[f"inflow_{name}"].append(inflow[name])
        depth_now = np.maximum(np.asarray(zs) - np.asarray(zb), 0.0)
        series["t_s"].append(second + 1 - cs.SPINUP_S)
        series["outfall_q"].append(flow_new)
        series["surface_m3"].append(float(depth_now.sum()) * cell_area)
        series["network_m3"].append(
            sum(n.volume for n in manholes.values())
            + sum(n.volume for n in (nodes["PI_1"], nodes["PI_2"]))
            + sum(link.volume for link in links)
        )

    wall_s = time.perf_counter() - wall_start
    routing = SystemStats(sim).routing_stats
    sim.report()
    sim.close()
    t_final = sfincs.current_time()
    sfincs.finalize()

    active_area = float(grid.active.sum()) * cell_area
    if config.rain == "map":
        rain_m3 = rain_map_m3
    else:
        rain_m3 = (
            cs.series_integral(cs.rain_series(config), t_final)
            / 1000.0
            / 3600.0
            * active_area
        )
    runoff_m3 = cs.runoff_volume_m3(config, t_final)
    exchanged_total = sum(exchanged.values())
    surface_final = series["surface_m3"][-1]
    network_final = series["network_m3"][-1]
    result = {
        "run": config.name,
        "config": {k: v for k, v in vars(config).items()},
        "active_cells": int(grid.active.sum()),
        "active_area_m2": active_area,
        "footprint_cells": {name: int(len(c)) for name, c in footprints.items()},
        "wall_time_s": wall_s,
        "rain_m3": rain_m3,
        "runoff_generators_m3": runoff_m3,
        "exchanged_m3": exchanged,
        "surface_final_m3": surface_final,
        "network_final_m3": network_final,
        "outfall_m3": outfall_m3,
        "swmm_flooded_m3": sum(flooded.values()),
        "pending_spill_m3": sum(pending.values()),
        "surface_side_error_m3": rain_m3 + runoff_m3 - surface_final - exchanged_total,
        "network_side_error_m3": (
            exchanged_total
            - sum(pending.values())
            - network_final
            - outfall_m3
        ),
        "swmm_routing_error_pct": float(routing["routing_error"]),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    np.savez(run_dir / "series.npz", **{k: np.array(v) for k, v in series.items()})
    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    name, directory, library = sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3]
    print(json.dumps(run(cs.RUNS[name], directory, library), indent=2))
