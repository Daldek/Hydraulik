"""Reading ``sfincs.inp``: the reader agrees with the writer."""

from pathlib import Path

import numpy as np
import pytest

from hydraulik.engines.sfincs.inp import planned_outputs, read_inp, tstop_s
from hydraulik.engines.sfincs.model import (
    ModelInputs,
    RegularGrid,
    precip_breakpoints,
    write_model,
)
from hydraulik.exceptions import InputDataError, NotFoundError


def _model(tmp_path: Path, **changes: object) -> Path:
    grid = RegularGrid(0.0, 0.0, 10.0, 3, 2)
    inputs = ModelInputs(
        grid=grid,
        elevation_m=np.zeros(grid.shape),
        active=np.ones(grid.shape, dtype=bool),
        precip=precip_breakpoints([6.0], 600.0, 5400.0),
        tstop_s=5400.0,
        **changes,  # type: ignore[arg-type]
    )
    write_model(tmp_path, inputs)
    return tmp_path


def test_what_the_writer_wrote_is_read_back_from_the_file_or_the_directory(
    tmp_path: Path,
) -> None:
    _model(tmp_path)

    from_directory = read_inp(tmp_path)
    from_file = read_inp(tmp_path / "sfincs.inp")

    assert from_directory == from_file
    assert (from_directory["mmax"], from_directory["nmax"]) == ("3", "2")
    assert from_directory["inputformat"] == "bin"
    assert tstop_s(from_directory) == 5400.0


def test_keys_are_lower_case_and_lines_without_an_equals_sign_are_skipped(
    tmp_path: Path,
) -> None:
    (tmp_path / "sfincs.inp").write_text(
        "MMAX = 10\nthis line is text\n  Dx=5.0 \n= 7\n", encoding="utf-8"
    )

    assert read_inp(tmp_path) == {"mmax": "10", "dx": "5.0"}


def test_a_directory_without_a_model_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError) as caught:
        read_inp(tmp_path)

    assert caught.value.details["reason"] == "model_missing"


@pytest.mark.parametrize("keys", [{}, {"tstart": "x", "tstop": "y"}])
def test_a_file_without_valid_times_is_data_error(keys: dict[str, str]) -> None:
    with pytest.raises(InputDataError) as caught:
        tstop_s(keys)

    assert caught.value.details["reason"] == "invalid_inp"


def test_the_his_file_is_planned_only_for_a_model_with_points_or_cross_sections(
    tmp_path: Path,
) -> None:
    plain = read_inp(_model(tmp_path))
    with_points = {"obsfile": "sfincs.obs"}
    with_sections = {"crsfile": "sfincs.crs"}

    assert planned_outputs(plain) == ("sfincs_map.nc", "sfincs.log")
    assert planned_outputs(with_points) == (
        "sfincs_map.nc",
        "sfincs_his.nc",
        "sfincs.log",
    )
    assert planned_outputs(with_sections)[1] == "sfincs_his.nc"
