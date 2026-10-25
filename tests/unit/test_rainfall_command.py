"""``rainfall build``: the routes to a rain table, the refusals, plan and the CLI."""

import json
from pathlib import Path
from typing import Any

import pytest

from hydraulik import build_rainfall, check_command, run_command
from hydraulik.cli import main
from hydraulik.data.tables import read_rain_table
from hydraulik.exceptions import (
    ConflictError,
    InvalidInputError,
    MissingDependencyError,
    NoDataError,
    SourceUnavailableError,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "rain"


def _reason(caught: pytest.ExceptionInfo[InvalidInputError]) -> object:
    return caught.value.details["reason"]


@pytest.fixture
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Replace the network call of IMGWTools; the list records every call."""
    import imgwtools
    from imgwtools import PMaXTPData, PMaXTPResult

    calls: list[tuple[Any, ...]] = []

    def fake(latitude: float, longitude: float, *, method: str = "POT") -> PMaXTPResult:
        calls.append((latitude, longitude, method))
        return PMaXTPResult(
            method=method,
            latitude=latitude,
            longitude=longitude,
            data=PMaXTPData(ks={"60": {"10": 31.5, "1": 50.0}}),
        )

    monkeypatch.setattr(imgwtools, "fetch_pmaxtp", fake)
    return calls


def test_a_given_depth_makes_a_rain_table_that_reads_back_with_the_same_depth(
    tmp_path: Path,
) -> None:
    out = tmp_path / "rain.csv"

    document = build_rainfall(
        hietogram_type="euler_ii", total_mm=40.0, duration_min=120.0, output=out
    )

    body = document.to_dict()
    table = read_rain_table(out)
    assert body["schema"] == "hydraulik-rain/1"
    assert (body["source"], body["hietogram_type"]) == ("design", "euler_ii")
    assert body["parameters"] == {}
    assert body["depth"] == {"source": "given", "value_mm": 40.0}
    assert body["timestep_min"] == 5.0 and body["n_steps"] == 24
    assert body["total_mm"] == pytest.approx(40.0)
    assert table.total_mm == pytest.approx(40.0, abs=1e-3)  # 4 decimals per step
    assert body["duration_min"] == 120.0 == table.duration_min
    assert body["peak_intensity_mm_h"] == pytest.approx(table.peak_intensity_mm_h)
    assert [f["status"] for f in body["files"]] == ["written"]
    assert body["files"][0]["path"] == str(out.resolve())
    assert document.notices == []
    assert out.read_text(encoding="utf-8").startswith("time_min,depth_mm\n5,")


def test_the_pmaxtp_document_gives_the_depth_and_the_attribution_comes_with_it(
    tmp_path: Path,
) -> None:
    document = build_rainfall(
        hietogram_type="beta",
        pmaxtp=FIXTURES / "pmaxtp_fetch.json",
        probability_percent=10,
        duration_min=60.0,
        timestep_min=10.0,
        alpha=2.0,
        beta=5.0,
        output=tmp_path / "rain.csv",
    )

    body = document.to_dict()
    assert body["total_mm"] == pytest.approx(38.8)
    assert body["parameters"] == {"alpha": 2.0, "beta": 5.0}
    assert body["depth"]["source"] == "pmaxtp" and body["depth"]["via"] == "document"
    assert body["depth"]["value_mm"] == 38.8
    assert (body["depth"]["duration_min"], body["depth"]["probability_percent"]) == (
        60,
        10,
    )
    assert body["depth"]["method"] == "POT" and body["depth"]["error_mm"] == 3.1
    assert body["depth"]["path"].endswith("pmaxtp_fetch.json")
    [attribution] = document.notices
    assert (attribution["level"], attribution["code"]) == ("info", "pmaxtp_attribution")
    assert "IMGW-PIB" in attribution["message"]


def test_a_point_is_fetched_once_through_imgwtools_and_not_while_planning(
    tmp_path: Path, fetched: list[tuple[Any, ...]]
) -> None:
    options: dict[str, Any] = {
        "hietogram_type": "block",
        "latitude": 52.1,
        "longitude": 21.0,
        "probability_percent": 10,
        "duration_min": 60.0,
        "output": tmp_path / "rain.csv",
    }

    plan = check_command(
        "rainfall build", **{**options, "output": str(options["output"])}
    )
    assert fetched == [] and not (tmp_path / "rain.csv").exists()
    document = build_rainfall(**options)

    body = document.to_dict()
    assert fetched == [(52.1, 21.0, "POT")]
    assert body["total_mm"] == pytest.approx(31.5)
    assert body["depth"]["via"] == "library" and "path" not in body["depth"]
    assert (body["depth"]["latitude"], body["depth"]["longitude"]) == (52.1, 21.0)
    assert any("network" in step for step in plan.to_dict()["steps"])
    assert [n["code"] for n in document.notices] == ["pmaxtp_attribution"]


def test_the_method_of_a_point_is_passed_on_and_a_missing_pair_is_no_data(
    tmp_path: Path, fetched: list[tuple[Any, ...]]
) -> None:
    build_rainfall(
        hietogram_type="block",
        latitude=52.1,
        longitude=21.0,
        method="AMP",
        probability_percent=1,
        duration_min=60.0,
        output=tmp_path / "rain.csv",
    )
    with pytest.raises(NoDataError):
        build_rainfall(
            hietogram_type="block",
            latitude=52.1,
            longitude=21.0,
            probability_percent=5,  # allowed for PMAXTP, absent from the fake answer
            duration_min=60.0,
            output=tmp_path / "other.csv",
            force=True,
        )

    assert fetched[0] == (52.1, 21.0, "AMP")
    assert not (tmp_path / "other.csv").exists()


def test_an_unreachable_imgw_is_source_unavailable_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import imgwtools

    def down(latitude: float, longitude: float, *, method: str = "POT") -> None:
        raise imgwtools.IMGWConnectionError("timed out")

    monkeypatch.setattr(imgwtools, "fetch_pmaxtp", down)

    with pytest.raises(SourceUnavailableError) as caught:
        build_rainfall(
            hietogram_type="block",
            latitude=52.1,
            longitude=21.0,
            probability_percent=10,
            duration_min=60.0,
            output=tmp_path / "out" / "rain.csv",
        )

    assert "--total-mm" in (caught.value.hint or "")
    assert not (tmp_path / "out").exists()


def test_a_hydrolog_document_is_converted_as_it_is(tmp_path: Path) -> None:
    document = build_rainfall(
        hietogram=FIXTURES / "hietogram_euler_ii.json", output=tmp_path / "rain.csv"
    )

    body = document.to_dict()
    table = read_rain_table(tmp_path / "rain.csv")
    assert (body["source"], body["hietogram_type"]) == ("hietogram", "euler_ii")
    assert body["parameters"] == {"peak_position": 0.33}
    assert body["depth"] is None
    assert (body["timestep_min"], body["n_steps"], body["duration_min"]) == (
        10.0,
        6,
        60,
    )
    assert body["total_mm"] == pytest.approx(40.0) == pytest.approx(table.total_mm)
    assert document.notices == []


@pytest.mark.parametrize(
    "extra",
    [
        {"hietogram_type": "block"},
        {"total_mm": 30.0},
        {"duration_min": 60.0},
        {"timestep_min": 5.0},
        {"probability_percent": 10},
        {"alpha": 2.0},
    ],
)
def test_nothing_of_a_design_may_be_given_with_a_document(
    tmp_path: Path, extra: dict[str, Any]
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        build_rainfall(
            hietogram=FIXTURES / "hietogram_euler_ii.json",
            output=tmp_path / "rain.csv",
            **extra,
        )

    assert _reason(caught) == "option_not_applicable"
    assert caught.value.details["option"] == next(iter(extra))


@pytest.mark.parametrize(
    ("options", "reason", "option"),
    [
        ({}, "missing_option", "hietogram_type"),
        (
            {"hietogram_type": "block", "duration_min": 60.0},
            "missing_option",
            "total_mm",
        ),
        (
            {"hietogram_type": "block", "total_mm": 30.0},
            "missing_option",
            "duration_min",
        ),
        (
            {
                "hietogram_type": "block",
                "total_mm": 30.0,
                "pmaxtp": FIXTURES / "pmaxtp_fetch.json",
                "duration_min": 60.0,
            },
            "exclusive_options",
            "pmaxtp",
        ),
        (
            {
                "hietogram_type": "block",
                "latitude": 52.0,
                "probability_percent": 10,
                "duration_min": 60.0,
            },
            "missing_option",
            "longitude",
        ),
        (
            {
                "hietogram_type": "block",
                "pmaxtp": FIXTURES / "pmaxtp_fetch.json",
                "duration_min": 60.0,
            },
            "missing_option",
            "probability_percent",
        ),
        (
            {
                "hietogram_type": "block",
                "total_mm": 30.0,
                "probability_percent": 10,
                "duration_min": 60.0,
            },
            "option_not_applicable",
            "probability_percent",
        ),
        (
            {
                "hietogram_type": "block",
                "pmaxtp": FIXTURES / "pmaxtp_fetch.json",
                "method": "POT",
                "probability_percent": 10,
                "duration_min": 60.0,
            },
            "option_not_applicable",
            "method",
        ),
        (
            {
                "hietogram_type": "block",
                "latitude": 52.0,
                "longitude": 21.0,
                "method": "MEAN",
                "probability_percent": 10,
                "duration_min": 60.0,
            },
            "not_allowed",
            "method",
        ),
        (
            {
                "hietogram_type": "block",
                "latitude": 52.0,
                "longitude": 21.0,
                "probability_percent": 10,
                "duration_min": 75.0,
            },
            "not_allowed",
            "duration_min",
        ),
        (
            {
                "hietogram_type": "block",
                "latitude": 52.0,
                "longitude": 21.0,
                "probability_percent": 3,
                "duration_min": 60.0,
            },
            "not_allowed",
            "probability_percent",
        ),
        (
            {"hietogram_type": "gauss", "total_mm": 30.0, "duration_min": 60.0},
            "not_allowed",
            "hietogram_type",
        ),
    ],
)
def test_a_wrong_combination_of_options_is_refused_with_the_option_named(
    tmp_path: Path, options: dict[str, Any], reason: str, option: str
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        build_rainfall(output=tmp_path / "rain.csv", **options)

    assert _reason(caught) == reason
    assert caught.value.details["option"] == option
    assert not (tmp_path / "rain.csv").exists()


def test_the_catalog_refuses_two_shapes_or_two_depths_before_the_function_runs(
    tmp_path: Path,
) -> None:
    with pytest.raises(InvalidInputError) as shapes:
        run_command(
            "rainfall build",
            hietogram_type="block",
            hietogram=str(FIXTURES / "hietogram_euler_ii.json"),
            output=str(tmp_path / "r.csv"),
        )
    with pytest.raises(InvalidInputError) as depths:
        run_command(
            "rainfall build",
            hietogram_type="block",
            total_mm=30.0,
            latitude=52.0,
            duration_min=60.0,
            output=str(tmp_path / "r.csv"),
        )

    assert (shapes.value.details["group"], depths.value.details["group"]) == (
        "shape",
        "depth",
    )


def test_a_duration_that_is_not_a_multiple_of_the_step_is_a_warning(
    tmp_path: Path,
) -> None:
    document = build_rainfall(
        hietogram_type="block",
        total_mm=30.0,
        duration_min=62.0,
        output=tmp_path / "rain.csv",
    )

    [warning] = document.notices
    assert (warning["level"], warning["code"]) == ("warning", "duration_truncated")
    assert "60 min" in warning["message"] and "30.0 mm" in warning["message"]
    assert document.to_dict()["duration_min"] == 60.0


def test_check_plans_the_file_and_the_steps_and_reads_the_document_but_not_the_net(
    tmp_path: Path,
) -> None:
    plan = check_command(
        "rainfall build",
        hietogram_type="euler_ii",
        pmaxtp=str(FIXTURES / "pmaxtp_fetch.json"),
        probability_percent=10,
        duration_min=60.0,
        output=str(tmp_path / "rain.csv"),
    )

    body = plan.to_dict()
    assert [(t["name"], t["action"]) for t in body["targets"]] == [
        ("rain.csv", "write")
    ]
    assert body["blockers"] == []
    assert "38.8 mm" in " ".join(body["steps"]) and "euler_ii" in " ".join(
        body["steps"]
    )
    assert not (tmp_path / "rain.csv").exists()


def test_check_of_a_missing_document_or_depth_is_an_error_not_a_plan(
    tmp_path: Path,
) -> None:
    with pytest.raises(NoDataError):
        check_command(
            "rainfall build",
            hietogram_type="block",
            pmaxtp=str(FIXTURES / "pmaxtp_fetch.json"),
            probability_percent=10,
            duration_min=75.0,
            output=str(tmp_path / "rain.csv"),
        )


def test_missing_packages_are_blockers_of_the_plan_and_refusals_of_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hydraulik.operations._support.extra_found", lambda module: False
    )
    options: dict[str, Any] = {
        "hietogram_type": "block",
        "latitude": 52.0,
        "longitude": 21.0,
        "probability_percent": 10,
        "duration_min": 60.0,
    }

    plan = check_command("rainfall build", output=str(tmp_path / "r.csv"), **options)
    with pytest.raises(MissingDependencyError) as caught:
        build_rainfall(output=tmp_path / "r.csv", **options)

    blockers = plan.to_dict()["blockers"]
    assert [b["reason"] for b in blockers] == ["extra_missing"] * 2
    assert all("hydraulik[rainfall]" in b["hint"] for b in blockers)
    assert caught.value.details["extras"] == ["rainfall"]
    assert caught.value.details["modules"] == ["hydrolog", "imgwtools"]


def test_the_document_route_needs_neither_hydrolog_nor_imgwtools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hydraulik.operations._support.extra_found", lambda module: False
    )

    document = build_rainfall(
        hietogram=FIXTURES / "hietogram_euler_ii.json", output=tmp_path / "rain.csv"
    )

    assert document.to_dict()["total_mm"] == pytest.approx(40.0)


def test_an_existing_table_is_a_conflict_until_force_replaces_it(
    tmp_path: Path,
) -> None:
    options: dict[str, Any] = {
        "hietogram_type": "block",
        "total_mm": 30.0,
        "duration_min": 60.0,
        "output": tmp_path / "rain.csv",
    }
    build_rainfall(**options)

    with pytest.raises(ConflictError) as caught:
        build_rainfall(**options)
    plan = check_command(
        "rainfall build", **{**options, "output": str(options["output"])}
    )
    again = build_rainfall(force=True, **options)

    assert caught.value.details["reason"] == "output_exists"
    assert plan.to_dict()["conflicts"] == ["output_exists"]
    assert [f["status"] for f in again.to_dict()["files"]] == ["replaced"]


def test_the_cli_writes_the_table_and_prints_the_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "rainfall",
            "build",
            "--hietogram-type",
            "triangular",
            "--peak-position",
            "0.4",
            "--total-mm",
            "25",
            "--duration-min",
            "60",
            "--timestep-min",
            "10",
            "--output",
            str(tmp_path / "rain.csv"),
            "--json",
        ]
    )

    envelope = json.loads(capsys.readouterr().out)
    assert code == 0 and envelope["command"] == "rainfall build"
    assert envelope["result"]["parameters"] == {"peak_position": 0.4}
    assert read_rain_table(tmp_path / "rain.csv").step_min == 10.0


def test_the_cli_reports_a_wrong_combination_as_a_validation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["rainfall", "build", "--total-mm", "25", "--output", str(tmp_path / "r.csv")]
    )

    stderr = capsys.readouterr().err.strip().splitlines()
    error = json.loads(stderr[-1])
    assert code == 2
    assert error["details"]["reason"] == "missing_option"
    assert error["details"]["option"] == "hietogram_type"
    assert "Brakuje wymaganej opcji" in stderr[0]  # the human line is Polish by default
