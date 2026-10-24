"""A model built from rasters runs on the real SFINCS (marker ``live``).

Set ``HYDRAULIK_SFINCS_EXE`` to a SFINCS executable and run ``pytest -m live``. The
terrain falls to the south: if the arrays were written in the wrong order the water
would collect at the wrong edge, so this test checks the orientation of the whole chain
(raster, grid, files, SFINCS, results) on the real engine.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from hydraulik import ModelDocument, build_model, run_model
from hydraulik.data.tables import render_rain_table

from ..synthetic import write_raster

EXE = os.environ.get("HYDRAULIK_SFINCS_EXE")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not EXE, reason="set HYDRAULIK_SFINCS_EXE to run this test"),
]

X0, Y0 = 362000.0, 504000.0


def test_water_collects_at_the_low_edge_and_the_balance_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("rasterio")
    pytest.importorskip("netCDF4")
    monkeypatch.setenv("HYDRAULIK_SFINCS_EXE", str(EXE))
    ys = Y0 + 100.0 - (np.arange(100) + 0.5)  # row 0 of the raster is the north edge
    terrain = np.tile((0.02 * (ys - Y0))[:, None], (1, 100))  # 2 % down to the south
    dem = write_raster(tmp_path / "dem.tif", terrain, west=X0, north=Y0 + 100.0)
    cn = write_raster(
        tmp_path / "cn.tif", np.full((100, 100), 95.0), west=X0, north=Y0 + 100.0
    )
    rain = tmp_path / "rain.csv"
    rain.write_text(render_rain_table(5.0, [100 / 6] * 6), encoding="utf-8")  # 100 mm
    stations = tmp_path / "stations.csv"
    stations.write_text(
        f"name,x_m,y_m\nsouth,{X0 + 52.5},{Y0 + 2.5}\nnorth,{X0 + 52.5},{Y0 + 97.5}\n",
        encoding="utf-8",
    )

    built = build_model(
        dem=[dem],
        dx_m=5.0,
        rain=rain,
        curve_number_raster=cn,
        observation_points=stations,
        recession_min=120.0,
        output_dir=tmp_path / "model",
    )
    run = run_model(model=tmp_path / "model", output_dir=tmp_path / "run")

    results = run.to_dict()["results"]
    balance = results["balance"]
    assert isinstance(built, ModelDocument) and built.grid["active_cells"] == 400
    assert balance["flags"] == []
    assert abs(balance["residual_percent"]) < 0.1  # a closed model closes
    assert balance["rain_m3"] == pytest.approx(100e-3 * 100 * 100, rel=0.01)
    assert 0.0 < balance["infiltration_m3"] < balance["rain_m3"]
    by_name = {s["name"]: s for s in results["stations"]}
    # water under huthresh (5 cm) does not move: the heavy rain runs off to the south
    assert by_name["south"]["max_depth_m"] > 0.2
    assert by_name["north"]["max_depth_m"] < 0.06
