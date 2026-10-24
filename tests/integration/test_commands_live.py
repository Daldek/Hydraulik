"""The commands on the real SFINCS engine: model run, results read, results export."""

import json
import os
from pathlib import Path

import pytest

from hydraulik.cli import main
from hydraulik.engines.sfincs.model import write_model

from ..synthetic import slope_with_outflow

EXE = os.environ.get("HYDRAULIK_SFINCS_EXE")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not EXE, reason="set HYDRAULIK_SFINCS_EXE to run this test"),
]


def _call(capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, object]:
    code = main([*args, "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    envelope: dict[str, object] = json.loads(captured.out)
    return envelope


def test_run_read_and_export_agree_on_the_same_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rasterio = pytest.importorskip("rasterio")
    pytest.importorskip("netCDF4")
    monkeypatch.setenv("HYDRAULIK_SFINCS_EXE", str(EXE))
    model, run = tmp_path / "model", tmp_path / "run"
    model.mkdir()
    write_model(model, slope_with_outflow())

    planned = _call(
        capsys,
        "model",
        "run",
        "--model",
        str(model),
        "--output-dir",
        str(run),
        "--check",
    )
    ran = _call(capsys, "model", "run", "--model", str(model), "--output-dir", str(run))
    read = _call(
        capsys, "results", "read", "--run", str(run), "--thresholds-m", "0.05,0.1"
    )
    exported = _call(
        capsys,
        "results",
        "export",
        "--run",
        str(run),
        "--variable",
        "max_depth",
        "--output",
        str(tmp_path / "hmax.tif"),
    )

    assert planned["result"]["blockers"] == []  # type: ignore[index]
    assert not any(n["code"] == "balance_residual" for n in ran.get("notices", []))  # type: ignore[attr-defined]
    results = ran["result"]["results"]  # type: ignore[index]
    assert results["balance"]["open_boundary"] is True
    assert results["engine"]["status"] == 0
    assert [s["name"] for s in results["stations"]] == ["low"]  # the quoted name
    depth = read["result"]["depth"]  # type: ignore[index]
    assert depth["max_depth_m"] == results["depth"]["max_depth_m"]
    assert [a["threshold_m"] for a in depth["flooded_area_m2"]] == [0.05, 0.1]
    assert (
        depth["flooded_area_m2"][0]["area_m2"] > depth["flooded_area_m2"][1]["area_m2"]
    )
    assert sorted(p.name for p in run.iterdir()) == [
        "sfincs.log",
        "sfincs_his.nc",
        "sfincs_map.nc",
    ]
    with rasterio.open(tmp_path / "hmax.tif") as raster:
        assert float(raster.read(1, masked=True).max()) == pytest.approx(
            results["depth"]["max_depth_m"], abs=1e-4
        )
    assert exported["result"]["format"] == "geotiff"  # type: ignore[index]
