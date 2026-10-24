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

from hydraulik.engines.detect import SfincsInstall
from hydraulik.engines.sfincs.model import (
    ModelInputs,
    RegularGrid,
    precip_breakpoints,
    write_model,
)
from hydraulik.engines.sfincs.results import (
    depth_statistics,
    read_map,
    read_stations,
    surface_balance,
)
from hydraulik.engines.sfincs.run import run_sfincs
from hydraulik.exceptions import EngineError

EXE = os.environ.get("HYDRAULIK_SFINCS_EXE")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not EXE, reason="set HYDRAULIK_SFINCS_EXE to run this test"),
]


def _closed_basin() -> ModelInputs:
    """A flat 10 x 10 basin of 10 m cells, 30 mm of rain, CN 80, no outflow."""
    grid = RegularGrid(0.0, 0.0, 10.0, 10, 10)
    return ModelInputs(
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


def test_closed_basin_infiltrates_by_the_scs_equation(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    write_model(tmp_path, _closed_basin())

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


def test_the_runner_and_the_reader_close_the_balance_of_a_closed_basin(
    tmp_path: Path,
) -> None:
    pytest.importorskip("netCDF4")
    inputs = _closed_basin()
    write_model(tmp_path, inputs)
    seen: list[int] = []

    info = run_sfincs(
        SfincsInstall("exe", (str(EXE),)), tmp_path, timeout_s=300, progress=seen.append
    )

    run = read_map(tmp_path / "sfincs_map.nc")
    balance = surface_balance(run, expected_rain_mm=inputs.precip.depth_mm())
    stations = read_stations(tmp_path / "sfincs_his.nc")
    assert info.returncode == 0 and seen[-1] == 100
    assert run.status == 0 and run.grid.epsg == 2180
    assert run.huthresh_m == pytest.approx(0.05)
    assert balance.flags == ()
    assert abs(balance.residual_percent) < 0.05
    assert balance.rain_m3 == pytest.approx(30.0e-3 * 100 * 100.0, rel=0.002)
    # the basin keeps its runoff everywhere, under huthresh, so no depth is in hmax
    assert depth_statistics(run).max_depth_m == 0.0
    assert balance.stored_m3 == pytest.approx(
        stations[0].depth_m[-1] * 100 * 100.0, rel=0.001
    )


def test_a_model_that_sfincs_rejects_is_an_engine_error_with_its_message(
    tmp_path: Path,
) -> None:
    write_model(tmp_path, _closed_basin())
    (tmp_path / "sfincs.precip").unlink()

    with pytest.raises(EngineError) as caught:
        run_sfincs(SfincsInstall("exe", (str(EXE),)), tmp_path, timeout_s=300)

    assert "sfincs.precip" in str(caught.value)
    assert caught.value.details["reason"] == "engine_failed"
    assert caught.value.details["returncode"] != 0


def test_a_slope_with_outflow_cells_gives_its_water_away_as_the_residual(
    tmp_path: Path,
) -> None:
    pytest.importorskip("netCDF4")
    grid = RegularGrid(0.0, 0.0, 10.0, 10, 10)
    rows = np.arange(10)[:, None] * np.ones((1, 10))
    outflow = np.zeros(grid.shape, dtype=bool)
    outflow[0, 4:6] = True  # two cells at the low (south) edge
    inputs = ModelInputs(
        grid=grid,
        elevation_m=0.5 + 0.04 * rows,  # 0.4 % slope towards row 0
        active=np.ones(grid.shape, dtype=bool),
        precip=precip_breakpoints([30.0, 30.0], 900.0, 7200.0),
        tstop_s=7200.0,
        outflow=outflow,
        manning=0.04,
        dtmax_s=10.0,
        dtout_s=7200.0,
    )
    write_model(tmp_path, inputs)

    run_sfincs(SfincsInstall("exe", (str(EXE),)), tmp_path, timeout_s=300)

    run = read_map(tmp_path / "sfincs_map.nc")
    balance = surface_balance(run, expected_rain_mm=inputs.precip.depth_mm())
    statistics = depth_statistics(run, (0.05, 0.1))
    assert balance.open_boundary and balance.flags == ()
    assert 0.0 < balance.residual_percent < 50.0  # the water that left
    assert balance.infiltration_m3 == 0.0
    assert statistics.max_depth_m > 0.05  # the water ponds at the low edge
    assert statistics.flooded_area_m2[0.05] >= statistics.flooded_area_m2[0.1] > 0.0
