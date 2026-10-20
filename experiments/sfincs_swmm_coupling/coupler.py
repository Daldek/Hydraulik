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
from dataclasses import dataclass
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
# Legacy exchange law (v1): 0.5 m x 0.5 m grate, textbook coefficients,
# discontinuous switch between weir and orifice when the node head crosses
# the ground level.
INLET_AREA_M2 = 0.25
INLET_PERIMETER_M = 2.0
WEIR_COEFFICIENT = 0.4  # Q = Cw * P * h^1.5 * sqrt(2g)
ORIFICE_COEFFICIENT = 0.6  # Q = Co * A * sqrt(2g * dh)

# Continuous exchange law (v2, default). Coefficients calibrated for a
# manhole by Rubinato et al. (2017, J. Hydrol. 552:421-432,
# doi:10.1016/j.jhydrol.2017.06.024), referenced - as in Itzi - to the node
# surface area A and the perimeter of a circle of that area, P = 2*sqrt(pi*A).
RUBINATO_WEIR_COEFFICIENT = 0.54  # Q = 2/3 * Cw * P * h^1.5 * sqrt(2g)
RUBINATO_ORIFICE_COEFFICIENT = 0.167  # Q = Co * A * sqrt(2g * dh)


@dataclass(frozen=True)
class Inlet:
    """Geometry and coefficients of the continuous exchange law (v2)."""

    area_m2: float = cs.NODE_SURFACE_AREA_M2
    weir_coefficient: float = RUBINATO_WEIR_COEFFICIENT
    orifice_coefficient: float = RUBINATO_ORIFICE_COEFFICIENT

    @property
    def perimeter_m(self) -> float:
        return 2.0 * math.sqrt(math.pi * self.area_m2)


# One scenario runs per process; run() sets the inlet of that scenario here.
INLET = Inlet()
ORIFICE_LINEAR_BELOW_M = 0.01  # orifice law linearised for |dh| below this

# Semi-implicit exchange in delta form: Q_k = Q_{k-1} + (Q0 - Q_{k-1}) / (1 + K),
# a linearised backward-Euler step for the change of the exchange discharge.
DERIVATIVE_STEP_M = 1e-4  # finite-difference step for dQ/dzs and dQ/dH
MEASURED_NODE_AREA_MIN_M2 = 0.01  # bounds of the measured node storage area
MEASURED_NODE_AREA_MAX_M2 = 1.0e4
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


def exchange_discharge(
    zs_m: float, ground_m: float, head_m: float, law: str = "continuous"
) -> float:
    """Exchange discharge between surface and network node [m3/s].

    Positive values mean flow from the surface into the network.
    ``law`` selects the continuous formulation (default) or the legacy one.

    Parameters
    ----------
    zs_m : float
        Surface water level in the exchange cell.
    ground_m : float
        Surface (bed) elevation of the exchange cell.
    head_m : float
        Hydraulic head in the network node.
    law : str
        "continuous" (v2) or "legacy" (v1).
    """
    if law == "continuous":
        return continuous_exchange_discharge(zs_m, ground_m, head_m)
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


def orifice_discharge(head_difference_m: float) -> float:
    """Orifice law Co*A*sqrt(2g*dh), linearised for small dh (bounded slope)."""
    dh = abs(head_difference_m)
    coefficient = INLET.orifice_coefficient * INLET.area_m2 * math.sqrt(2 * GRAVITY)
    if dh < ORIFICE_LINEAR_BELOW_M:
        return (
            coefficient
            * math.sqrt(ORIFICE_LINEAR_BELOW_M)
            * dh
            / ORIFICE_LINEAR_BELOW_M
        )
    return coefficient * math.sqrt(dh)


def continuous_exchange_discharge(zs_m: float, ground_m: float, head_m: float) -> float:
    """Exchange discharge that is continuous in zs and the node head [m3/s].

    Positive values mean flow from the surface into the network.

    - Node head above the surface level: the node spills (orifice law).
    - Otherwise inflow over the manhole rim: a free weir, reduced by the
      Villemonte (1947) submergence factor once the node head rises above
      the rim, and capped by the orifice law for the head difference.

    Every branch tends to the same value at its boundary (zero at zs = H,
    the free-weir value at H = rim), so the discharge has no jumps.
    """
    if head_m >= zs_m:
        return -orifice_discharge(head_m - zs_m)
    upstream_depth = zs_m - ground_m
    if upstream_depth <= 0.0:
        return 0.0
    weir = (
        2.0
        / 3.0
        * INLET.weir_coefficient
        * INLET.perimeter_m
        * upstream_depth**1.5
        * math.sqrt(2 * GRAVITY)
    )
    downstream_depth = head_m - ground_m
    if downstream_depth > 0.0:
        ratio = downstream_depth / upstream_depth
        weir *= (1.0 - ratio**1.5) ** 0.385
    # Below the rim the water falls freely into the manhole: the orifice head
    # is the surface depth, not the difference with the (lower) node head.
    return min(weir, orifice_discharge(zs_m - max(head_m, ground_m)))


def semi_implicit_discharge(
    zs_m: float,
    ground_m: float,
    head_m: float,
    law: str,
    interval_s: float,
    surface_area_m2: float,
    node_area_m2: float,
    q_previous_m3s: float,
) -> float:
    """Exchange discharge from a linearised implicit step in delta form.

    Changing the exchange by dQ over one interval lowers the surface by
    dQ*dt/A_s and raises the node head by dQ*dt/A_n. Evaluating the exchange
    law at those levels, linearised, gives
        Q_k = Q_{k-1} + (Q0 - Q_{k-1}) / (1 + K),
        K = dt * (dQ/dzs / A_s - dQ/dH / A_n) >= 0,
    i.e. under-relaxation with w = 1/(1+K) derived from the stiffness of the
    link. K is large only where the law is stiff (small head difference, small
    node storage). Only the change of Q is damped, so a steady state is not
    biased (a non-delta form Q = Q0/(1+K) reduces steady exchange).
    """
    q0 = exchange_discharge(zs_m, ground_m, head_m, law)
    e = DERIVATIVE_STEP_M
    dq_dzs = (
        exchange_discharge(zs_m + e, ground_m, head_m, law)
        - exchange_discharge(zs_m - e, ground_m, head_m, law)
    ) / (2 * e)
    dq_dh = (
        exchange_discharge(zs_m, ground_m, head_m + e, law)
        - exchange_discharge(zs_m, ground_m, head_m - e, law)
    ) / (2 * e)
    stiffness = interval_s * (dq_dzs / surface_area_m2 - dq_dh / node_area_m2)
    return q_previous_m3s + (q0 - q_previous_m3s) / (1.0 + max(stiffness, 0.0))


def analytical_rain_volume_m3(t_s: float) -> float:
    """Rain volume over the whole domain up to time t (matches sfincs.prcp)."""
    area = cs.N_CELLS_X * cs.N_CELLS_Y * cs.CELL_SIZE_M**2
    rate = cs.RAIN_INTENSITY_MM_H / 1000.0 / 3600.0
    full = min(t_s, cs.RAIN_DURATION_S)
    ramp = min(max(t_s - cs.RAIN_DURATION_S, 0.0), 1.0)
    ramp_volume = rate * (ramp - 0.5 * ramp**2)
    return area * (rate * full + ramp_volume)


def analytical_inflow_volume_m3(t_s: float, scenario: cs.Scenario) -> float:
    """Surface inflow volume up to time t (piecewise-linear hydrograph)."""
    points = cs.inflow_hydrograph(scenario)
    volume = 0.0
    for (t0, q0), (t1, q1) in zip(points, points[1:]):
        if t_s <= t0:
            break
        t_upper = min(t_s, t1)
        q_upper = q0 + (q1 - q0) * (t_upper - t0) / (t1 - t0)
        volume += 0.5 * (q0 + q_upper) * (t_upper - t0)
    return volume


def steady_state_statistics(
    series: dict, nodes: list[str], scenario: cs.Scenario
) -> list[dict]:
    """Mean, spread and sign flips of the exchange at the end of each step."""
    t = np.array(series["t"])
    hydrograph = cs.inflow_hydrograph(scenario)
    step_ends = [
        t1
        for (_, q0), (t1, q1) in zip(hydrograph, hydrograph[1:])
        if q0 == q1 and q0 > 0.0
    ]
    statistics = []
    for t_end in step_ends:
        window = (t > t_end - cs.STEADY_WINDOW_S) & (t <= t_end)
        half = (t > t_end - cs.STEADY_WINDOW_S / 2) & (t <= t_end)
        entry = {
            "t_end_s": t_end,
            "inflow_m3s": float(np.interp(t_end, *zip(*hydrograph))),
            "outflow_m3s": float(np.mean(np.array(series["sink_q"])[window])),
        }
        for name in nodes:
            q = np.array(series[f"q_{name}"])
            qw = q[window]
            entry[name] = {
                "mean_m3s": float(qw.mean()),
                "std_m3s": float(qw.std()),
                "min_m3s": float(qw.min()),
                "max_m3s": float(qw.max()),
                "sign_flips": int(np.sum(np.diff(np.sign(qw[np.abs(qw) > 1e-6])) != 0)),
                # Drift: mean of the second half minus mean of the whole window.
                "drift_m3s": float(q[half].mean() - qw.mean()),
            }
        statistics.append(entry)
    return statistics


def network_volume_m3(nodes, links) -> float:
    return sum(n.volume for n in nodes.values()) + sum(l.volume for l in links)


def run(scenario: cs.Scenario, run_dir: Path, library_path: str) -> dict:
    global INLET
    INLET = Inlet(
        area_m2=scenario.inlet_area_m2,
        weir_coefficient=RUBINATO_WEIR_COEFFICIENT * scenario.inlet_coefficient_scale,
        orifice_coefficient=RUBINATO_ORIFICE_COEFFICIENT
        * scenario.inlet_coefficient_scale,
    )
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
        exchange_nodes = cs.exchange_nodes(scenario)
        nodes = {name: all_nodes[name] for name in exchange_nodes}
        links = [Links(sim)[c] for c, _, _ in cs.pipes(scenario)]
        outfall_link = links[-1]  # positive flow = network -> outfall
        for name, (x, y) in exchange_nodes.items():
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
        "sink_m3": [],
        "sink_q": [],
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
    # Node storage area for the semi-implicit scheme: fixed (SWMM MIN_SURFAREA)
    # or measured from the head response to the volume injected last interval.
    node_area = {name: cs.NODE_SURFACE_AREA_M2 for name in cells}
    head_previous = {name: None for name in cells}
    volume_previous = {name: 0.0 for name in cells}
    for name in cells:
        series[f"area_{name}"] = []

    # Free outflow at the downstream edge (inflow forcing only): the coupler
    # removes the water standing in the last column and books its volume.
    sink_cells = []
    if scenario.forcing == "inflow":
        sink_cells = [sfincs.cell_index(x, y) for x, y in cs.outflow_points()]
    sink_m3 = 0.0

    flooding_mode = scenario.spill_mode == "swmm_flooding"
    pending_m3 = {name: 0.0 for name in cells}  # flooded, not yet on the surface
    flooded_m3 = {name: 0.0 for name in cells}  # cumulative SWMM flooding

    wall_start = time.perf_counter()
    k = 0
    while True:
        t_target = (k + 1) * dt_c
        if t_target > t_end + 1e-9:
            break
        t_old = sfincs.current_time()

        q_now, q_in, spill_rate = {}, {}, {}
        for name, cell in cells.items():
            head = nodes[name].head
            if scenario.semi_implicit == "measured" and head_previous[name] is not None:
                volume = volume_previous[name]
                rise = head - head_previous[name]
                # Only a response in the direction of the injected volume is
                # attributed to it; otherwise the last estimate is kept.
                if abs(volume) > 1e-6 and abs(rise) > 1e-6 and volume * rise > 0:
                    node_area[name] = min(
                        max(volume / rise, MEASURED_NODE_AREA_MIN_M2),
                        MEASURED_NODE_AREA_MAX_M2,
                    )
            if scenario.semi_implicit:
                q = semi_implicit_discharge(
                    float(zs[cell]),
                    grounds[name],
                    head,
                    scenario.exchange_law,
                    dt_c,
                    cell_area_m2,
                    node_area[name],
                    q_previous[name],
                )
            else:
                q = exchange_discharge(
                    float(zs[cell]), grounds[name], head, scenario.exchange_law
                )
            head_previous[name] = head
            if flooding_mode:
                # Spills come from SWMM's own flooding, never from a negative
                # lateral inflow: only surface -> node discharge is imposed.
                q = max(q, 0.0)
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
            q_previous[name] = q
            q_in[name] = q
            spill_rate[name] = pending_m3[name] / dt_c if flooding_mode else 0.0
            q_now[name] = q - spill_rate[name]
            qext[cell] = -q_now[name]

        sink_q = 0.0
        for cell in sink_cells:
            q = max(float(zs[cell]) - float(zb[cell]), 0.0) * cell_area_m2
            q /= max_removal_window_s
            qext[cell] = -q
            sink_q += q

        sfincs.update_until(t_target)
        t_new = sfincs.current_time()
        overshoot_s.append(t_new - t_target)
        np.maximum(zs_max, zs, out=zs_max)
        sink_m3 += sink_q * (t_new - t_old)

        if scenario.coupled:
            for name in q_now:
                volume_in = q_in[name] * (t_new - t_old)
                volume_spilled = spill_rate[name] * (t_new - t_old)
                pending_m3[name] -= volume_spilled
                exchanged_m3[name] += volume_in - volume_spilled
                volume_previous[name] = volume_in - volume_spilled
                nodes[name].generated_inflow(volume_in / dt_c)
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
            if flooding_mode:
                # Water SWMM floods out of a full node goes back to the surface
                # cell over the next interval (exact volume, one-step lag).
                for name, node in nodes.items():
                    flooded = node.statistics["flooding_volume"]
                    pending_m3[name] += flooded - flooded_m3[name]
                    flooded_m3[name] = flooded
            swmm_elapsed = (sim.current_time - swmm_start).total_seconds()
            if abs(swmm_elapsed - t_target) > 1e-6:
                raise RuntimeError(f"SWMM at {swmm_elapsed} s, expected {t_target} s")

        depth = np.maximum(zs - zb, 0.0)
        series["t"].append(t_target)
        series["t_sfincs"].append(t_new)
        series["surface_m3"].append(float(depth.sum() * cell_area_m2))
        series["network_m3"].append(network_volume_m3(nodes, links) if links else 0.0)
        series["outfall_m3"].append(outfall_out_m3)
        series["sink_m3"].append(sink_m3)
        series["sink_q"].append(sink_q)
        for name, cell in cells.items():
            series[f"q_{name}"].append(q_now[name])
            series[f"head_{name}"].append(nodes[name].head)
            series[f"zs_{name}"].append(float(zs[cell]))
            series[f"area_{name}"].append(node_area[name])
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
    if scenario.forcing == "inflow":
        rain, inflow = 0.0, analytical_inflow_volume_m3(t_final, scenario)
    else:
        rain, inflow = analytical_rain_volume_m3(t_final), 0.0
    surface = series["surface_m3"][-1]
    network = series["network_m3"][-1]
    out = series["outfall_m3"][-1]
    sink = series["sink_m3"][-1]
    conceptual = rain - surface if scenario.conceptual_drainage_mm_h else 0.0
    pending_total = sum(pending_m3.values())
    total_error = (
        rain + inflow - surface - network - out - sink - conceptual - pending_total
    )
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
        "forcing": scenario.forcing,
        "rain_m3": rain,
        "surface_inflow_m3": inflow,
        "downstream_outflow_m3": sink,
        "surface_final_m3": surface,
        "network_final_m3": network,
        "outfall_net_m3": out,
        "exchanged_total_m3": exchanged_total,
        "exchanged_per_node_m3": exchanged_m3,
        "mass_error_m3": total_error,
        "mass_error_pct_of_rain": (
            100.0 * total_error / rain if rain > 0.0 else float("nan")
        ),
        "outfall_gross_inflow_m3": outfall_gross_in_m3,
        "mass_error_pct_of_inflow": (
            100.0 * total_error / (rain + inflow + outfall_gross_in_m3)
        ),
        "limited_steps": limited_steps,
        "max_abs_dq_m3s": max(
            (float(np.max(np.abs(np.diff(q)))) for q in q_arrays.values()), default=0.0
        ),
        "surface_side_error_m3": (
            rain + inflow - surface - exchanged_total - sink - conceptual
        ),
        "network_side_error_m3": exchanged_total - pending_total - network - out,
        "spill_mode": scenario.spill_mode,
        "swmm_flooded_m3": sum(flooded_m3.values()),
        "pending_spill_m3": pending_total,
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
        "steady_states": (
            steady_state_statistics(series, list(cells), scenario)
            if scenario.forcing == "inflow"
            else []
        ),
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
