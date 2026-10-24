"""Running SFINCS: progress, failure, timeout, threads and the Docker command."""

import os
import sys
import time
from pathlib import Path

import pytest

from hydraulik.engines.detect import SfincsInstall
from hydraulik.engines.sfincs.run import run_sfincs
from hydraulik.exceptions import EngineError, InvalidInputError

from ..synthetic import fake_docker, fake_sfincs, write_map


@pytest.fixture
def model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A model directory (only ``sfincs.inp``) and the map the fake program writes."""
    directory = tmp_path / "model"
    directory.mkdir()
    (directory / "sfincs.inp").write_text("mmax = 1\n", encoding="utf-8")
    write_map(tmp_path / "result.nc")
    monkeypatch.setenv("FAKE_SFINCS_MAP", str(tmp_path / "result.nc"))
    return directory


def test_a_finished_run_reports_its_progress_and_leaves_the_results_in_place(
    tmp_path: Path, model: Path
) -> None:
    seen: list[int] = []

    info = run_sfincs(fake_sfincs(tmp_path), model, timeout_s=60, progress=seen.append)

    assert seen == [0, 50, 100]
    assert (info.kind, info.returncode) == ("exe", 0)
    assert "100% complete" in info.log_tail
    assert (model / "sfincs_map.nc").is_file()


def test_a_failed_run_carries_the_error_line_of_sfincs_and_the_end_of_its_log(
    tmp_path: Path, model: Path
) -> None:
    (model / "mode.txt").write_text("fail", encoding="utf-8")

    with pytest.raises(EngineError) as caught:
        run_sfincs(fake_sfincs(tmp_path), model, timeout_s=60)

    error = caught.value
    assert error.code == "calculation_error"
    assert error.details["reason"] == "engine_failed"
    assert error.details["returncode"] == 2
    assert 'prcp file "sfincs.precip" not found' in str(error)
    assert "0% complete" in error.details["log_tail"]


def test_a_run_that_exceeds_the_timeout_is_stopped_and_says_so(
    tmp_path: Path, model: Path
) -> None:
    (model / "mode.txt").write_text("hang", encoding="utf-8")
    started = time.monotonic()

    with pytest.raises(EngineError) as caught:
        run_sfincs(fake_sfincs(tmp_path), model, timeout_s=0.5)

    assert caught.value.details["reason"] == "engine_timeout"
    assert caught.value.details["timeout_s"] == 0.5
    assert time.monotonic() - started < 30  # the sleeping program was killed


def test_threads_become_omp_num_threads_and_the_program_runs_in_the_directory(
    tmp_path: Path, model: Path
) -> None:
    run_sfincs(fake_sfincs(tmp_path), model, timeout_s=60, threads=3)

    threads, working = (model / "seen.txt").read_text().split("|")
    assert threads == "3"
    assert Path(working).resolve() == model.resolve()


def test_an_unstartable_program_is_an_engine_error_not_a_traceback(
    tmp_path: Path,
) -> None:
    install = SfincsInstall("exe", (str(tmp_path / "no-such-program"),))

    with pytest.raises(EngineError) as caught:
        run_sfincs(install, tmp_path, timeout_s=5)

    assert caught.value.details["reason"] == "engine_unavailable"


def test_docker_mounts_the_directory_and_runs_as_the_caller(
    tmp_path: Path, model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "docker.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))

    info = run_sfincs(fake_docker(tmp_path), model, timeout_s=60, threads=2)

    words = log.read_text().split()
    assert words[:3] == ["run", "--rm", "--name"]
    assert words[3].startswith("hydraulik-sfincs-")
    assert words[4:6] == ["-v", f"{model.resolve()}:/data"]
    if hasattr(os, "getuid"):
        assert words[6:8] == ["--user", f"{os.getuid()}:{os.getgid()}"]
    assert words[-3:-1] == ["-e", "OMP_NUM_THREADS=2"]
    assert words[-1] == "deltares/sfincs-cpu:sfincs-v2.4.1"
    assert info.kind == "docker"


@pytest.mark.skipif(sys.platform == "win32", reason="the fake program sleeps")
def test_a_container_that_outlives_the_timeout_is_killed_by_name(
    tmp_path: Path, model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "docker.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    monkeypatch.setenv("FAKE_DOCKER_HANG", "1")

    with pytest.raises(EngineError) as caught:
        run_sfincs(fake_docker(tmp_path), model, timeout_s=0.5)

    started, killed = log.read_text().splitlines()[:2]
    name = started.split()[3]
    assert killed == f"kill {name}"
    assert caught.value.details["reason"] == "engine_timeout"


def test_a_docker_install_without_an_image_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError):
        run_sfincs(SfincsInstall("docker", ("docker",)), tmp_path, timeout_s=5)
