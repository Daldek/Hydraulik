"""``results read`` and ``results export`` on synthetic results, library and CLI."""

import json
from pathlib import Path

import numpy as np
import pytest

from hydraulik import check_command, export_results, read_results
from hydraulik.cli import main
from hydraulik.exceptions import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
)

from ..synthetic import write_his, write_map


@pytest.fixture
def run(tmp_path: Path) -> Path:
    """A run directory: 4 x 5 cells of 10 m, 40 cm of water at one cell."""
    folder = tmp_path / "run"
    folder.mkdir()
    depth = np.zeros((4, 5))
    depth[0, 1] = 0.40
    depth[2, 3] = 0.12
    write_map(folder / "sfincs_map.nc", depth=depth, rain_m=0.03, infiltration_m=0.03)
    write_his(folder / "sfincs_his.nc", names=("outlet",), x=(1015.0,), y=(2005.0,))
    return folder


def test_reading_a_run_gives_the_grid_the_maxima_the_balance_and_the_stations(
    run: Path,
) -> None:
    body = read_results(run=run, thresholds_m=[0.1, 0.3]).to_dict()

    assert body["schema"] == "hydraulik-results/1"
    assert body["grid"]["epsg"] == 2180 and body["grid"]["active_cells"] == 20
    assert body["depth"]["max_depth_m"] == pytest.approx(0.40)
    assert (body["depth"]["max_depth_x_m"], body["depth"]["max_depth_y_m"]) == (
        1015.0,
        2005.0,
    )
    assert body["depth"]["flooded_area_m2"] == [
        {"threshold_m": 0.1, "area_m2": 200.0},
        {"threshold_m": 0.3, "area_m2": 100.0},
    ]
    assert body["balance"]["flags"] == ["balance_residual"]  # 0.4 m + 0.12 m stored
    assert [s["name"] for s in body["stations"]] == ["outlet"]


def test_the_map_file_itself_names_a_run_too_and_the_station_file_is_optional(
    run: Path,
) -> None:
    (run / "sfincs_his.nc").unlink()

    body = read_results(run=run / "sfincs_map.nc").to_dict()

    assert body["stations"] == []
    assert body["depth"]["flooded_area_m2"][0]["threshold_m"] == 0.1  # the default


def test_a_threshold_under_huthresh_is_a_validation_error_naming_the_reason(
    run: Path,
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        read_results(run=run, thresholds_m=[0.01])

    assert caught.value.details["reason"] == "below_huthresh"


def test_the_expected_rain_is_compared_with_the_map(run: Path) -> None:
    document = read_results(run=run, expected_rain_mm=60.0)

    assert "rain_mismatch" in document.to_dict()["balance"]["flags"]
    assert "rain_mismatch" in [n["code"] for n in document.notices]


def test_a_directory_without_a_map_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError) as caught:
        read_results(run=tmp_path)

    assert caught.value.details["reason"] == "results_missing"


def test_a_map_is_exported_as_a_geotiff_and_a_second_export_needs_force(
    run: Path, tmp_path: Path
) -> None:
    rasterio = pytest.importorskip("rasterio")
    target = tmp_path / "out" / "hmax.tif"

    document = export_results(run=run, variable="max_depth", output=target)

    body = document.to_dict()
    assert (body["format"], body["variable"]) == ("geotiff", "max_depth")
    assert [f["status"] for f in body["files"]] == ["written"]
    with rasterio.open(target) as raster:
        assert raster.crs.to_epsg() == 2180
        assert float(raster.read(1, masked=True).max()) == pytest.approx(0.40)
    with pytest.raises(ConflictError):
        export_results(run=run, variable="max_depth", output=target)
    again = export_results(run=run, variable="max_depth", output=target, force=True)
    assert again.to_dict()["files"][0]["status"] == "replaced"
    assert sorted(p.name for p in target.parent.iterdir()) == ["hmax.tif"]


def test_the_stations_are_exported_as_a_table(run: Path, tmp_path: Path) -> None:
    target = tmp_path / "stations.csv"

    body = export_results(run=run, variable="stations", output=target).to_dict()

    assert body["format"] == "csv"
    assert target.read_text().splitlines()[0] == "time_s,station,level_m,depth_m"


def test_stations_of_a_run_without_a_station_file_are_not_found(
    run: Path, tmp_path: Path
) -> None:
    (run / "sfincs_his.nc").unlink()

    with pytest.raises(NotFoundError):
        export_results(run=run, variable="stations", output=tmp_path / "s.csv")


def test_an_unknown_variable_and_a_directory_as_output_are_refused(
    run: Path, tmp_path: Path
) -> None:
    with pytest.raises(InvalidInputError) as unknown:
        export_results(run=run, variable="elevation", output=tmp_path / "e.tif")
    with pytest.raises(InvalidInputError) as directory:
        export_results(run=run, variable="max_depth", output=tmp_path)

    assert unknown.value.details["allowed"][-1] == "stations"
    assert directory.value.details["reason"] == "not_a_file"


def test_an_output_inside_a_store_of_another_tool_is_a_conflict(
    run: Path, tmp_path: Path
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "kartograf-store.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ConflictError) as caught:
        export_results(run=run, variable="stations", output=store / "s.csv")

    assert caught.value.details["reason"] == "output_in_store"
    assert not (store / "s.csv").exists()


def test_check_plans_an_export_without_writing(run: Path, tmp_path: Path) -> None:
    target = tmp_path / "plan" / "hmax.tif"

    plan = check_command(
        "results export", run=str(run), variable="max_depth", output=str(target)
    )

    body = plan.to_dict()
    assert [(t["name"], t["action"]) for t in body["targets"]] == [
        ("hmax.tif", "write")
    ]
    assert not target.parent.exists()


def test_the_cli_prints_the_envelope_of_a_read_and_of_an_export_plan(
    run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["results", "read", "--run", str(run), "--thresholds-m", "0.1", "--json"])
        == 0
    )
    read = json.loads(capsys.readouterr().out)
    target = tmp_path / "hmax.tif"
    code = main(
        [
            "results",
            "export",
            "--run",
            str(run),
            "--variable",
            "max_depth",
            "--output",
            str(target),
            "--check",
            "--json",
        ]
    )
    plan = json.loads(capsys.readouterr().out)

    assert (
        read["command"],
        read["result"]["depth"]["flooded_area_m2"][0]["area_m2"],
    ) == (
        "results read",
        200.0,
    )
    assert any(n["code"] == "balance_residual" for n in read["notices"])
    assert code == 0 and plan["check"] is True
    assert plan["result"]["schema"] == "hydraulik-plan/1" and not target.exists()
