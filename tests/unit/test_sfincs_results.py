"""Reading SFINCS results: map, statistics, balance, stations, GeoTIFF export."""

from pathlib import Path

import numpy as np
import pytest

from hydraulik.engines.sfincs.results import (
    depth_statistics,
    export_geotiff,
    read_map,
    read_stations,
    surface_balance,
    write_stations_csv,
)
from hydraulik.exceptions import (
    InputDataError,
    InvalidInputError,
    NotFoundError,
    UnsupportedError,
)

from ..synthetic import write_his, write_map

ROWS, COLUMNS = 4, 5


def _depth() -> np.ndarray:
    depth = np.zeros((ROWS, COLUMNS))
    depth[0, 1] = 0.40  # south row, second column
    depth[2, 3] = 0.12
    depth[1, 1] = 0.02  # under huthresh: not in hmax
    return depth


def test_the_map_carries_the_grid_the_masks_and_the_unmasked_depth(
    tmp_path: Path,
) -> None:
    active = np.ones((ROWS, COLUMNS), dtype=bool)
    active[3, 4] = False
    outflow = np.zeros((ROWS, COLUMNS), dtype=bool)
    outflow[0, 0] = True
    write_map(tmp_path / "m.nc", depth=_depth(), active=active, outflow=outflow)

    run = read_map(tmp_path / "m.nc")

    grid = run.grid
    assert (grid.x0_m, grid.y0_m, grid.dx_m, grid.epsg) == (1000.0, 2000.0, 10.0, 2180)
    assert grid.shape == (ROWS, COLUMNS)
    assert not run.active[3, 4] and run.outflow[0, 0] and run.outflow.sum() == 1
    assert run.depth_m[1, 1] == pytest.approx(0.02)  # h is not masked under huthresh
    assert np.isnan(run.max_depth_m[1, 1])  # hmax is
    assert run.max_depth_m[0, 1] == pytest.approx(0.40)
    assert np.isnan(run.depth_m[3, 4])
    assert run.huthresh_m == pytest.approx(0.05)
    assert (run.status, run.end_time_s) == (0, 7200.0)
    assert run.build_revision == "$Rev: v2.4.1 Galibier+"


def test_statistics_find_the_deepest_cell_and_count_the_area_above_each_limit(
    tmp_path: Path,
) -> None:
    write_map(tmp_path / "m.nc", depth=_depth())

    stats = depth_statistics(read_map(tmp_path / "m.nc"), (0.1, 0.3, 0.5))

    assert stats.max_depth_m == pytest.approx(0.40)
    assert (stats.max_depth_x_m, stats.max_depth_y_m) == (1015.0, 2005.0)
    assert stats.flooded_area_m2 == {0.1: 200.0, 0.3: 100.0, 0.5: 0.0}
    assert stats.active_area_m2 == ROWS * COLUMNS * 100.0
    assert stats.max_velocity_ms == pytest.approx(0.5)


def test_a_threshold_below_the_wet_dry_limit_is_refused_because_the_file_lacks_it(
    tmp_path: Path,
) -> None:
    write_map(tmp_path / "m.nc", depth=_depth())
    run = read_map(tmp_path / "m.nc")

    with pytest.raises(InvalidInputError) as caught:
        depth_statistics(run, (0.02,))

    assert caught.value.details["reason"] == "below_huthresh"


def test_a_closed_run_that_keeps_its_water_closes_the_balance(tmp_path: Path) -> None:
    # 30 mm of rain, 10 mm infiltrated, 20 mm left standing everywhere
    write_map(
        tmp_path / "m.nc",
        depth=np.full((ROWS, COLUMNS), 0.02),
        rain_m=0.03,
        infiltration_m=0.01,
    )

    balance = surface_balance(read_map(tmp_path / "m.nc"), expected_rain_mm=30.0)

    area = ROWS * COLUMNS * 100.0
    assert balance.rain_m3 == pytest.approx(0.03 * area)
    assert balance.infiltration_m3 == pytest.approx(0.01 * area)
    assert balance.stored_m3 == pytest.approx(0.02 * area)
    assert balance.residual_m3 == pytest.approx(0.0, abs=1e-3)
    assert not balance.open_boundary and balance.flags == ()


def test_water_that_vanishes_from_a_closed_model_is_flagged(tmp_path: Path) -> None:
    write_map(
        tmp_path / "m.nc",
        depth=np.full((ROWS, COLUMNS), 0.015),  # 5 mm missing = 16 % of the rain
        rain_m=0.03,
        infiltration_m=0.01,
    )

    balance = surface_balance(read_map(tmp_path / "m.nc"))

    assert balance.residual_percent == pytest.approx(16.67, abs=0.01)
    assert balance.flags == ("balance_residual",)


def test_the_residual_of_an_open_model_is_its_outflow_and_only_a_gain_is_wrong(
    tmp_path: Path,
) -> None:
    outflow = np.zeros((ROWS, COLUMNS), dtype=bool)
    outflow[0, 0] = True
    write_map(
        tmp_path / "left.nc",
        outflow=outflow,
        depth=np.full((ROWS, COLUMNS), 0.01),
        rain_m=0.03,
        infiltration_m=0.01,
    )
    write_map(
        tmp_path / "gain.nc",
        outflow=outflow,
        depth=np.full((ROWS, COLUMNS), 0.03),
        rain_m=0.03,
        infiltration_m=0.01,
    )

    left = surface_balance(read_map(tmp_path / "left.nc"))
    gain = surface_balance(read_map(tmp_path / "gain.nc"))

    assert left.open_boundary and left.flags == ()
    assert left.residual_m3 == pytest.approx(0.01 * ROWS * COLUMNS * 100.0)
    assert gain.flags == ("balance_gain",)


def test_the_rain_sfincs_applied_is_checked_against_the_precipitation_file(
    tmp_path: Path,
) -> None:
    write_map(
        tmp_path / "m.nc",
        depth=np.full((ROWS, COLUMNS), 0.02),
        rain_m=0.03,
        infiltration_m=0.01,
    )

    balance = surface_balance(read_map(tmp_path / "m.nc"), expected_rain_mm=45.0)

    assert balance.flags == ("rain_mismatch",)
    assert balance.expected_rain_m3 == pytest.approx(0.045 * ROWS * COLUMNS * 100.0)


def test_a_last_depth_map_before_the_end_of_the_run_and_a_missing_rain_map_are_flagged(
    tmp_path: Path,
) -> None:
    write_map(tmp_path / "early.nc", depth_time_s=6600.0)
    write_map(tmp_path / "bare.nc", with_accumulated=False)

    early = surface_balance(read_map(tmp_path / "early.nc"))
    bare = surface_balance(read_map(tmp_path / "bare.nc"))

    assert "time_mismatch" in early.flags
    assert bare.flags == ("no_rain_output",)


def test_stations_have_names_depth_and_the_time_of_the_maximum(tmp_path: Path) -> None:
    level = np.array([[0.0, 1.0], [0.3, 1.0], [0.1, 1.0]])  # (time, station)
    write_his(
        tmp_path / "his.nc",
        names=("outlet", "park"),
        x=(1015.0, 1035.0),
        y=(2005.0, 2025.0),
        bed=(0.0, 2.0),
        level=level,
    )

    outlet, park = read_stations(tmp_path / "his.nc")

    assert (outlet.name, outlet.x_m, outlet.y_m) == ("outlet", 1015.0, 2005.0)
    assert outlet.max_depth_m == pytest.approx(0.3)
    assert outlet.time_of_max_s == 600.0
    assert park.max_depth_m == 0.0  # the level stays under the bed
    assert park.depth_m.tolist() == [0.0, 0.0, 0.0]


def test_the_station_series_are_written_as_a_table(tmp_path: Path) -> None:
    write_his(tmp_path / "his.nc")

    write_stations_csv(read_stations(tmp_path / "his.nc"), tmp_path / "s.csv")

    lines = (tmp_path / "s.csv").read_text().splitlines()
    assert lines[0] == "time_s,station,level_m,depth_m"
    assert lines[3] == "1200,outlet,0.1000,0.1000"


def test_the_geotiff_is_north_up_in_the_crs_of_the_model_with_no_data_outside(
    tmp_path: Path,
) -> None:
    rasterio = pytest.importorskip("rasterio")
    active = np.ones((ROWS, COLUMNS), dtype=bool)
    active[3, 4] = False
    write_map(tmp_path / "m.nc", depth=_depth(), active=active)

    export_geotiff(read_map(tmp_path / "m.nc"), "max_depth", tmp_path / "d.tif")

    with rasterio.open(tmp_path / "d.tif") as raster:
        data = raster.read(1, masked=True)
        assert raster.crs.to_epsg() == 2180
        assert raster.shape == (ROWS, COLUMNS)
        assert tuple(raster.transform)[:6] == (10.0, 0.0, 1000.0, 0.0, -10.0, 2040.0)
        assert data[ROWS - 1, 1] == pytest.approx(0.40)  # row 0 of the model is south
        assert data.mask[0, COLUMNS - 1]  # the inactive cell: no data
        assert data.mask[ROWS - 2, 1]  # under huthresh: no data
        assert raster.tags()["variable"] == "max_depth"


def test_an_unknown_map_is_refused(tmp_path: Path) -> None:
    pytest.importorskip("rasterio")
    write_map(tmp_path / "m.nc")

    with pytest.raises(InvalidInputError):
        export_geotiff(read_map(tmp_path / "m.nc"), "elevation", tmp_path / "d.tif")


def test_a_missing_or_foreign_file_is_reported_not_traced(tmp_path: Path) -> None:
    (tmp_path / "text.nc").write_text("not netcdf", encoding="utf-8")

    with pytest.raises(NotFoundError):
        read_map(tmp_path / "none.nc")
    with pytest.raises(InputDataError) as caught:
        read_map(tmp_path / "text.nc")

    assert caught.value.details["reason"] == "invalid_netcdf"


def test_a_map_that_is_not_a_regular_grid_is_unsupported(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    with netcdf4.Dataset(tmp_path / "q.nc", "w") as dataset:  # a quadtree-style file
        dataset.createDimension("nodes", 3)
        dataset.createVariable("zb", "f4", ("nodes",))

    with pytest.raises(UnsupportedError) as caught:
        read_map(tmp_path / "q.nc")

    assert caught.value.details["reason"] == "map_layout"
