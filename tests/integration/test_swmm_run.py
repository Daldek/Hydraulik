"""Running a SWMM input and reading its results, on the real engine of pyswmm."""

from pathlib import Path

import pytest

from hydraulik.data.tables import Hydrograph
from hydraulik.engines.swmm.network import SwmmSettings, read_network_table, write_inp
from hydraulik.engines.swmm.run import SwmmStepper, SwmmSummary, run_swmm
from hydraulik.exceptions import InputDataError, InvalidInputError, UnsupportedError

pytest.importorskip("pyswmm")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "swmm"


def _inp(tmp_path: Path, duration_s: float = 900.0) -> Path:
    network = read_network_table(FIXTURES / "network_chain.csv")
    path = tmp_path / "network.inp"
    path.write_text(write_inp(network, SwmmSettings(duration_s)), encoding="utf-8")
    return path


def _run(
    tmp_path: Path, inflow: Hydrograph, duration_s: float = 900.0
) -> tuple[Path, SwmmSummary]:
    report = tmp_path / "network.rpt"
    summary = run_swmm(
        _inp(tmp_path, duration_s),
        report,
        tmp_path / "network.out",
        inflows={"J1": inflow},
    )
    return report, summary


def _error_percent(summary: SwmmSummary) -> float:
    """The continuity error from the totals: the same book as SWMM's own report."""
    missing = (
        summary.external_inflow_m3
        - summary.outflow_m3
        - summary.flooding_m3
        - summary.final_storage_m3
    )
    return 100.0 * missing / summary.external_inflow_m3


def test_a_steady_inflow_leaves_by_the_outfall_and_the_water_is_accounted_for(
    tmp_path: Path,
) -> None:
    report, summary = _run(tmp_path, Hydrograph((0.0, 900.0), (0.05, 0.05)))

    assert summary.duration_s == 900.0
    assert summary.external_inflow_m3 == pytest.approx(45.0, rel=0.01)
    assert summary.flooding_m3 == 0.0
    assert (
        0.5 * 45.0 < summary.outflow_m3 < summary.external_inflow_m3
    )  # the pipes fill
    assert _error_percent(summary) == pytest.approx(
        summary.continuity_error_percent, abs=0.01
    )
    assert abs(summary.continuity_error_percent) < 5.0  # SWMM's own error
    assert "Flow Routing Continuity" in report.read_text()


def test_the_statistics_name_every_node_and_conduit(tmp_path: Path) -> None:
    _, summary = _run(tmp_path, Hydrograph((0.0, 900.0), (0.05, 0.05)))

    nodes = {n.name: n for n in summary.nodes}
    links = {link.name: link for link in summary.links}
    assert {name: node.kind for name, node in nodes.items()} == {
        "J1": "junction",
        "J2": "junction",
        "J3": "junction",
        "OUT": "outfall",
    }
    assert nodes["J1"].peak_inflow_m3s == pytest.approx(0.05, rel=0.02)
    assert not any(node.flooded for node in nodes.values())
    assert set(links) == {"C_J1", "C_J2", "C_J3"}
    assert links["C_J3"].peak_flow_m3s == pytest.approx(0.05, rel=0.05)
    assert links["C_J3"].peak_velocity_ms > 0.0


def test_an_inflow_beyond_the_capacity_floods_the_node_and_the_balance_still_closes(
    tmp_path: Path,
) -> None:
    _, summary = _run(tmp_path, Hydrograph((0.0, 300.0, 301.0), (1.5, 1.5, 0.0)))

    flooded = {n.name: n for n in summary.nodes if n.flooded}
    assert "J1" in flooded and "OUT" not in flooded
    assert max(flooded.values(), key=lambda n: n.flooding_volume_m3).name == "J1"
    assert sum(n.flooding_volume_m3 for n in flooded.values()) == pytest.approx(
        summary.flooding_m3
    )
    assert summary.flooding_m3 > 50.0
    assert _error_percent(summary) == pytest.approx(
        summary.continuity_error_percent, abs=0.01
    )


def test_the_volume_of_the_hydrograph_is_what_enters_the_network(
    tmp_path: Path,
) -> None:
    triangle = Hydrograph((0.0, 120.0, 360.0), (0.0, 0.2, 0.0))

    _, summary = _run(tmp_path, triangle)

    assert summary.external_inflow_m3 == pytest.approx(triangle.volume_m3, rel=0.01)


def test_an_inflow_to_a_node_that_is_not_in_the_model_is_refused(
    tmp_path: Path,
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        run_swmm(
            _inp(tmp_path),
            tmp_path / "r.rpt",
            tmp_path / "r.out",
            inflows={"NOPE": Hydrograph((0.0, 1.0), (1.0, 1.0))},
        )

    assert caught.value.details["reason"] == "unknown_node"


def test_an_input_that_swmm_rejects_quotes_the_errors_of_its_report(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.inp"
    bad.write_text(
        "[OPTIONS]\nFLOW_UNITS CMS\nSTART_DATE nonsense\n[JUNCTIONS]\nJ1 1 2\n",
        encoding="utf-8",
    )

    with pytest.raises(InputDataError) as caught:
        SwmmStepper(bad, tmp_path / "bad.rpt", tmp_path / "bad.out")

    assert caught.value.details["reason"] == "invalid_inp"
    assert "invalid date/time" in " ".join(caught.value.details["errors"])


def test_an_input_in_us_units_is_refused_before_swmm_starts(tmp_path: Path) -> None:
    text = _inp(tmp_path).read_text().replace("CMS", "CFS", 1)
    (tmp_path / "us.inp").write_text(text, encoding="utf-8")

    with pytest.raises(UnsupportedError) as caught:
        SwmmStepper(tmp_path / "us.inp", tmp_path / "u.rpt", tmp_path / "u.out")

    assert caught.value.details["reason"] == "flow_units"


def test_the_stride_is_a_whole_number_of_seconds(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError):
        SwmmStepper(_inp(tmp_path), tmp_path / "r.rpt", tmp_path / "r.out", stride_s=0)


def test_the_stepper_gives_heads_flows_and_storage_between_strides(
    tmp_path: Path,
) -> None:
    with SwmmStepper(
        _inp(tmp_path, 120.0), tmp_path / "r.rpt", tmp_path / "r.out"
    ) as s:
        assert s.rim_m("J1") == pytest.approx(9.745)
        assert s.stored_volume_m3() < 0.001  # the pipes are empty
        for _ in range(60):
            s.add_inflow("J1", 0.1)
            assert s.advance()
        assert s.time_s == 60.0
        assert 7.745 < s.head_m("J1") < 9.745
        assert s.stored_volume_m3() > 0.0
        assert s.outfall_flow_m3s() > 0.0
        assert s.flooding_volume_m3("J1") == 0.0
        while s.advance():
            pass
        assert s.ended and s.time_s == s.end_s == 120.0
