"""From the terrain download to the flood map, on data that a fake Kartograf delivers.

``terrain download`` starts the fake Kartograf program
(``tests/fake_kartograf_program``), which writes a real GeoTIFF, a BDOT10k-like
GeoPackage and a raster of soil groups for a catchment of 100 m x 100 m
(``tests.synthetic.write_catchment``: grass in the west half, the asphalt of a car
park in the east half, soil group C, a 2 % fall to the south). Every later step is the
real command, called through the command line: ``rainfall build``, ``model build`` with
the downloaded land cover and soil groups, then ``model run`` and ``results export``.

The first test needs no engine and runs in the gate. The second runs the model on the
real SFINCS (marker ``live``; set ``HYDRAULIK_SFINCS_EXE``): the infiltration of every
cell must be the SCS equation of the curve number that the land cover and the soil gave
it, which checks the whole chain from the polygons of BDOT10k to the numbers of SFINCS.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("rasterio")
pytest.importorskip("geopandas")

import rasterio  # noqa: E402

from hydraulik.cli import main  # noqa: E402

from ..fake_kartograf import install, use  # noqa: E402
from ..synthetic import read_model_array, write_catchment  # noqa: E402

EXE = os.environ.get("HYDRAULIK_SFINCS_EXE")

X0, Y0 = 362000.0, 504000.0
RAIN_MM = 100.0


@dataclass(frozen=True)
class Chain:
    """What the first four commands made: the model and what they reported."""

    data: Path
    model: Path
    downloaded: dict[str, Any]
    built: dict[str, Any]


def call(
    capsys: pytest.CaptureFixture[str], *args: str, code: int = 0
) -> dict[str, Any]:
    """Run a command through the command line and return its envelope."""
    exit_code = main([*args, "--json"])
    captured = capsys.readouterr()
    assert exit_code == code, captured.err
    envelope: dict[str, Any] = json.loads(captured.out)
    return envelope


def product(files: list[dict[str, Any]], name: str) -> Path:
    """The path of the file that ``terrain download`` put into the folder ``name``."""
    (path,) = [Path(f["path"]) for f in files if Path(f["path"]).parent.name == name]
    return path


def make_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Chain:
    """Download the catchment, make the rain and build the model with the land cover."""
    payloads = write_catchment(tmp_path / "source")
    fake = install(
        tmp_path,
        monkeypatch,
        payloads={
            "elevation download": str(payloads["elevation"]),
            "landcover download": str(payloads["landcover"]),
            "soil hsg": str(payloads["soil"]),
        },
    )
    use(monkeypatch, fake)
    data, model = tmp_path / "data", tmp_path / "model"
    area = ["--bbox", "362000,504000,362100,504100", "--crs", "EPSG:2180"]

    planned = call(
        capsys, "terrain", "download", *area, "--output-dir", str(data), "--check"
    )
    downloaded = call(capsys, "terrain", "download", *area, "--output-dir", str(data))
    rain = tmp_path / "rain.csv"
    call(
        capsys,
        "rainfall",
        "build",
        "--hietogram-type",
        "block",
        "--total-mm",
        str(RAIN_MM),
        "--duration-min",
        "30",
        "--timestep-min",
        "5",
        "--output",
        str(rain),
    )
    stations = tmp_path / "stations.csv"
    stations.write_text(
        f"name,x_m,y_m\nsouth,{X0 + 52.5},{Y0 + 2.5}\nnorth,{X0 + 52.5},{Y0 + 97.5}\n",
        encoding="utf-8",
    )
    files = downloaded["result"]["files"]
    built = call(
        capsys,
        "model",
        "build",
        *("--dem", str(product(files, "elevation"))),
        *("--landcover", str(product(files, "landcover"))),
        *("--hsg", str(product(files, "soil"))),
        *("--dx-m", "5", "--rain", str(rain)),
        *("--observation-points", str(stations)),
        *("--recession-min", "120", "--output-dir", str(model)),
    )
    assert planned["result"]["conflicts"] == []
    return Chain(data, model, downloaded, built)


def test_the_downloaded_files_build_a_model_whose_cells_follow_the_land_cover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    chain = make_model(tmp_path, monkeypatch, capsys)

    assert chain.downloaded["status"] == "ok"
    assert sorted(p.name for p in chain.data.iterdir()) == [
        "elevation",
        "landcover",
        "soil",
    ]
    result = chain.built["result"]
    assert chain.built["status"] == "ok"
    assert (result["grid"]["rows"], result["grid"]["columns"]) == (20, 20)
    assert (result["roughness"]["source"], result["infiltration"]["source"]) == (
        "landcover",
        "landcover",
    )
    assert result["infiltration"]["hsg"]["cells"] == {"A": 0, "B": 0, "C": 400, "D": 0}
    areas = {c["class"]: c["area_m2"] for c in result["landcover"]["classes"]}
    assert areas == pytest.approx({"grass": 5000.0, "road_paved": 5000.0})
    codes = {n["code"] for n in chain.built["notices"]}
    assert not codes & {"cn_gaps", "landcover_unclassified", "landcover_unmapped"}
    n = read_model_array(chain.model, "sfincs.man", "float32")
    s = read_model_array(chain.model, "sfincs.scs", "float32")
    z = read_model_array(chain.model, "sfincs.dep", "float32")
    # row 0 is the south, column 0 the west: grass in columns 0 to 9, asphalt after
    assert n[:, :10] == pytest.approx(0.15) and n[:, 10:] == pytest.approx(0.011)
    assert s[:, :10] == pytest.approx(1000.0 / 79.0 - 10.0, abs=1e-4)  # grass, group C
    assert s[:, 10:] == pytest.approx(1000.0 / 98.0 - 10.0, abs=1e-4)  # asphalt
    assert z[0, 0] == pytest.approx(0.02 * 2.5, abs=1e-4)  # the south edge is lowest
    assert z[19, 0] == pytest.approx(0.02 * 97.5, abs=1e-4)
    assert {Path(f["path"]).name for f in result["files"]} >= {
        "sfincs.inp",
        "manning.tif",
        "curve_number.tif",
    }
    with rasterio.open(chain.model / "curve_number.tif") as curve:
        values = curve.read(1)  # north-up
        assert values[:, :10] == pytest.approx(79.0)
        assert values[:, 10:] == pytest.approx(98.0)


@pytest.mark.live
@pytest.mark.skipif(not EXE, reason="set HYDRAULIK_SFINCS_EXE to run this test")
def test_the_model_runs_on_sfincs_and_every_half_infiltrates_by_the_scs_equation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("netCDF4")
    monkeypatch.setenv("HYDRAULIK_SFINCS_EXE", str(EXE))
    chain = make_model(tmp_path, monkeypatch, capsys)
    run = tmp_path / "run"

    ran = call(
        capsys, "model", "run", "--model", str(chain.model), "--output-dir", str(run)
    )
    call(
        capsys,
        *("results", "export", "--run", str(run), "--variable", "infiltration"),
        *("--output", str(tmp_path / "infiltration.tif")),
    )

    results = ran["result"]["results"]
    balance = results["balance"]
    assert balance["flags"] == [] and abs(balance["residual_percent"]) < 0.1
    assert balance["rain_m3"] == pytest.approx(
        RAIN_MM / 1000.0 * 100.0 * 100.0, rel=0.01
    )
    by_name = {s["name"]: s for s in results["stations"]}
    # water under huthresh (5 cm) stays where it fell; the rest runs to the south edge
    assert by_name["south"]["max_depth_m"] > 0.2
    assert by_name["north"]["max_depth_m"] < 0.06
    with rasterio.open(tmp_path / "infiltration.tif") as raster:
        infiltrated_mm = 1000.0 * raster.read(1, masked=True).filled(np.nan)
    west, east = infiltrated_mm[:, :10].mean(), infiltrated_mm[:, 10:].mean()
    for curve_number, found in ((79.0, west), (98.0, east)):
        storage = 25400.0 / curve_number - 254.0  # S [mm]
        runoff = (RAIN_MM - 0.2 * storage) ** 2 / (RAIN_MM + 0.8 * storage)
        assert found == pytest.approx(RAIN_MM - runoff, abs=0.1)
    assert west > 8.0 * east  # the car park sheds the rain that the grass takes
    assert balance["infiltration_m3"] == pytest.approx(
        (west + east) / 2.0 / 1000.0 * 100.0 * 100.0, rel=0.01
    )
