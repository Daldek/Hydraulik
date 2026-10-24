"""The coupling worker: real SWMM on a fake surface, and the process around it."""

import csv
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pyswmm")
pytest.importorskip("netCDF4")

from hydraulik.coupling.coupler import CouplerSettings, ExchangeNode  # noqa: E402
from hydraulik.coupling.process import run_worker  # noqa: E402
from hydraulik.coupling.worker import (  # noqa: E402
    RESULT_NAME,
    SERIES_COLUMNS,
    SERIES_NAME,
    CoupleJob,
    main,
    run_job,
)
from hydraulik.engines.swmm.network import (  # noqa: E402
    SwmmSettings,
    read_network_table,
    write_inp,
)
from hydraulik.exceptions import EngineError, HydraulikError  # noqa: E402

from ..coupling_fakes import FakeSurface  # noqa: E402
from ..synthetic import closed_basin  # noqa: E402

DURATION_S = 600


@pytest.fixture
def stage(tmp_path: Path) -> Path:
    """A directory with a SWMM input whose pipe is too small for the rain."""
    folder = tmp_path / "stage"
    folder.mkdir()
    table = folder / "net.csv"
    table.write_text(
        "name,x_m,y_m,rim_m,depth_m,to,diameter_m\n"
        "J1,2.5,2.5,10.0,0.5,OUT,0.05\n"
        "OUT,50,2.5,9.0,2.0,,\n",
        encoding="utf-8",
    )
    text = write_inp(read_network_table(table), SwmmSettings(float(DURATION_S)))
    (folder / "network.inp").write_text(text, encoding="utf-8")
    return folder


def job_for(stage: Path, **settings: Any) -> CoupleJob:
    return CoupleJob(
        library="libsfincs.so",
        qext_unit="m3s",
        directory=str(stage),
        inp=str(stage / "network.inp"),
        report=str(stage / "network.rpt"),
        out=str(stage / "network.out"),
        nodes=(ExchangeNode("J1", 2.5, 2.5),),
        settings=CouplerSettings(interval_s=5, **settings),
    )


def test_a_pipe_that_is_too_small_floods_and_the_water_is_booked_on_both_sides(
    stage: Path,
) -> None:
    surface = FakeSurface(
        [10.0], cell_m=5.0, rain_mm_h=1000.0, end_s=float(DURATION_S), step_s=1.0
    )

    summary = run_job(job_for(stage), surface=surface)

    node = summary["nodes"][0]
    swmm = summary["swmm"]
    assert summary["intervals"] == DURATION_S // 5
    assert node["flooded_m3"] > 0.0 and node["returned_m3"] > 0.0
    assert node["returned_m3"] + node["pending_m3"] == pytest.approx(
        node["flooded_m3"], abs=1e-9
    )
    assert surface.created_m3 == 0.0
    # the surface side closes exactly, the network side to SWMM's own continuity error
    assert surface.rain_m3 - summary["surface_final_m3"] == pytest.approx(
        summary["exchanged_m3"], abs=1e-9
    )
    network_error = (
        summary["exchanged_m3"]
        - summary["pending_m3"]
        - summary["network_final_m3"]
        - summary["outfall_net_m3"]
    )
    assert abs(network_error) < 0.01 * swmm["external_inflow_m3"]
    assert abs(swmm["continuity_error_percent"]) < 1.0
    assert (stage / "network.rpt").is_file()
    assert summary["outside"] == [] and node["name"] == "J1"


def test_the_series_has_a_row_for_every_interval_and_node(stage: Path) -> None:
    surface = FakeSurface(
        [10.0], cell_m=5.0, rain_mm_h=1000.0, end_s=float(DURATION_S), step_s=1.0
    )

    run_job(job_for(stage), surface=surface)

    with (stage / SERIES_NAME).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0]) == SERIES_COLUMNS
    assert len(rows) == DURATION_S // 5
    assert {row["node"] for row in rows} == {"J1"}
    assert float(rows[-1]["time_s"]) == DURATION_S
    assert all(float(row["zs_m"]) >= 10.0 for row in rows)  # the bed of the cell


def test_a_job_survives_its_file_and_a_damaged_file_is_named(tmp_path: Path) -> None:
    job = job_for(tmp_path, mode="coordinator", relaxation=0.2)
    path = tmp_path / "job.json"
    path.write_text(job.to_json(), encoding="utf-8")

    assert CoupleJob.read(path) == job
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(HydraulikError) as caught:
        CoupleJob.read(path)
    assert caught.value.details["reason"] == "invalid_job"


def test_the_worker_leaves_the_error_document_when_it_fails(tmp_path: Path) -> None:
    job = tmp_path / "job.json"
    job.write_text("[]", encoding="utf-8")

    code = main([str(job)])

    body = json.loads((tmp_path / RESULT_NAME).read_text(encoding="utf-8"))
    assert code == 1 and body["status"] == "error"
    assert body["error"]["code"] == "data_error"
    assert body["error"]["details"]["reason"] == "invalid_job"
    assert main([]) == 2  # a call without a job is a usage error


def model_stage(tmp_path: Path, stage: Path) -> CoupleJob:
    """A stage with a real model and SWMM input, and a library that does not exist."""
    from hydraulik.engines.sfincs.model import write_model

    write_model(stage, closed_basin())
    return CoupleJob(
        library=str(tmp_path / "no-such-libsfincs.so"),
        qext_unit="m3s",
        directory=str(stage),
        inp=str(stage / "network.inp"),
        report=str(stage / "network.rpt"),
        out=str(stage / "network.out"),
        nodes=(ExchangeNode("J1", 2.5, 2.5),),
        settings=CouplerSettings(),
    )


def test_the_parent_gets_the_error_of_the_worker_with_its_code_and_details(
    tmp_path: Path, stage: Path
) -> None:
    job = stage / "job.json"
    job.write_text(model_stage(tmp_path, stage).to_json(), encoding="utf-8")

    with pytest.raises(EngineError) as caught:
        run_worker(stage, job, timeout_s=120.0)

    assert caught.value.code == "calculation_error"
    assert caught.value.details["reason"] == "engine_unavailable"
    assert "--enable-shared" in str(caught.value.hint)
    assert (stage / "coupling.log").is_file()  # the output of the process stays there


def test_a_worker_that_is_too_slow_is_stopped_with_the_end_of_its_output(
    tmp_path: Path, stage: Path
) -> None:
    job = stage / "job.json"
    job.write_text(model_stage(tmp_path, stage).to_json(), encoding="utf-8")

    with pytest.raises(EngineError) as caught:
        run_worker(stage, job, timeout_s=0.001)

    assert caught.value.details["reason"] == "engine_timeout"
    assert "log_tail" in caught.value.details


def test_a_worker_that_leaves_no_result_is_an_engine_failure(
    tmp_path: Path, stage: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "job.json").write_text("[]", encoding="utf-8")  # its result lands here

    with pytest.raises(EngineError) as caught:
        run_worker(stage, elsewhere / "job.json", timeout_s=120.0)

    assert caught.value.details["reason"] == "engine_failed"
    assert caught.value.details["returncode"] == 1
