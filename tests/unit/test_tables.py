"""The rain table and the hydrograph table: reading, validation, round trip."""

from pathlib import Path

import pytest

from hydraulik.data.tables import (
    Hydrograph,
    read_hydrograph,
    read_rain_table,
    render_rain_table,
)
from hydraulik.exceptions import InputDataError, NotFoundError


def _write(tmp_path: Path, text: str, name: str = "t.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_rain_table_written_by_hydraulik_is_read_back(tmp_path: Path) -> None:
    depths = [0.5, 2.25, 4.0, 1.125]
    path = _write(tmp_path, render_rain_table(5.0, depths))

    table = read_rain_table(path)

    assert table.step_min == 5.0
    assert table.depth_mm == pytest.approx(depths)
    assert table.duration_min == 20.0
    assert table.total_mm == pytest.approx(7.875)
    assert table.peak_intensity_mm_h == pytest.approx(48.0)  # 4 mm in 5 min


def test_a_rain_table_may_carry_other_columns_in_any_order_and_a_bom(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "\ufeffnote,depth_mm,time_min\nx,1.5,10\ny,2.5,20\n")

    table = read_rain_table(path)

    assert (table.step_min, table.depth_mm) == (10.0, (1.5, 2.5))


@pytest.mark.parametrize(
    "text",
    [
        "time_min,depth_mm\n",  # no rows
        "time_min\n5\n",  # a column is missing
        "time_min,depth_mm\n5,x\n",  # not a number
        "time_min,depth_mm\n5,nan\n",  # not finite
        "time_min,depth_mm\n5,1\n11,1\n",  # not regular
        "time_min,depth_mm\n10,1\n15,1\n",  # does not start at the first step
        "time_min,depth_mm\n5,-1\n",  # negative depth
        "time_min,depth_mm\n0,1\n",  # zero step
    ],
)
def test_an_invalid_rain_table_is_a_data_error_that_names_the_file(
    tmp_path: Path, text: str
) -> None:
    with pytest.raises(InputDataError) as caught:
        read_rain_table(_write(tmp_path, text, "rain.csv"))

    assert caught.value.details["reason"] == "invalid_rain_table"
    assert "rain.csv" in str(caught.value)


def test_a_missing_table_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        read_hydrograph(tmp_path / "none.csv")


def test_a_hydrograph_is_interpolated_in_seconds_and_zero_outside(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "time_min,discharge_m3s\n1,0\n3,4\n5,0\n")

    series = read_hydrograph(path)

    assert series.times_s == (60.0, 180.0, 300.0)
    assert [series.at(t) for t in (0.0, 60.0, 120.0, 180.0, 240.0, 300.0, 301.0)] == [
        0.0,
        0.0,
        2.0,
        4.0,
        2.0,
        0.0,
        0.0,
    ]
    assert series.volume_m3 == pytest.approx(480.0)  # 0.5 * 240 s * 4 m3/s


def test_a_single_point_hydrograph_has_no_volume() -> None:
    single = Hydrograph((0.0,), (3.0,))

    assert single.at(0.0) == 3.0
    assert single.volume_m3 == 0.0


@pytest.mark.parametrize(
    "text",
    [
        "time_min,discharge_m3s\n0,1\n0,2\n",  # time does not increase
        "time_min,discharge_m3s\n0,-1\n",  # negative discharge
        "time_min,discharge_m3s\n",  # no rows
    ],
)
def test_an_invalid_hydrograph_is_a_data_error(tmp_path: Path, text: str) -> None:
    with pytest.raises(InputDataError) as caught:
        read_hydrograph(_write(tmp_path, text))

    assert caught.value.details["reason"] == "invalid_hydrograph"
