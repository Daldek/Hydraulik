"""The generated SWMM input runs on the real SWMM engine that ships with pyswmm."""

from pathlib import Path

import pytest

from hydraulik.engines.swmm import inp as inp_module
from hydraulik.engines.swmm.network import SwmmSettings, read_network_table, write_inp
from hydraulik.engines.swmm.report import routing_continuity_error_percent

pyswmm = pytest.importorskip("pyswmm")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "swmm"


def _run(tmp_path: Path, text: str, inflow_m3s: float) -> tuple[Path, float, float]:
    """Run the INP with a steady inflow at J1; return report, J1 head, outlet flow."""
    inp = tmp_path / "network.inp"
    inp.write_text(text, encoding="utf-8")
    report = tmp_path / "network.rpt"
    with pyswmm.Simulation(str(inp), str(report), str(tmp_path / "network.out")) as sim:
        node = pyswmm.Nodes(sim)["J1"]
        outlet = pyswmm.Links(sim)["C_J3"]
        node.generated_inflow(inflow_m3s)
        for _ in sim:
            pass
        head, outflow = float(node.head), float(outlet.flow)
    return report, head, outflow


def test_generated_input_runs_and_the_steady_outflow_equals_the_inflow(
    tmp_path: Path,
) -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")

    report, head, outflow = _run(
        tmp_path, write_inp(network, SwmmSettings(900.0)), 0.05
    )

    assert routing_continuity_error_percent(report) is not None
    assert network.junctions[0].invert_m < head < network.junctions[0].rim_m
    assert outflow == pytest.approx(0.05, rel=0.05)


def test_a_patched_user_file_is_accepted_by_swmm(tmp_path: Path) -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")
    coarse = write_inp(network, SwmmSettings(900.0), {"ROUTING_STEP": 30})
    patched = inp_module.patch_options(coarse, {"ROUTING_STEP": 0.5})
    patched = inp_module.patch_junction_surcharge(patched, 0.0)

    report, _, outflow = _run(tmp_path, patched, 0.05)

    assert routing_continuity_error_percent(report) is not None
    assert outflow == pytest.approx(0.05, rel=0.05)
