"""SWMM alone: head spikes when a node becomes surcharged (EXTRAN).

Replays the surface-to-network inflows of the coupled backwater run
(V3_base_flood_extran_norelax, needs runs/<scenario>/series.npz) in a plain
SWMM model and reports, per node, the largest head change within 1 s and the
highest head between 2000 and 2560 s (before the backwater really reaches the
manhole rims). Spikes that also appear here come from SWMM, not from the
coupling. README section 7.1.

Usage: python swmm_spikes.py
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from pyswmm import Nodes, Simulation

import case_setup as cs
import swmm_only as so

SOURCE = "V3_base_flood_extran_norelax"
WINDOW_S = (2000, 2560)

BASE = cs.SCENARIOS[SOURCE]
VARIANTS = {
    "EXTRAN, step 0.5 s (as coupled)": ({"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.5}, BASE),
    "EXTRAN, step 0.1 s": ({"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.1}, BASE),
    "EXTRAN, no cap at the rim": (
        {"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.5},
        replace(BASE, spill_mode="exchange"),
    ),
    "EXTRAN, INERTIAL_DAMPING FULL": (
        {"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.5, "INERTIAL_DAMPING": "FULL"},
        BASE,
    ),
    "EXTRAN, tight head tolerance": (
        {"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.5, "HEAD_TOLERANCE": 0.00005, "MAX_TRIALS": 50},
        BASE,
    ),
    "EXTRAN, MIN_SURFAREA 12 m2": (
        {"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.5, "MIN_SURFAREA": 12},
        BASE,
    ),
    "SLOT, step 0.5 s": ({"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.5}, BASE),
}


def main() -> None:
    inflows = so.inflow_series(SOURCE, "positive")
    for number, (label, (options, scenario)) in enumerate(VARIANTS.items()):
        inp = so.build_inp(f"spikes_{number}", scenario, inflows, options)
        heads = {name: [] for name in cs.exchange_nodes(scenario)}
        with Simulation(str(inp)) as sim:
            sim.step_advance(1)
            nodes = Nodes(sim)
            for _ in sim:
                for name in heads:
                    heads[name].append(nodes[name].head)
        t = np.arange(1, len(next(iter(heads.values()))) + 1)
        inside = (t > WINDOW_S[0]) & (t < WINDOW_S[1])
        cells = []
        for name, h in heads.items():
            h = np.array(h)
            jump = np.abs(np.diff(h))[inside[1:]].max()
            cells.append(f"{name}: jump {jump:.2f} m/s, max {h[inside].max():.3f} m")
        print(f"{label:34} | " + " | ".join(cells))


if __name__ == "__main__":
    main()
