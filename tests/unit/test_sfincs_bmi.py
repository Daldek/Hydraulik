"""The layout of a model, the BMI wrapper and the surface, without the real library."""

import ctypes.util
import os
from pathlib import Path

import numpy as np
import pytest

import hydraulik.engines.sfincs.bmi as bmi_module
from hydraulik.engines.sfincs.bmi import SfincsBmi, SfincsSurface
from hydraulik.engines.sfincs.inp import patch_inp, read_inp
from hydraulik.engines.sfincs.layout import ModelLayout
from hydraulik.engines.sfincs.model import (
    ModelInputs,
    RegularGrid,
    active_order,
    precip_breakpoints,
    write_model,
)
from hydraulik.exceptions import (
    EngineError,
    InputDataError,
    NotFoundError,
    UnsupportedError,
)

from ..coupling_fakes import FakeBmi


def write_small_model(directory: Path, active: np.ndarray | None = None) -> RegularGrid:
    """A 3 columns x 2 rows model of 5 m cells; ``active`` selects the cells."""
    grid = RegularGrid(100.0, 200.0, 5.0, 3, 2, 2180)
    mask = np.ones(grid.shape, dtype=bool) if active is None else active
    write_model(
        directory,
        ModelInputs(
            grid=grid,
            elevation_m=np.zeros(grid.shape),
            active=mask,
            precip=precip_breakpoints([1.0], 600.0, 1200.0),
            tstop_s=1200.0,
            dtmax_s=2.0,
        ),
    )
    return grid


def test_the_position_of_a_cell_is_its_rank_among_the_active_cells_in_sfincs_order(
    tmp_path: Path,
) -> None:
    active = np.array([[True, False, True], [True, True, False]])  # row 0 is the south
    grid = write_small_model(tmp_path, active)

    layout = ModelLayout.read(tmp_path)

    assert layout.active_cells == 4
    expected = {int(k): rank for rank, k in enumerate(active_order(active))}
    for row in range(2):
        for column in range(3):
            x, y = grid.centre_of(row, column)
            flat = column * 2 + row  # Fortran order: the row runs fastest
            found = layout.cell_of(x, y)
            assert found == (expected[flat] if active[row, column] else None)
    assert layout.cell_of(99.0, 205.0) is None  # west of the grid
    assert layout.cell_of(105.0, 211.0) is None  # north of it


@pytest.mark.parametrize(
    ("extra", "key"),
    [
        ("rotation = 15\n", "rotation"),
        ("qtrfile = sfincs.qtr\n", "qtrfile"),
        ("sbgfile = sfincs.sbg\n", "sbgfile"),
        ("inputformat = asc\n", "inputformat"),
    ],
)
def test_models_that_number_their_cells_differently_are_refused(
    tmp_path: Path, extra: str, key: str
) -> None:
    write_small_model(tmp_path)
    inp = tmp_path / "sfincs.inp"
    inp.write_text(
        "\n".join(
            line for line in inp.read_text().splitlines() if not line.startswith(key)
        )
        + "\n"
        + extra
    )

    with pytest.raises(UnsupportedError) as caught:
        ModelLayout.read(tmp_path)

    assert caught.value.details["reason"] == "model_layout"


def test_a_model_without_input_or_with_a_wrong_index_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        ModelLayout.read(tmp_path)
    write_small_model(tmp_path)
    (tmp_path / "sfincs.ind").write_bytes(np.int32(9).tobytes())  # claims 9, holds none

    with pytest.raises(InputDataError) as caught:
        ModelLayout.read(tmp_path)

    assert caught.value.details["reason"] == "invalid_index"


def test_keys_of_sfincs_inp_are_set_or_added_and_the_rest_is_kept(
    tmp_path: Path,
) -> None:
    write_small_model(tmp_path)
    before = read_inp(tmp_path)

    patch_inp(tmp_path, {"DTMAX": 1.0, "newkey": "x"})

    after = read_inp(tmp_path)
    assert after["dtmax"] == "1.0" and after["newkey"] == "x"
    assert {k: v for k, v in after.items() if k not in ("dtmax", "newkey")} == {
        k: v for k, v in before.items() if k != "dtmax"
    }
    with pytest.raises(NotFoundError):
        patch_inp(tmp_path / "nowhere", {"dtmax": 1})


def test_a_missing_or_foreign_library_is_an_engine_error_with_the_fix(
    tmp_path: Path,
) -> None:
    libm = ctypes.util.find_library("m")
    with pytest.raises(EngineError) as missing:
        SfincsBmi(tmp_path / "libsfincs.so")
    assert missing.value.details["reason"] == "engine_unavailable"
    assert "--enable-shared" in str(missing.value.hint)
    if libm:
        with pytest.raises(EngineError) as foreign:
            SfincsBmi(libm)
        assert "is not the SFINCS library" in str(foreign.value)
        assert "initialize" in foreign.value.details["missing"]


def test_sfincs_starts_one_model_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bmi_module, "_used", True)

    with pytest.raises(EngineError) as caught:
        SfincsBmi.__new__(SfincsBmi).initialize()

    assert caught.value.details["reason"] == "one_model_per_process"


@pytest.fixture
def fake_bmi(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[float, float], int]:
    """Let SfincsSurface load the stand-in for the library."""
    positions: dict[tuple[float, float], int] = {}
    monkeypatch.setattr(
        bmi_module, "SfincsBmi", lambda library: FakeBmi(library, positions=positions)
    )
    return positions


def test_the_surface_lives_in_the_model_directory_and_finalises_what_it_started(
    tmp_path: Path, fake_bmi: dict[tuple[float, float], int]
) -> None:
    four = np.array([[True, True, True], [True, False, False]])  # the fake has four
    write_small_model(tmp_path, four)
    here = Path.cwd()

    with SfincsSurface("libsfincs.so", tmp_path, qext_unit="m3s") as surface:
        assert Path.cwd() == tmp_path.resolve()
        assert surface.end_s == 100.0 and surface.max_step_s == 2.0
        assert surface.advance_to(10.0) == 10.25  # the library may overshoot
        driven = FakeBmi.last
    assert driven is not None and driven.flags == {"qext": True}
    assert driven.calls == ["initialize", "update_until(10)", "finalize"]
    assert Path.cwd() == here


def test_a_point_is_looked_up_on_the_index_and_the_library_must_agree(
    tmp_path: Path, fake_bmi: dict[tuple[float, float], int]
) -> None:
    four = np.array([[True, True, True], [True, False, False]])
    grid = write_small_model(tmp_path, four)
    first = grid.centre_of(0, 0)
    inactive = grid.centre_of(1, 2)
    fake_bmi[first] = 0
    fake_bmi[grid.centre_of(1, 0)] = 3  # the library says 3; the index file says 1

    with SfincsSurface("libsfincs.so", tmp_path, qext_unit="m3s") as surface:
        assert surface.locate(*first) == 0
        assert surface.locate(*inactive) is None  # the library is never asked
        assert surface.locate(0.0, 0.0) is None
        with pytest.raises(EngineError) as caught:
            surface.locate(*grid.centre_of(1, 0))

    assert caught.value.details["reason"] == "cell_numbering"


def test_qext_is_written_in_the_unit_of_the_library(
    tmp_path: Path, fake_bmi: dict[tuple[float, float], int]
) -> None:
    write_small_model(tmp_path, np.array([[True, True, True], [True, False, False]]))

    with SfincsSurface("libsfincs.so", tmp_path, qext_unit="m3s") as surface:
        surface.set_source_m3s(1, -0.5)
        assert FakeBmi.last is not None and FakeBmi.last.qext[1] == -0.5
    with SfincsSurface("libsfincs.so", tmp_path, qext_unit="ms") as surface:
        surface.set_source_m3s(1, -0.5)
        assert FakeBmi.last is not None
        assert FakeBmi.last.qext[1] == pytest.approx(-0.5 / 25.0)  # per m2 of the cell


def test_the_surface_reads_levels_and_stores_the_unmasked_water(
    tmp_path: Path, fake_bmi: dict[tuple[float, float], int]
) -> None:
    write_small_model(tmp_path, np.array([[True, True, True], [True, False, False]]))

    with SfincsSurface("libsfincs.so", tmp_path, qext_unit="m3s") as surface:
        assert (surface.level_m(2), surface.bed_m(2), surface.area_m2(2)) == (
            3.0,
            0.5,
            25.0,
        )
        assert surface.stored_volume_m3() == pytest.approx(
            (0.5 + 1.5 + 2.5 + 3.5) * 25.0
        )


def test_a_library_with_another_count_of_cells_is_refused(
    tmp_path: Path, fake_bmi: dict[tuple[float, float], int]
) -> None:
    write_small_model(tmp_path)  # six cells, the fake has four

    with (
        pytest.raises(EngineError) as caught,
        SfincsSurface("libsfincs.so", tmp_path, qext_unit="m3s"),
    ):
        pass

    assert caught.value.details["reason"] == "cell_numbering"
    assert Path.cwd() != tmp_path.resolve() and os.getcwd() == str(Path.cwd())
