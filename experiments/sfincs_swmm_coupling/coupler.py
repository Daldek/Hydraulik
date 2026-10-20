"""Run one scenario of the SFINCS-SWMM coupling feasibility test.

Coupling scheme (explicit, synchronised at exchange times t_k = k * dt_c):

1. Read the surface water level zs at every exchange cell (SFINCS, BMI)
   and the hydraulic head H at every network node (SWMM, pyswmm).
2. Compute the exchange discharge Q (positive = surface -> network) with
   weir / orifice equations.
3. Limit Q > 0 to the water available in the cell over the longest possible
   SFINCS interval (dt_c + dtmax); SFINCS would otherwise clip zs at the bed
   and silently create water. Optionally (stabilised scheme) limit |Q| * dt_c
   to beta times the volume that would equalise zs and H while the node is
   full (H > ground); this removes the explicit-coupling limit cycle.
4. Impose -Q in SFINCS (qext, m3/s) and advance SFINCS to t_{k+1}.
   SFINCS overshoots t_{k+1} by up to one adaptive step, so the volume that
   actually left the surface is V = Q * (t_sfincs_new - t_sfincs_old).
5. Give SWMM exactly that volume as lateral inflow V / dt_c and advance it
   by dt_c (fixed routing step, lands exactly on t_{k+1}).

Exchanging volumes (not rates) makes the scheme mass-conservative by
construction; the remaining error is a time shift of at most one SFINCS step.

Usage: python coupler.py <scenario> <run_dir> <libsfincs.so>
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import case_setup as cs

GRAVITY = 9.81
INLET_AREA_M2 = 0.25  # 0.5 m x 0.5 m opening
INLET_PERIMETER_M = 2.0
WEIR_COEFFICIENT = 0.4  # Q = Cw * P * h^1.5 * sqrt(2g)
ORIFICE_COEFFICIENT = 0.6  # Q = Co * A * sqrt(2g * dh)
EQUALISATION_FRACTION = 0.5  # beta: share of the equalising volume allowed per interval


class SfincsBmi:
    """Minimal ctypes wrapper around the SFINCS BMI shared library."""

    def __init__(self, library_path: str) -> None:
        self.lib = ctypes.CDLL(library_path)
        self.lib.update_until.argtypes = [ctypes.c_double]

    def _check(self, ierr: int, what: str) -> None:
        if ierr != 0:
            raise RuntimeError(f"SFINCS BMI call '{what}' failed with code {ierr}")

    def initialize(self) -> None:
        self._check(self.lib.initialize(), "initialize")

    def update_until(self, t_target_s: float) -> None:
        self._check(self.lib.update_until(ctypes.c_double(t_target_s)), "update_until")

    def finalize(self) -> None:
        self._check(self.lib.finalize(), "finalize")

    def current_time(self) -> float:
        value = ctypes.c_double()
        self._check(self.lib.get_current_time(ctypes.byref(value)), "get_current_time")
        return value.value

    def end_time(self) -> float:
        value = ctypes.c_double()
        self._check(self.lib.get_end_time(ctypes.byref(value)), "get_end_time")
        return value.value

    def set_logical(self, name: str, value: bool) -> None:
        flag = (ctypes.c_int * 1)(1 if value else 0)
        self._check(self.lib.set_logical(name.encode(), flag), "set_logical")

    def array(self, name: str, ctype) -> np.ndarray:
        """Return a numpy view on a SFINCS array (no copy, writes go to SFINCS)."""
        shape = (ctypes.c_int * 6)()
        self._check(self.lib.get_var_shape(name.encode(), shape), "get_var_shape")
        pointer = ctypes.c_void_p()
        self._check(
            self.lib.get_value_ptr(name.encode(), ctypes.byref(pointer)),
            "get_value_ptr",
        )
        typed = ctypes.cast(pointer, ctypes.POINTER(ctype))
        return np.ctypeslib.as_array(typed, shape=(shape[0],))

    def cell_index(self, x_m: float, y_m: float) -> int:
        """Return the 0-based SFINCS cell index containing the point."""
        index = ctypes.c_int()
        self._check(
            self.lib.get_sfincs_cell_index(
                ctypes.byref(ctypes.c_double(x_m)),
                ctypes.byref(ctypes.c_double(y_m)),
                ctypes.byref(index),
            ),
            "get_sfincs_cell_index",
        )
        if index.value <= 0:
            raise ValueError(f"Point ({x_m}, {y_m}) lies outside the SFINCS grid")
        return index.value - 1

    def cell_area(self, index0: int) -> float:
        area = ctypes.c_double()
        self._check(
            self.lib.get_sfincs_cell_area(
                ctypes.byref(ctypes.c_int(index0 + 1)), ctypes.byref(area)
            ),
            "get_sfincs_cell_area",
        )
        return area.value


def exchange_discharge(zs_m: float, ground_m: float, head_m: float) -> float:
    """Exchange discharge between surface and network node [m3/s].

    Positive values mean flow from the surface into the network.

    Parameters
    ----------
    zs_m : float
        Surface water level in the exchange cell.
    ground_m : float
        Surface (bed) elevation of the exchange cell.
    head_m : float
        Hydraulic head in the network node.
    """
    depth = max(zs_m - ground_m, 0.0)
    if head_m <= ground_m:
        # Free inflow: weir at shallow depth, orifice at larger depth.
        if depth <= 0.0:
            return 0.0
        weir = (
            WEIR_COEFFICIENT * INLET_PERIMETER_M * depth**1.5 * math.sqrt(2 * GRAVITY)
        )
        orifice = ORIFICE_COEFFICIENT * INLET_AREA_M2 * math.sqrt(2 * GRAVITY * depth)
        return min(weir, orifice)
    if head_m < zs_m:
        # Submerged inflow against a partly surcharged node.
        return (
            ORIFICE_COEFFICIENT
            * INLET_AREA_M2
            * math.sqrt(2 * GRAVITY * (zs_m - head_m))
        )
    # Surcharge: the node spills onto the surface.
    return (
        -ORIFICE_COEFFICIENT * INLET_AREA_M2 * math.sqrt(2 * GRAVITY * (head_m - zs_m))
    )


def analytical_rain_volume_m3(t_s: float) -> float:
    """Rain volume over the whole domain up to time t (matches sfincs.prcp)."""
    area = cs.N_CELLS_X * cs.N_CELLS_Y * cs.CELL_SIZE_M**2
    rate = cs.RAIN_INTENSITY_MM_H / 1000.0 / 3600.0
    full = min(t_s, cs.RAIN_DURATION_S)
    ramp = min(max(t_s - cs.RAIN_DURATION_S, 0.0), 1.0)
    ramp_volume = rate * (ramp - 0.5 * ramp**2)
    return area * (rate * full + ramp_volume)


def network_volume_m3(nodes, links) -> float:
    return sum(n.volume for n in nodes.values()) + sum(l.volume for l in links)


def run(scenario: cs.Scenario, run_dir: Path, library_path: str) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    cs.write_sfincs_case(run_dir, scenario)
    swmm_inp = cs.write_swmm_case(run_dir, scenario) if scenario.coupled else None
    os.chdir(run_dir)  # SFINCS reads sfincs.inp from the working directory

    sfincs = SfincsBmi(library_path)
    sfincs.initialize()
    zs = sfincs.array("zs", ctypes.c_double)
    zb = sfincs.array("zb", ctypes.c_float)
    qext = sfincs.array("qext", ctypes.c_float)
    cell_area_m2 = cs.CELL_SIZE_M**2
    t_end = sfincs.end_time()
    dt_c = scenario.exchange_interval_s

    sim = nodes = links = None
    cells, grounds = {}, {}
    if scenario.coupled:
        from pyswmm import Links, Nodes, Simulation, SystemStats

        sfincs.set_logical("qext", True)
        sim = Simulation(str(swmm_inp))
        if dt_c != int(dt_c):
            raise ValueError(
                "SWMM strides in whole seconds; use an integer exchange interval"
            )
        # SWMM advances in 1 s strides (= its routing step) so that the outfall
        # discharge can be integrated accurately for any exchange interval.
        sim.step_advance(cs.SWMM_ROUTING_STEP_S)
        sim.start()
        swmm_start = sim.start_time
        all_nodes = Nodes(sim)
        nodes = {name: all_nodes[name] for name in cs.EXCHANGE_NODES_XY}
        links = [Links(sim)[c] for c in ("C1", "C2", "C3")]
        outfall_link = links[-1]  # positive flow = network -> outfall
        for name, (x, y) in cs.EXCHANGE_NODES_XY.items():
            cells[name] = sfincs.cell_index(x, y)
            grounds[name] = float(zb[cells[name]])
            cell_area_m2 = sfincs.cell_area(cells[name])
        # Consistency check: SWMM rim elevation must equal the SFINCS bed.
        for name, node in nodes.items():
            rim = node.invert_elevation + node.full_depth
            if abs(rim - grounds[name]) > 1e-3:
                raise RuntimeError(
                    f"{name}: SWMM rim {rim:.4f} != SFINCS bed {grounds[name]:.4f}"
                )

    max_removal_window_s = dt_c + cs.SFINCS_DTMAX_S
    series = {
        "t": [],
        "t_sfincs": [],
        "surface_m3": [],
        "network_m3": [],
        "outfall_m3": [],
    }
    for name in cells:
        series[f"q_{name}"] = []
        series[f"head_{name}"] = []
        series[f"zs_{name}"] = []
    overshoot_s, capped_steps, limited_steps = [], 0, 0
    exchanged_m3 = {name: 0.0 for name in cells}
    outfall_out_m3 = 0.0  # net volume through the outfall (positive = leaving)
    outfall_gross_in_m3 = 0.0  # volume entering the network from the outfall
    outfall_flow = 0.0
    zs_max = np.array(zs, copy=True)
    q_previous = {name: 0.0 for name in cells}
    w = scenario.relaxation

    wall_start = time.perf_counter()
    k = 0
    while True:
        t_target = (k + 1) * dt_c
        if t_target > t_end + 1e-9:
            break
        t_old = sfincs.current_time()

        q_now = {}
        for name, cell in cells.items():
            head = nodes[name].head
            q = exchange_discharge(float(zs[cell]), grounds[name], head)
            q = w * q + (1.0 - w) * q_previous[name]
            if scenario.equalisation_limiter and head > grounds[name]:
                area_eq = (cell_area_m2 * cs.NODE_SURFACE_AREA_M2) / (
                    cell_area_m2 + cs.NODE_SURFACE_AREA_M2
                )
                limit = (
                    EQUALISATION_FRACTION * abs(float(zs[cell]) - head) * area_eq / dt_c
                )
                if abs(q) > limit:
                    q = math.copysign(limit, q)
                    limited_steps += 1
            if q > 0.0:
                available = max(float(zs[cell]) - grounds[name], 0.0) * cell_area_m2
                limit = available / max_removal_window_s
                if q > limit:
                    q = limit
                    capped_steps += 1
            q_now[name] = q
            q_previous[name] = q
            qext[cell] = -q

        sfincs.update_until(t_target)
        t_new = sfincs.current_time()
        overshoot_s.append(t_new - t_target)
        np.maximum(zs_max, zs, out=zs_max)

        if scenario.coupled:
            for name, q in q_now.items():
                volume = q * (t_new - t_old)
                exchanged_m3[name] += volume
                nodes[name].generated_inflow(volume / dt_c)
            for _ in range(int(dt_c) // cs.SWMM_ROUTING_STEP_S):
                try:
                    next(sim)
                except StopIteration:
                    # SWMM signals the end of its run on the last stride.
                    if t_target < t_end - 1e-9:
                        raise RuntimeError(
                            f"SWMM stopped early before t = {t_target} s"
                        )
                # Trapezoidal rule, as SWMM's own continuity accounting.
                flow_new = outfall_link.flow
                volume = 0.5 * (outfall_flow + flow_new) * cs.SWMM_ROUTING_STEP_S
                outfall_out_m3 += volume
                outfall_gross_in_m3 += max(-volume, 0.0)
                outfall_flow = flow_new
            swmm_elapsed = (sim.current_time - swmm_start).total_seconds()
            if abs(swmm_elapsed - t_target) > 1e-6:
                raise RuntimeError(f"SWMM at {swmm_elapsed} s, expected {t_target} s")

        depth = np.maximum(zs - zb, 0.0)
        series["t"].append(t_target)
        series["t_sfincs"].append(t_new)
        series["surface_m3"].append(float(depth.sum() * cell_area_m2))
        series["network_m3"].append(network_volume_m3(nodes, links) if links else 0.0)
        series["outfall_m3"].append(outfall_out_m3)
        for name, cell in cells.items():
            series[f"q_{name}"].append(q_now[name])
            series[f"head_{name}"].append(nodes[name].head)
            series[f"zs_{name}"].append(float(zs[cell]))
        k += 1

    wall_s = time.perf_counter() - wall_start

    swmm_stats = {}
    if scenario.coupled:
        routing = SystemStats(sim).routing_stats
        swmm_stats = {key: float(value) for key, value in routing.items()}
        sim.report()
        sim.close()
    sfincs.finalize()

    # Mass balance at the final time.
    t_final = series["t_sfincs"][-1]
    rain = analytical_rain_volume_m3(t_final)
    surface = series["surface_m3"][-1]
    network = series["network_m3"][-1]
    out = series["outfall_m3"][-1]
    conceptual = rain - surface if scenario.conceptual_drainage_mm_h else 0.0
    total_error = rain - surface - network - out - conceptual
    exchanged_total = sum(exchanged_m3.values())

    q_arrays = {name: np.array(series[f"q_{name}"]) for name in cells}
    sign_flips = {
        name: int(np.sum(np.diff(np.sign(q[np.abs(q) > 1e-6])) != 0))
        for name, q in q_arrays.items()
    }

    result = {
        "scenario": scenario.name,
        "description": scenario.description,
        "exchange_interval_s": dt_c,
        "wall_time_s": wall_s,
        "rain_m3": rain,
        "surface_final_m3": surface,
        "network_final_m3": network,
        "outfall_net_m3": out,
        "exchanged_total_m3": exchanged_total,
        "exchanged_per_node_m3": exchanged_m3,
        "mass_error_m3": total_error,
        "mass_error_pct_of_rain": 100.0 * total_error / rain,
        "outfall_gross_inflow_m3": outfall_gross_in_m3,
        "mass_error_pct_of_inflow": 100.0 * total_error / (rain + outfall_gross_in_m3),
        "limited_steps": limited_steps,
        "max_abs_dq_m3s": max(
            (float(np.max(np.abs(np.diff(q)))) for q in q_arrays.values()), default=0.0
        ),
        "surface_side_error_m3": rain - surface - exchanged_total - conceptual,
        "network_side_error_m3": exchanged_total - network - out,
        "swmm_routing_stats": swmm_stats,
        "overshoot_s": {
            "mean": float(np.mean(overshoot_s)),
            "max": float(np.max(overshoot_s)),
            "p95": float(np.percentile(overshoot_s, 95)),
        },
        "capped_steps": capped_steps,
        "sign_flips": sign_flips,
        "max_depth_m": float(np.max(zs_max - zb)),
        "max_depth_at_end_m": float(
            np.max(zs_max[-cs.N_CELLS_Y * 5 :] - zb[-cs.N_CELLS_Y * 5 :])
        ),
        "flooded_area_m2_gt_5cm": float(np.sum((zs_max - zb) > 0.05) * cell_area_m2),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    np.savez(
        run_dir / "series.npz",
        zs_max=zs_max,
        zb=np.array(zb),
        **{key: np.array(value) for key, value in series.items()},
    )
    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    name, directory, library = sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3]
    print(json.dumps(run(cs.SCENARIOS[name], directory, library), indent=2))
