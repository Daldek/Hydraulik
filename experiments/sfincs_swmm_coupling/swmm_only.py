"""SWMM without SFINCS: is the continuity error a property of SWMM itself?

Each test runs one network of the coupled scenarios as a plain SWMM model.
The nodes receive prescribed lateral inflows (SWMM [INFLOWS] time series):
the exchange discharges recorded in the coupled run (signed, i.e. including
the spills taken out of surcharged nodes), the same series with spills
removed, or SWMM numerics varied (surcharge method, routing step, iteration
tolerance). The continuity error is read from SWMM's own report.

Usage: python swmm_only.py   (needs runs/<scenario>/series.npz of the coupled runs)
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import numpy as np
from pyswmm import Simulation

import case_setup as cs

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs" / "swmm_only"

# name: (coupled scenario providing network + inflows, inflow mode, SWMM options)
TESTS = {
    "base_replay_slot_rs1": (
        "V_base",
        "signed",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 1},
    ),
    "base_replay_slot_rs05": (
        "V_base",
        "signed",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.5},
    ),
    "base_replay_slot_rs025": (
        "V_base",
        "signed",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.25},
    ),
    "base_replay_slot_tight": (
        "V_base",
        "signed",
        {
            "SURCHARGE_METHOD": "SLOT",
            "ROUTING_STEP": 0.5,
            "HEAD_TOLERANCE": 0.00005,
            "MAX_TRIALS": 50,
        },
    ),
    "base_replay_extran_rs05": (
        "V_base",
        "signed",
        {"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.5},
    ),
    "base_positive_slot_rs05": (
        "V_base",
        "positive",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.5},
    ),
    "base_positive_extran_rs05": (
        "V_base",
        "positive",
        {"SURCHARGE_METHOD": "EXTRAN", "ROUTING_STEP": 0.5},
    ),
    "base_positive_slot_tight": (
        "V_base",
        "positive",
        {
            "SURCHARGE_METHOD": "SLOT",
            "ROUTING_STEP": 0.5,
            "HEAD_TOLERANCE": 0.00005,
            "MAX_TRIALS": 50,
        },
    ),
    "nodes12_replay_slot_rs05": (
        "V_nodes_12",
        "signed",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.5},
    ),
    "nodes12_positive_slot_rs05": (
        "V_nodes_12",
        "positive",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.5},
    ),
    "nodes12_positive_slot_tight": (
        "V_nodes_12",
        "positive",
        {
            "SURCHARGE_METHOD": "SLOT",
            "ROUTING_STEP": 0.5,
            "HEAD_TOLERANCE": 0.00005,
            "MAX_TRIALS": 50,
        },
    ),
    "depth4_positive_slot_rs05": (
        "V_depth_4",
        "positive",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.5},
    ),
    "free_replay_slot_rs05": (
        "V1_base",
        "signed",
        {"SURCHARGE_METHOD": "SLOT", "ROUTING_STEP": 0.5},
    ),
}


def inflow_series(scenario: str, mode: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Exchange discharge per node from the coupled run (optionally spills removed)."""
    data = np.load(HERE / "runs" / scenario / "series.npz")
    t = np.concatenate([[0.0], data["t"]])
    series = {}
    for key in data.files:
        if key.startswith("q_J"):
            q = np.concatenate([[0.0], data[key]])
            series[key[2:]] = (t, np.maximum(q, 0.0) if mode == "positive" else q)
    return series


def build_inp(test: str, scenario: cs.Scenario, inflows, options: dict) -> Path:
    run_dir = RUNS / test
    run_dir.mkdir(parents=True, exist_ok=True)
    text = cs.write_swmm_case(
        run_dir, replace(scenario, outfall_stage=scenario.outfall_stage)
    ).read_text()
    for key, value in options.items():
        pattern = rf"(?m)^{key}\s+.*$"
        line = f"{key:<21}{value}"
        text = (
            re.sub(pattern, line, text)
            if re.search(pattern, text)
            else text.replace("[JUNCTIONS]", f"{line}\n\n[JUNCTIONS]", 1)
        )
    rows = []
    for node, (t, q) in inflows.items():
        # Piecewise-constant coupled inflow (value held over the preceding
        # second) written as a step series: two points per value.
        for t0, t1, value in zip(t[:-1], t[1:], q[1:]):
            rows.append(f"TS_{node} {t0 / 3600 + 1e-7:.8f} {value:.6f}")
            rows.append(f"TS_{node} {t1 / 3600:.8f} {value:.6f}")
    text += "\n[TIMESERIES]\n" + "\n".join(rows) + "\n"
    text += "\n[INFLOWS]\n" + "".join(
        f"{node} FLOW TS_{node} FLOW 1.0 1.0\n" for node in inflows
    )
    path = run_dir / "network.inp"
    path.write_text(text)
    return path


def continuity_error_pct(report: Path) -> float:
    matches = re.findall(r"Continuity Error \(%\) \.+\s+(-?[\d.]+)", report.read_text())
    return float(matches[-1])  # the last one is flow routing


def main() -> None:
    results = {}
    for test, (scenario_name, mode, options) in TESTS.items():
        scenario = cs.SCENARIOS[scenario_name]
        inp = build_inp(test, scenario, inflow_series(scenario_name, mode), options)
        report = inp.with_suffix(".rpt")
        with Simulation(str(inp), str(report), str(inp.with_suffix(".out"))) as sim:
            for _ in sim:
                pass
        error = continuity_error_pct(report)
        results[test] = {
            "scenario": scenario_name,
            "inflow": mode,
            "options": options,
            "routing_error_pct": error,
        }
        print(f"{test:30} {error:+7.3f} %")
    (HERE / "results" / "swmm_only.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
