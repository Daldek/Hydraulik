"""``swmm run``: the options, the plan and the refusals, without starting SWMM."""

import json
from pathlib import Path

import pytest

from hydraulik import check_command, run_command, run_network
from hydraulik.cli import main
from hydraulik.engines.swmm.network import SwmmSettings, read_network_table, write_inp
from hydraulik.engines.swmm.run import SwmmSummary
from hydraulik.exceptions import (
    InputDataError,
    InvalidInputError,
    MissingDependencyError,
    NotFoundError,
    UnsupportedError,
)
from hydraulik.operations.swmm import DEFAULT_RECESSION_MIN

NETWORK = (
    Path(__file__).resolve().parents[1] / "fixtures" / "swmm" / "network_chain.csv"
)


@pytest.fixture
def inflow(tmp_path: Path) -> Path:
    path = tmp_path / "inflow.csv"
    path.write_text("time_min,discharge_m3s\n0,0\n5,0.05\n10,0\n", encoding="utf-8")
    return path


@pytest.fixture
def inp(tmp_path: Path) -> Path:
    """A SWMM input of the user's own: the chain of the fixture, 15 minutes."""
    path = tmp_path / "sewer.inp"
    path.write_text(
        write_inp(read_network_table(NETWORK), SwmmSettings(900.0)), encoding="utf-8"
    )
    return path


def _reason(caught: pytest.ExceptionInfo[InvalidInputError]) -> object:
    return caught.value.details["reason"]


@pytest.mark.parametrize(
    ("error_percent", "warned"),
    [(12.5, True), (-5.1, True), (5.0, False), (-4.9, False), (0.0, False)],
)
def test_a_continuity_error_above_five_percent_is_a_warning_with_the_value(
    tmp_path: Path,
    inp: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_percent: float,
    warned: bool,
) -> None:
    def fake_run(inp: Path, report: Path, out: Path, **_: object) -> SwmmSummary:
        Path(report).write_text("report", encoding="utf-8")
        return SwmmSummary(900.0, 10.0, 8.0, 0.0, 1.0, error_percent, (), ())

    monkeypatch.setattr("hydraulik.operations.swmm.run_swmm", fake_run)

    document = run_network(inp=inp, output_dir=tmp_path / "o")

    found = [n for n in document.notices if n["code"] == "continuity_error"]
    assert bool(found) is warned
    if warned:
        assert found[0]["level"] == "warning"
        assert f"{error_percent:.2f} %" in found[0]["message"]
        assert "network.rpt" in found[0]["message"]
    assert document.to_dict()["totals"]["continuity_error_percent"] == error_percent


def test_exactly_one_of_the_two_sources_is_required(tmp_path: Path, inp: Path) -> None:
    with pytest.raises(InvalidInputError) as none:
        run_network(output_dir=tmp_path / "o")
    with pytest.raises(InvalidInputError) as both:
        run_network(network=NETWORK, inp=inp, output_dir=tmp_path / "o")

    assert (_reason(none), _reason(both)) == ("missing_option", "exclusive_options")


def test_the_catalog_already_refuses_both_sources_before_the_function_runs(
    tmp_path: Path, inp: Path
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        run_command(
            "swmm run",
            network=str(NETWORK),
            inp=str(inp),
            output_dir=str(tmp_path / "o"),
        )

    assert caught.value.details["group"] == "source"


def test_a_network_table_has_no_inflow_of_its_own(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError) as caught:
        run_network(network=NETWORK, output_dir=tmp_path / "o")

    assert _reason(caught) == "inflow_required"
    assert "--inflow" in (caught.value.hint or "")


def test_an_inflow_and_its_node_go_together(tmp_path: Path, inflow: Path) -> None:
    with pytest.raises(InvalidInputError) as no_node:
        run_network(network=NETWORK, inflow=inflow, output_dir=tmp_path / "o")
    with pytest.raises(InvalidInputError) as no_file:
        run_network(network=NETWORK, inflow_node="J1", output_dir=tmp_path / "o")

    assert no_node.value.details["option"] == "inflow_node"
    assert no_file.value.details["option"] == "inflow"


@pytest.mark.parametrize(
    "option", ["recession_min", "routing_step_s", "surcharge_method"]
)
def test_options_of_the_table_are_refused_with_the_users_own_input(
    tmp_path: Path, inp: Path, option: str
) -> None:
    value: float | str = "SLOT" if option == "surcharge_method" else 1.0

    with pytest.raises(InvalidInputError) as caught:
        run_network(inp=inp, output_dir=tmp_path / "o", **{option: value})  # type: ignore[arg-type]

    assert _reason(caught) == "option_not_applicable"
    assert caught.value.details["option"] == option


def test_an_inflow_node_that_is_not_a_junction_lists_the_allowed_ones(
    tmp_path: Path, inflow: Path
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        run_network(
            network=NETWORK,
            inflow=inflow,
            inflow_node="OUT",  # the outfall takes no inflow
            output_dir=tmp_path / "o",
        )

    assert _reason(caught) == "unknown_node"
    assert caught.value.details["allowed"] == ["J1", "J2", "J3"]


def test_missing_files_are_not_found_and_bad_tables_are_data_errors(
    tmp_path: Path, inflow: Path
) -> None:
    with pytest.raises(NotFoundError):
        run_network(
            network=tmp_path / "none.csv",
            inflow=inflow,
            inflow_node="J1",
            output_dir=tmp_path / "o",
        )
    with pytest.raises(NotFoundError):
        run_network(
            network=NETWORK,
            inflow=tmp_path / "none.csv",
            inflow_node="J1",
            output_dir=tmp_path / "o",
        )
    broken = tmp_path / "broken.csv"
    broken.write_text("name,x_m\nJ1,1\n", encoding="utf-8")
    with pytest.raises(InputDataError) as caught:
        run_network(
            network=broken, inflow=inflow, inflow_node="J1", output_dir=tmp_path / "o"
        )

    assert caught.value.details["reason"] == "invalid_network_table"


def test_an_input_in_us_units_is_refused_while_planning(
    tmp_path: Path, inp: Path
) -> None:
    inp.write_text(inp.read_text().replace("CMS", "CFS", 1), encoding="utf-8")

    with pytest.raises(UnsupportedError) as caught:
        check_command("swmm run", inp=str(inp), output_dir=str(tmp_path / "o"))

    assert caught.value.details["reason"] == "flow_units"


def test_check_plans_the_two_files_and_the_steps_and_writes_nothing(
    tmp_path: Path, inflow: Path
) -> None:
    out = tmp_path / "swmm"

    plan = check_command(
        "swmm run",
        network=str(NETWORK),
        inflow=str(inflow),
        inflow_node="J1",
        output_dir=str(out),
    )

    body = plan.to_dict()
    assert body["schema"] == "hydraulik-plan/1"
    assert [(t["name"], t["action"]) for t in body["targets"]] == [
        ("network.inp", "write"),
        ("network.rpt", "write"),
    ]
    assert body["blockers"] == []
    steps = " ".join(body["steps"])
    duration = 600 + round(DEFAULT_RECESSION_MIN * 60)
    assert f"{duration} s" in steps  # the end of the hydrograph and the recession
    assert "J1" in steps
    assert not out.exists()


def test_check_lists_an_existing_output_as_a_conflict_that_force_turns_into_replace(
    tmp_path: Path, inp: Path
) -> None:
    out = tmp_path / "swmm"
    out.mkdir()
    (out / "network.rpt").write_text("old", encoding="utf-8")

    plain = check_command("swmm run", inp=str(inp), output_dir=str(out)).to_dict()
    forced = check_command(
        "swmm run", inp=str(inp), output_dir=str(out), force=True
    ).to_dict()

    assert plain["conflicts"] == ["output_exists"]
    assert [t["action"] for t in plain["targets"]] == ["write", "conflict"]
    assert [t["action"] for t in forced["targets"]] == ["write", "replace"]


def test_check_names_a_missing_pyswmm_as_a_blocker_and_the_run_refuses(
    tmp_path: Path, inp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hydraulik.operations._support.extra_found", lambda module: False
    )

    plan = check_command("swmm run", inp=str(inp), output_dir=str(tmp_path / "o"))
    with pytest.raises(MissingDependencyError) as caught:
        run_network(inp=inp, output_dir=tmp_path / "o")

    assert plan.to_dict()["blockers"][0]["reason"] == "extra_missing"
    assert "hydraulik[swmm]" in plan.to_dict()["blockers"][0]["hint"]
    assert caught.value.details["reason"] == "extra_missing"
    assert not (tmp_path / "o").exists()


def test_the_cli_prints_the_plan_as_json_and_nothing_is_written(
    tmp_path: Path, inflow: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
            "--output-dir",
            str(tmp_path / "swmm"),
            "--check",
            "--json",
        ]
    )

    envelope = json.loads(capsys.readouterr().out)
    assert code == 0
    assert envelope["command"] == "swmm run" and envelope["check"] is True
    assert envelope["result"]["schema"] == "hydraulik-plan/1"
    assert not (tmp_path / "swmm").exists()


def test_the_cli_reports_a_wrong_combination_as_a_validation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["swmm", "run", "--network", str(NETWORK), "-o", str(tmp_path), "--json"]
    )

    error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert code == 2
    assert error["code"] == "validation_error"
    assert error["details"]["reason"] == "inflow_required"
    assert error["command"] == "swmm run"
