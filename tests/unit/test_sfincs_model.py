"""The SFINCS regular-grid writer: file layout, binary order, rain tail, validation."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hydraulik.engines.sfincs.model import (
    ModelInputs,
    RegularGrid,
    active_order,
    precip_breakpoints,
    render_inp,
    write_model,
)
from hydraulik.exceptions import InvalidInputError

GRID = RegularGrid(100.0, 200.0, 10.0, columns=3, rows=2)
BASE = ModelInputs(
    grid=GRID,
    elevation_m=np.arange(6, dtype=float).reshape(2, 3),
    active=np.ones((2, 3), dtype=bool),
    precip=precip_breakpoints([6.0], 600.0, 1200.0),
    tstop_s=1200.0,
)


def _inputs(**changes: Any) -> ModelInputs:
    return replace(BASE, **changes)


def test_active_cells_are_counted_down_the_rows_first() -> None:
    active = np.array([[True, False], [True, True]])

    assert active_order(active).tolist() == [0, 1, 3]


def test_index_and_elevation_files_follow_the_sfincs_order(tmp_path: Path) -> None:
    write_model(tmp_path, BASE)

    index = np.frombuffer((tmp_path / "sfincs.ind").read_bytes(), dtype=np.int32)
    elevation = np.frombuffer((tmp_path / "sfincs.dep").read_bytes(), dtype=np.float32)

    assert index.tolist() == [6, 1, 2, 3, 4, 5, 6]  # np, then (m - 1) * nmax + n
    assert elevation.tolist() == [0.0, 3.0, 1.0, 4.0, 2.0, 5.0]  # column by column


def test_inactive_cells_are_left_out_of_every_file(tmp_path: Path) -> None:
    active = np.ones((2, 3), dtype=bool)
    active[1, 0] = False

    write_model(tmp_path, _inputs(active=active, manning=np.full((2, 3), 0.03)))

    index = np.frombuffer((tmp_path / "sfincs.ind").read_bytes(), dtype=np.int32)
    assert index[0] == 5 and 2 not in index[1:]
    assert (tmp_path / "sfincs.msk").stat().st_size == 5
    assert (tmp_path / "sfincs.dep").stat().st_size == 5 * 4
    assert (tmp_path / "sfincs.man").stat().st_size == 5 * 4


def test_outflow_cells_get_mask_value_three(tmp_path: Path) -> None:
    outflow = np.zeros((2, 3), dtype=bool)
    outflow[0, 0] = True

    write_model(tmp_path, _inputs(outflow=outflow))

    mask = np.frombuffer((tmp_path / "sfincs.msk").read_bytes(), dtype=np.int8)
    assert mask.tolist() == [3, 1, 1, 1, 1, 1]


def test_curve_number_is_written_as_storage_in_inches(tmp_path: Path) -> None:
    cn = np.array([[80.0, 100.0, np.nan], [60.0, 80.0, 80.0]])

    write_model(tmp_path, _inputs(curve_number=cn))

    storage = np.frombuffer((tmp_path / "sfincs.scs").read_bytes(), dtype=np.float32)
    expected = [2.5, 1000 / 60 - 10, 0.0, 2.5, 0.0, 2.5]  # S = 1000 / CN - 10
    assert storage.tolist() == pytest.approx(expected, abs=1e-5)
    keys = (tmp_path / "sfincs.inp").read_text().replace(" ", "").splitlines()
    assert "scsfile=sfincs.scs" in keys and "sfacinf=0.2" in keys


def test_manning_is_a_file_for_an_array_and_a_key_for_a_number(tmp_path: Path) -> None:
    uniform = tmp_path / "uniform"
    varying = tmp_path / "varying"
    uniform.mkdir()
    varying.mkdir()

    write_model(uniform, _inputs(manning=0.035))
    write_model(varying, _inputs(manning=np.full((2, 3), 0.03)))

    assert "manning         = 0.035" in (uniform / "sfincs.inp").read_text()
    assert not (uniform / "sfincs.man").exists()
    assert "manningfile     = sfincs.man" in (varying / "sfincs.inp").read_text()


def test_inp_carries_the_grid_the_times_and_the_overrides() -> None:
    text = render_inp(
        replace(BASE, extra={"huvmin": 0.01, "dtmax": 5}),
        files={
            "index": "sfincs.ind",
            "mask": "sfincs.msk",
            "elevation": "sfincs.dep",
            "precip": "sfincs.precip",
        },
    )

    keys = dict(line.split("=", 1) for line in text.splitlines())
    keys = {k.strip(): v.strip() for k, v in keys.items()}
    assert (keys["mmax"], keys["nmax"], keys["dx"]) == ("3", "2", "10.0")
    assert (keys["x0"], keys["y0"], keys["rotation"]) == ("100.0", "200.0", "0")
    assert keys["tstop"] == "20000101 002000"
    assert keys["inputformat"] == "bin"
    assert keys["storecumprcp"] == "1"
    assert keys["dtmax"] == "5"  # the override replaces the generated value
    assert keys["huvmin"] == "0.01"


def test_observation_points_are_written_with_their_names(tmp_path: Path) -> None:
    write_model(tmp_path, _inputs(observation_points=((115.0, 205.0, "outlet"),)))

    assert (tmp_path / "sfincs.obs").read_text() == "115.000 205.000 outlet\n"
    assert "obsfile         = sfincs.obs" in (tmp_path / "sfincs.inp").read_text()


def test_rain_series_ends_flat_and_reaches_tstop() -> None:
    series = precip_breakpoints([5.0, 0.0, 2.0], 300.0, 3000.0)

    assert series.times_s[-1] == 3000.0
    assert series.intensity_mm_h[-2:] == (0.0, 0.0)  # SFINCS extrapolates the end
    assert series.depth_mm() == pytest.approx(7.0, rel=0.005)


def test_rain_that_lasts_to_tstop_still_gets_a_flat_tail() -> None:
    series = precip_breakpoints([1.0], 600.0, 600.0)

    assert series.times_s[-1] > 600.0
    assert series.intensity_mm_h[-2:] == (0.0, 0.0)


@pytest.mark.parametrize(
    ("depths", "step", "tstop"),
    [
        ([1.0], 600.0, 300.0),
        ([-1.0], 600.0, 900.0),
        ([], 600.0, 900.0),
        ([1.0], 0.0, 9),
    ],
)
def test_invalid_rain_is_refused(
    depths: list[float], step: float, tstop: float
) -> None:
    with pytest.raises(InvalidInputError):
        precip_breakpoints(depths, step, tstop)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"elevation_m": np.zeros((3, 3))}, "shape_mismatch"),
        ({"active": np.zeros((2, 3), dtype=bool)}, "empty_domain"),
        ({"manning": 0.0}, "out_of_range"),
        ({"manning": np.full((2, 3), np.nan)}, "out_of_range"),
        ({"curve_number": np.full((2, 3), 20.0)}, "out_of_range"),
        ({"observation_points": ((0.0, 0.0, "x"),)}, "outside_grid"),
    ],
)
def test_invalid_inputs_are_refused_before_anything_is_written(
    tmp_path: Path, changes: dict[str, Any], reason: str
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        write_model(tmp_path, _inputs(**changes))

    assert caught.value.details["reason"] == reason
    assert list(tmp_path.iterdir()) == []


def test_a_gap_in_the_elevation_of_an_active_cell_is_refused(tmp_path: Path) -> None:
    elevation = BASE.elevation_m.copy()
    elevation[0, 0] = np.nan

    with pytest.raises(InvalidInputError) as caught:
        write_model(tmp_path, _inputs(elevation_m=elevation))

    assert caught.value.details["reason"] == "elevation_gap"


def test_an_outflow_cell_outside_the_domain_is_refused(tmp_path: Path) -> None:
    active = np.ones((2, 3), dtype=bool)
    active[0, 0] = False
    outflow = np.zeros((2, 3), dtype=bool)
    outflow[0, 0] = True

    with pytest.raises(InvalidInputError) as caught:
        write_model(tmp_path, _inputs(active=active, outflow=outflow))

    assert caught.value.details["reason"] == "outflow_outside_domain"


def test_grid_finds_the_cell_of_a_point_and_the_centre_of_a_cell() -> None:
    assert GRID.cell_of(115.0, 205.0) == (0, 1)
    assert GRID.cell_of(99.9, 205.0) is None
    assert GRID.cell_of(115.0, 220.0) is None
    assert GRID.centre_of(1, 2) == (125.0, 215.0)
