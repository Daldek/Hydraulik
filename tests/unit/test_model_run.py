"""``model run`` with a fake SFINCS program: staging, planning, errors, notices."""

from pathlib import Path

import numpy as np
import pytest

from hydraulik import check_command, run_command, run_model
from hydraulik.engines.detect import EngineStatus, SfincsInstall
from hydraulik.exceptions import (
    ConflictError,
    EngineError,
    MissingDependencyError,
    UnsupportedError,
)

from ..synthetic import fake_sfincs, write_his, write_map

INP = """mmax            = 5
nmax            = 4
dx              = 10.0
tstart          = 20000101 000000
tstop           = 20000101 020000
inputformat     = bin
outputformat    = net
precipfile      = sfincs.precip
"""


@pytest.fixture
def model(tmp_path: Path) -> Path:
    """A model directory whose rain file holds 30 mm."""
    folder = tmp_path / "model"
    folder.mkdir()
    (folder / "sfincs.inp").write_text(
        INP + "obsfile         = sfincs.obs\n", encoding="utf-8"
    )
    (folder / "sfincs.precip").write_text("0 60\n1800 60\n", encoding="utf-8")
    (folder / "sfincs.obs").write_text("1025 2015 outlet\n", encoding="utf-8")
    (folder / "sfincs.dep").write_bytes(b"\x00" * 80)
    return folder


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SfincsInstall:
    """Make ``model run`` find the fake SFINCS, which writes a consistent closed run."""
    install = fake_sfincs(tmp_path)
    status = EngineStatus("sfincs", True, "setting", "fake-sfincs", "fake", "fake")
    monkeypatch.setattr(
        "hydraulik.operations.model.detect_sfincs", lambda settings: (status, install)
    )
    write_map(
        tmp_path / "result_map.nc",
        depth=np.full((4, 5), 0.02),
        rain_m=0.03,
        infiltration_m=0.01,
    )
    write_his(tmp_path / "result_his.nc")
    monkeypatch.setenv("FAKE_SFINCS_MAP", str(tmp_path / "result_map.nc"))
    monkeypatch.setenv("FAKE_SFINCS_HIS", str(tmp_path / "result_his.nc"))
    return install


def _names(folder: Path) -> list[str]:
    return sorted(item.name for item in folder.iterdir())


def test_a_run_writes_the_results_and_nothing_else_and_reports_the_balance(
    tmp_path: Path, model: Path, engine: SfincsInstall
) -> None:
    out = tmp_path / "run"

    document = run_model(model=model, output_dir=out)

    body = document.to_dict()
    assert body["schema"] == "hydraulik-run/1"
    assert _names(out) == ["sfincs.log", "sfincs_his.nc", "sfincs_map.nc"]
    assert [f["status"] for f in body["files"]] == ["written"] * 3
    assert all(len(f["sha256"]) == 64 for f in body["files"])
    assert body["engine"]["kind"] == "exe"
    results = body["results"]
    assert results["schema"] == "hydraulik-results/1"
    assert results["source"] == str(out.resolve() / "sfincs_map.nc")
    assert results["balance"]["flags"] == []
    assert results["balance"]["residual_percent"] == pytest.approx(0.0, abs=0.01)
    assert results["balance"]["expected_rain_m3"] == pytest.approx(30.0e-3 * 20 * 100.0)
    assert [s["name"] for s in results["stations"]] == ["outlet"]
    assert _names(model) == ["sfincs.dep", "sfincs.inp", "sfincs.obs", "sfincs.precip"]


def test_a_failed_run_leaves_the_output_directory_without_a_file_or_staging(
    tmp_path: Path, model: Path, engine: SfincsInstall
) -> None:
    (model / "mode.txt").write_text("fail", encoding="utf-8")
    out = tmp_path / "run"

    with pytest.raises(EngineError) as caught:
        run_model(model=model, output_dir=out)

    assert caught.value.details["reason"] == "engine_failed"
    assert "sfincs.precip" in str(caught.value)
    assert list(out.iterdir()) == []  # the staging directory is gone too


def test_a_program_that_exits_without_a_map_is_an_engine_error_with_the_log(
    tmp_path: Path, model: Path, engine: SfincsInstall
) -> None:
    (model / "mode.txt").write_text("silent", encoding="utf-8")

    with pytest.raises(EngineError) as caught:
        run_model(model=model, output_dir=tmp_path / "run")

    assert "without writing sfincs_map.nc" in str(caught.value)
    assert "100% complete" in caught.value.details["log_tail"]


def test_a_map_whose_status_is_not_zero_is_not_published(
    tmp_path: Path, model: Path, engine: SfincsInstall, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_map(tmp_path / "bad.nc", status=3.0)
    monkeypatch.setenv("FAKE_SFINCS_MAP", str(tmp_path / "bad.nc"))

    with pytest.raises(EngineError) as caught:
        run_model(model=model, output_dir=tmp_path / "run")

    assert caught.value.details["status"] == 3
    assert list((tmp_path / "run").iterdir()) == []


def test_a_balance_that_does_not_close_is_a_warning_not_an_error(
    tmp_path: Path, model: Path, engine: SfincsInstall, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_map(tmp_path / "leaky.nc", depth=np.zeros((4, 5)), rain_m=0.03)
    monkeypatch.setenv("FAKE_SFINCS_MAP", str(tmp_path / "leaky.nc"))

    document = run_model(model=model, output_dir=tmp_path / "run")

    assert document.status == "ok"
    warnings = [n["code"] for n in document.notices if n["level"] == "warning"]
    assert warnings == ["balance_residual"]
    assert document.to_dict()["results"]["balance"]["flags"] == ["balance_residual"]


def test_the_rain_in_the_map_is_checked_against_the_precipitation_file(
    tmp_path: Path, model: Path, engine: SfincsInstall, monkeypatch: pytest.MonkeyPatch
) -> None:
    (model / "sfincs.precip").write_text("0 120\n1800 120\n", encoding="utf-8")  # 60 mm

    document = run_model(model=model, output_dir=tmp_path / "run")

    warnings = [n["code"] for n in document.notices if n["level"] == "warning"]
    assert warnings == ["rain_mismatch"]


def test_the_output_may_be_the_model_directory_and_the_inputs_stay_as_they_were(
    tmp_path: Path, model: Path, engine: SfincsInstall
) -> None:
    run_model(model=model, output_dir=model)

    assert _names(model) == [
        "sfincs.dep",
        "sfincs.inp",
        "sfincs.log",
        "sfincs.obs",
        "sfincs.precip",
        "sfincs_his.nc",
        "sfincs_map.nc",
    ]
    assert (model / "sfincs.dep").read_bytes() == b"\x00" * 80


def test_existing_results_are_a_conflict_until_force_replaces_them(
    tmp_path: Path, model: Path, engine: SfincsInstall
) -> None:
    out = tmp_path / "run"
    run_model(model=model, output_dir=out)

    with pytest.raises(ConflictError) as caught:
        run_model(model=model, output_dir=out)
    again = run_model(model=model, output_dir=out, force=True)

    assert caught.value.details["reason"] == "output_exists"
    assert len(caught.value.details["paths"]) == 3
    assert [f["status"] for f in again.to_dict()["files"]] == ["replaced"] * 3


def test_check_plans_the_files_and_the_engine_and_writes_nothing(
    tmp_path: Path, model: Path, engine: SfincsInstall
) -> None:
    out = tmp_path / "run"

    plan = check_command("model run", model=str(model), output_dir=str(out))

    body = plan.to_dict()
    assert body["schema"] == "hydraulik-plan/1"
    assert [t["name"] for t in body["targets"]] == [
        "sfincs_map.nc",
        "sfincs_his.nc",
        "sfincs.log",
    ]
    assert {t["action"] for t in body["targets"]} == {"write"}
    assert body["blockers"] == []
    assert any("fake-sfincs" in step for step in body["steps"])
    assert not out.exists()


def test_check_names_a_missing_engine_as_a_blocker_and_the_run_refuses(
    tmp_path: Path, model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = EngineStatus(
        "sfincs", False, None, None, None, "no sfincs found", "Install SFINCS."
    )
    monkeypatch.setattr(
        "hydraulik.operations.model.detect_sfincs", lambda settings: (status, None)
    )

    plan = run_command(
        "model run", model=str(model), output_dir=str(tmp_path / "o"), check=True
    )
    with pytest.raises(MissingDependencyError) as caught:
        run_model(model=model, output_dir=tmp_path / "o")

    assert plan.to_dict()["blockers"] == [
        {
            "reason": "engine_missing",
            "message": "no sfincs found",
            "hint": "Install SFINCS.",
        }
    ]
    assert caught.value.details["reason"] == "engine_missing"
    assert caught.value.hint == "Install SFINCS."
    assert not (tmp_path / "o").exists()


def test_a_model_that_does_not_write_netcdf_is_unsupported(
    tmp_path: Path, model: Path, engine: SfincsInstall
) -> None:
    text = (model / "sfincs.inp").read_text().replace("outputformat    = net", "")
    (model / "sfincs.inp").write_text(text, encoding="utf-8")

    with pytest.raises(UnsupportedError) as caught:
        run_model(model=model, output_dir=tmp_path / "run")

    assert caught.value.details["reason"] == "output_format"
