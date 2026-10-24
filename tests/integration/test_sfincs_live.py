"""A model written by Hydraulik on the real SFINCS engine (marker ``live``).

Set ``HYDRAULIK_SFINCS_EXE`` to a SFINCS executable and run ``pytest -m live``. The
variable is read when the module is imported, because the test fixtures clear the
environment of every test.
"""

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from hydraulik.engines.sfincs.model import (
    ModelInputs,
    RegularGrid,
    precip_breakpoints,
    write_model,
)

EXE = os.environ.get("HYDRAULIK_SFINCS_EXE")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not EXE, reason="set HYDRAULIK_SFINCS_EXE to run this test"),
]


def test_closed_basin_infiltrates_by_the_scs_equation(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    grid = RegularGrid(0.0, 0.0, 10.0, 10, 10)
    inputs = ModelInputs(
        grid=grid,
        elevation_m=np.zeros(grid.shape),
        active=np.ones(grid.shape, dtype=bool),
        precip=precip_breakpoints([5.0] * 6, 600.0, 7200.0),
        tstop_s=7200.0,
        manning=np.full(grid.shape, 0.03),
        curve_number=np.full(grid.shape, 80.0),
        observation_points=((55.0, 55.0, "centre"),),
        dtmax_s=10.0,
        dtout_s=7200.0,
        dthisout_s=600.0,
    )
    write_model(tmp_path, inputs)

    done = subprocess.run(
        [str(EXE)], cwd=tmp_path, capture_output=True, text=True, timeout=300
    )

    assert done.returncode == 0, done.stdout[-800:]
    with netcdf4.Dataset(tmp_path / "sfincs_map.nc") as map_file:
        rain_mm = float(np.ma.mean(map_file["cumprcp"][-1])) * 1000.0
        infiltrated_mm = float(np.ma.mean(map_file["cuminf"][-1])) * 1000.0
    with netcdf4.Dataset(tmp_path / "sfincs_his.nc") as his_file:
        stored_mm = float(his_file["point_zs"][-1, 0]) * 1000.0
    storage_mm, abstraction = 1000.0 / 80.0 * 25.4 - 254.0, 0.2  # S in mm
    runoff_mm = (rain_mm - abstraction * storage_mm) ** 2 / (
        rain_mm + (1.0 - abstraction) * storage_mm
    )
    assert rain_mm == pytest.approx(30.0, abs=0.05)
    assert infiltrated_mm == pytest.approx(rain_mm - runoff_mm, abs=0.05)
    assert stored_mm == pytest.approx(runoff_mm, abs=0.05)
