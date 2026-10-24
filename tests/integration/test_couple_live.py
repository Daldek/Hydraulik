"""``model couple`` on the real SFINCS library and the real SWMM (marker ``live``).

Build SFINCS with ``--enable-shared``, set ``HYDRAULIK_SFINCS_LIBRARY`` to the
``libsfincs`` it made and ``HYDRAULIK_SFINCS_QEXT_UNIT`` to ``ms`` (v2.4.1) or ``m3s``
(``main``), then ``pytest -m live``. The variables are read when the module is imported,
because the test fixtures clear the environment of every test.

The surface is a bowl of 20 x 20 cells of 5 m with a manhole in the middle that is too
small for the rain, so the node fills, floods, and SWMM's flooding returns to the cell.
"""

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hydraulik.cli import main
from hydraulik.engines.sfincs.model import (
    ModelInputs,
    RegularGrid,
    precip_breakpoints,
    write_model,
)
from hydraulik.engines.sfincs.results import read_map

LIBRARY = os.environ.get("HYDRAULIK_SFINCS_LIBRARY")
UNIT = os.environ.get("HYDRAULIK_SFINCS_QEXT_UNIT", "m3s")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not LIBRARY, reason="set HYDRAULIK_SFINCS_LIBRARY to run this test"
    ),
]


@pytest.fixture
def bowl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """The model directory and the network table; the environment names the library."""
    pytest.importorskip("netCDF4")
    pytest.importorskip("pyswmm")
    monkeypatch.setenv("HYDRAULIK_SFINCS_LIBRARY", str(LIBRARY))
    monkeypatch.setenv("HYDRAULIK_SFINCS_QEXT_UNIT", UNIT)
    grid = RegularGrid(0.0, 0.0, 5.0, 20, 20, 2180)
    rows, columns = np.indices(grid.shape)
    x, y = (columns + 0.5) * 5.0, (rows + 0.5) * 5.0
    bed = 10.0 + 0.02 * np.hypot(x - 52.5, y - 52.5)
    model = tmp_path / "model"
    model.mkdir()
    write_model(
        model,
        ModelInputs(
            grid=grid,
            elevation_m=bed,
            active=np.ones(grid.shape, dtype=bool),
            precip=precip_breakpoints([20.0] * 3, 600.0, 1800.0),
            tstop_s=1800.0,
            manning=0.03,
            observation_points=((52.5, 52.5, "node"),),
            dtmax_s=60.0,
            dtout_s=1800.0,
            dthisout_s=60.0,
        ),
    )
    network = tmp_path / "network.csv"
    network.write_text(
        "name,x_m,y_m,rim_m,depth_m,to,diameter_m\n"
        f"J1,52.5,52.5,{bed[10, 10]:.4f},2,OUT,0.15\n"
        "OUT,150,52.5,9.0,2,,\n",
        encoding="utf-8",
    )
    return model, network


def couple(
    capsys: pytest.CaptureFixture[str],
    model: Path,
    network: Path,
    out: Path,
    *more: str,
) -> tuple[int, dict[str, Any]]:
    code = main(
        ["model", "couple", "--model", str(model), "--network", str(network),
         "--output-dir", str(out), *more, "--json"]
    )  # fmt: skip
    captured = capsys.readouterr()
    if code != 0:
        return code, json.loads(captured.err.strip().splitlines()[-1])
    return code, json.loads(captured.out)


def test_flooded_water_returns_to_the_street_and_the_books_close(
    tmp_path: Path, bowl: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    model, network = bowl
    out = tmp_path / "coupled"

    code, envelope = couple(capsys, model, network, out, "--exchange-interval-s", "5")

    assert code == 0, envelope
    result = envelope["result"]
    balance, node = result["balance"], result["nodes"][0]
    assert balance["flags"] == [] and abs(balance["total_error_percent"]) < 0.5
    assert balance["rain_m3"] == pytest.approx(60e-3 * 100 * 100, rel=0.01)
    assert node["flooded_m3"] > 100.0  # the pipe takes a fraction of the rain
    assert node["returned_m3"] + node["pending_m3"] == pytest.approx(
        node["flooded_m3"], abs=1e-6
    )
    assert abs(balance["network_side_error_m3"]) < 0.01 * node["flooded_m3"]
    assert abs(balance["surface_side_error_m3"]) < 0.5  # the error of SFINCS alone
    assert abs(result["network"]["totals"]["continuity_error_percent"]) < 1.0
    assert result["coupling"]["intervals"] == 360
    assert result["coupling"]["overshoot_s"]["max"] < 5.0
    assert sorted(p.name for p in out.iterdir()) == [
        "coupling.csv",
        "network.inp",
        "network.rpt",
        "sfincs.log",
        "sfincs_his.nc",
        "sfincs_map.nc",
    ]
    run = read_map(out / "sfincs_map.nc")
    area = run.cell_area_m2
    assert run.status == 0
    assert float(np.nansum(run.depth_m)) * area == pytest.approx(
        balance["surface_m3"], rel=0.005
    )  # the library and the map tell the same story
    assert result["surface"]["stations"][0]["name"] == "node"


def test_a_wrong_qext_unit_shows_as_a_balance_that_does_not_close(
    tmp_path: Path,
    bowl: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model, network = bowl
    monkeypatch.setenv("HYDRAULIK_SFINCS_QEXT_UNIT", "ms" if UNIT == "m3s" else "m3s")

    code, envelope = couple(
        capsys, model, network, tmp_path / "wrong", "--exchange-interval-s", "5"
    )

    assert code == 0  # a balance that does not close is a warning, not an error
    balance = envelope["result"]["balance"]
    assert "balance_residual" in balance["flags"]
    assert (
        abs(balance["total_error_percent"]) > 2.0
    )  # far above the 1 % that is flagged
    warning = next(n for n in envelope["notices"] if n["code"] == "balance_residual")
    assert "sfincs.qext_unit" in warning["message"]


def test_the_coordinator_mode_closes_the_books_too(
    tmp_path: Path, bowl: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    model, network = bowl

    code, envelope = couple(
        capsys, model, network, tmp_path / "c", "--mode", "coordinator",
        "--exchange-interval-s", "2",
    )  # fmt: skip

    assert code == 0, envelope
    result = envelope["result"]
    assert result["coupling"]["mode"] == "coordinator"
    assert result["coupling"]["relaxation"] == 0.1
    assert abs(result["balance"]["total_error_percent"]) < 1.0
    assert result["nodes"][0]["returned_m3"] == 0.0  # the law spills, not SWMM
    assert result["nodes"][0]["peak_return_m3s"] > 0.0


def test_a_rim_above_the_bed_is_refused_by_the_real_run_with_the_nodes_named(
    tmp_path: Path, bowl: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    model, network = bowl
    network.write_text(
        network.read_text(encoding="utf-8").replace(
            "J1,52.5,52.5,10.0000", "J1,52.5,52.5,10.5"
        ),
        encoding="utf-8",
    )

    code, error = couple(capsys, model, network, tmp_path / "rim")

    assert code == 2
    assert error["details"]["reason"] == "rim_mismatch"
    assert error["details"]["nodes"][0]["node"] == "J1"
    assert not any((tmp_path / "rim").iterdir())


def test_check_sees_the_library_and_plans_the_files(
    tmp_path: Path, bowl: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    model, network = bowl

    code, envelope = couple(capsys, model, network, tmp_path / "plan", "--check")

    assert code == 0
    assert envelope["result"]["blockers"] == []
    assert not (tmp_path / "plan").exists()
