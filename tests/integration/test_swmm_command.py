"""``swmm run`` on the real SWMM of pyswmm: files, totals, notices and the CLI."""

import json
from pathlib import Path

import pytest

from hydraulik import run_network
from hydraulik.cli import main
from hydraulik.engines.swmm.network import SwmmSettings, read_network_table, write_inp
from hydraulik.exceptions import ConflictError, InputDataError, InvalidInputError

pytest.importorskip("pyswmm")

NETWORK = (
    Path(__file__).resolve().parents[1] / "fixtures" / "swmm" / "network_chain.csv"
)


def _inflow(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "inflow.csv"
    path.write_text("time_min,discharge_m3s\n" + rows, encoding="utf-8")
    return path


def _names(folder: Path) -> list[str]:
    return sorted(item.name for item in folder.iterdir())


def test_a_network_table_runs_and_only_the_input_and_the_report_are_written(
    tmp_path: Path,
) -> None:
    inflow = _inflow(tmp_path, "0,0\n5,0.05\n10,0.05\n15,0\n")  # 45 m3

    document = run_network(
        network=NETWORK,
        inflow=inflow,
        inflow_node="J1",
        output_dir=tmp_path / "swmm",
    )

    body = document.to_dict()
    assert body["schema"] == "hydraulik-swmm/1"
    assert _names(tmp_path / "swmm") == ["network.inp", "network.rpt"]  # no .out
    assert [f["status"] for f in body["files"]] == ["written", "written"]
    assert body["source"]["kind"] == "network"
    assert body["source"]["inflow"]["node"] == "J1"
    assert body["source"]["inflow"]["volume_m3"] == pytest.approx(
        0.5 * 5 * 60 * 0.05 + 5 * 60 * 0.05 + 0.5 * 5 * 60 * 0.05
    )
    assert body["duration_s"] == 15 * 60 + 10 * 60
    totals = body["totals"]
    assert totals["external_inflow_m3"] == pytest.approx(
        body["source"]["inflow"]["volume_m3"], rel=0.01
    )
    assert totals["flooding_m3"] == 0.0
    # the pipes drained during the recession: nearly all the water left
    assert totals["outflow_m3"] == pytest.approx(totals["external_inflow_m3"], rel=0.05)
    assert {n["name"]: n["kind"] for n in body["nodes"]} == {
        "J1": "junction",
        "J2": "junction",
        "J3": "junction",
        "OUT": "outfall",
    }
    assert {c["name"] for c in body["conduits"]} == {"C_J1", "C_J2", "C_J3"}
    assert "Flow Routing Continuity" in (tmp_path / "swmm" / "network.rpt").read_text()
    assert "FLOW_UNITS" in (tmp_path / "swmm" / "network.inp").read_text()
    assert document.notices == []


def test_an_inflow_beyond_the_capacity_floods_the_node_and_says_so(
    tmp_path: Path,
) -> None:
    inflow = _inflow(tmp_path, "0,1.5\n5,1.5\n5.05,0\n")

    document = run_network(
        network=NETWORK,
        inflow=inflow,
        inflow_node="J1",
        output_dir=tmp_path / "swmm",
    )

    body = document.to_dict()
    flooded = {n["name"] for n in body["nodes"] if n["flooding_volume_m3"] > 0}
    assert "J1" in flooded and "OUT" not in flooded
    assert body["totals"]["flooding_m3"] > 50.0
    codes = {n["code"]: n["level"] for n in document.notices}
    assert codes["flooding"] == "info"
    flooding = next(n for n in document.notices if n["code"] == "flooding")
    assert "J1" in flooding["message"]


def test_the_users_own_input_runs_where_it_is_and_is_copied_to_network_inp(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sewer.inp"
    source.write_text(
        write_inp(read_network_table(NETWORK), SwmmSettings(900.0)), encoding="utf-8"
    )
    inflow = _inflow(tmp_path, "0,0.05\n10,0.05\n")

    document = run_network(
        inp=source,
        inflow=inflow,
        inflow_node="J2",
        output_dir=tmp_path / "swmm",
    )

    body = document.to_dict()
    assert body["source"]["kind"] == "inp" and body["source"]["path"] == str(source)
    assert body["duration_s"] == 900.0  # the end date of the file rules
    assert (tmp_path / "swmm" / "network.inp").read_text() == source.read_text()
    assert body["totals"]["external_inflow_m3"] == pytest.approx(30.0, rel=0.01)


def test_a_hydrograph_that_outlasts_the_run_of_the_users_input_is_a_warning(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sewer.inp"
    source.write_text(
        write_inp(read_network_table(NETWORK), SwmmSettings(300.0)), encoding="utf-8"
    )
    inflow = _inflow(tmp_path, "0,0.02\n10,0.02\n")

    document = run_network(
        inp=source, inflow=inflow, inflow_node="J1", output_dir=tmp_path / "swmm"
    )

    cut = [n for n in document.notices if n["code"] == "inflow_cut"]
    assert [n["level"] for n in cut] == ["warning"]
    assert "600 s" in cut[0]["message"] and "300 s" in cut[0]["message"]


def test_a_node_that_is_not_in_the_users_input_is_refused_after_swmm_opened_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sewer.inp"
    source.write_text(
        write_inp(read_network_table(NETWORK), SwmmSettings(60.0)), encoding="utf-8"
    )

    with pytest.raises(InvalidInputError) as caught:
        run_network(
            inp=source,
            inflow=_inflow(tmp_path, "0,1\n1,1\n"),
            inflow_node="NOPE",
            output_dir=tmp_path / "swmm",
        )

    assert caught.value.details["reason"] == "unknown_node"
    assert list((tmp_path / "swmm").iterdir()) == []  # nothing, not even staging


def test_an_input_that_swmm_rejects_writes_nothing_and_quotes_the_report(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.inp"
    bad.write_text(
        "[OPTIONS]\nFLOW_UNITS CMS\nSTART_DATE nonsense\n[JUNCTIONS]\nJ1 1 2\n",
        encoding="utf-8",
    )

    with pytest.raises(InputDataError) as caught:
        run_network(inp=bad, output_dir=tmp_path / "swmm")

    assert caught.value.details["reason"] == "invalid_inp"
    assert list((tmp_path / "swmm").iterdir()) == []


def test_existing_files_are_a_conflict_until_force_replaces_them(
    tmp_path: Path,
) -> None:
    inflow = _inflow(tmp_path, "0,0.01\n2,0.01\n")
    options = {"network": NETWORK, "inflow": inflow, "inflow_node": "J1"}
    run_network(output_dir=tmp_path / "swmm", **options)  # type: ignore[arg-type]

    with pytest.raises(ConflictError) as caught:
        run_network(output_dir=tmp_path / "swmm", **options)  # type: ignore[arg-type]
    again = run_network(output_dir=tmp_path / "swmm", force=True, **options)  # type: ignore[arg-type]

    assert caught.value.details["reason"] == "output_exists"
    assert [f["status"] for f in again.to_dict()["files"]] == ["replaced"] * 2


def test_the_cli_runs_a_network_and_prints_the_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inflow = _inflow(tmp_path, "0,0.02\n3,0.02\n")

    code = main(
        [
            "swmm",
            "run",
            "--network",
            str(NETWORK),
            "--inflow",
            str(inflow),
            "--inflow-node",
            "J1",
            "--recession-min",
            "5",
            "--routing-step-s",
            "1",
            "--surcharge-method",
            "EXTRAN",
            "-o",
            str(tmp_path / "swmm"),
            "--json",
        ]
    )

    envelope = json.loads(capsys.readouterr().out)
    assert code == 0 and envelope["status"] == "ok"
    assert envelope["command"] == "swmm run"
    assert envelope["result"]["duration_s"] == 3 * 60 + 5 * 60
    assert _names(tmp_path / "swmm") == ["network.inp", "network.rpt"]
