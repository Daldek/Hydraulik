"""``model couple`` around a fake worker: refusals, staging, water books, notices."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("netCDF4")
pytest.importorskip("pyswmm")

from jsonschema import Draft202012Validator  # noqa: E402

from hydraulik import check_command, couple_model, run_command  # noqa: E402
from hydraulik.cli import main  # noqa: E402
from hydraulik.documents import CoupleDocument, PlanDocument  # noqa: E402
from hydraulik.engines.detect import EngineStatus  # noqa: E402
from hydraulik.engines.sfincs.inp import read_inp  # noqa: E402
from hydraulik.engines.sfincs.model import write_model  # noqa: E402
from hydraulik.engines.swmm import inp as swmm_inp  # noqa: E402
from hydraulik.exceptions import (  # noqa: E402
    ConflictError,
    EngineError,
    InvalidInputError,
    MissingDependencyError,
    UnsupportedError,
)

from ..synthetic import closed_basin, write_his, write_map  # noqa: E402

LIBRARY = "/fake/libsfincs.so"
NETWORK = (
    "name,x_m,y_m,rim_m,depth_m,to,diameter_m\n"
    "J1,55,55,0.0,2,OUT,0.3\n"
    "OUT,95,55,-1.0,2,,\n"
)
SEWER = """[TITLE]
user model
[OPTIONS]
FLOW_UNITS           CMS
FLOW_ROUTING         KINWAVE
START_DATE           06/01/2020
END_DATE             06/02/2020
ROUTING_STEP         30
[JUNCTIONS]
J1       -2.0 2.0 0 5 0
J2       -2.0 2.0 0 5 0
J3       -2.0 2.0 0 5 0
[OUTFALLS]
OUT      -3.0 FREE NO
[CONDUITS]
C1 J1 OUT 40 0.013 0 0 0 0
[XSECTIONS]
C1 CIRCULAR 0.3 0 0 0 1
[COORDINATES]
J1 55 55
J2 500 500
OUT 95 55
"""
SUMMARY: dict[str, Any] = {
    "intervals": 7200,
    "surface_time_s": 7200.0,
    "overshoot_s": {"mean": 0.1, "max": 0.5},
    "outfall_net_m3": 10.0,
    "outfall_gross_inflow_m3": 0.0,
    "surface_final_m3": 285.0,
    "network_final_m3": 5.0,
    "exchanged_m3": 15.0,
    "pending_m3": 0.0,
    "flooded_m3": 0.0,
    "outside": [],
    "nodes": [
        {
            "name": "J1",
            "cell": 55,
            "ground_m": 0.0,
            "exchanged_m3": 15.0,
            "flooded_m3": 0.0,
            "returned_m3": 0.0,
            "pending_m3": 0.0,
            "capped_steps": 0,
            "peak_exchange_m3s": 0.01,
            "peak_return_m3s": 0.0,
            "max_level_m": 0.03,
            "max_head_m": -1.5,
            "held_max_head_m": -1.5,
            "numerical_spike": False,
            "sign_flips": 0,
            "spill": {
                "total_m3": 0.0,
                "sustained_m3": 0.0,
                "sustained": False,
                "longest_s": 0.0,
            },
        }
    ],
    "swmm": {
        "duration_s": 7200.0,
        "external_inflow_m3": 15.0,
        "outflow_m3": 10.0,
        "flooding_m3": 0.0,
        "final_storage_m3": 5.0,
        "continuity_error_percent": -0.1,
        "nodes": [],
        "links": [],
    },
}


class Worker:
    """A stand-in for ``run_worker``: writes what the real one leaves in staging."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.summary: dict[str, Any] = json.loads(json.dumps(SUMMARY))
        self.depth_m = 0.0285  # 285 m3 on 100 cells of 100 m2: the books close
        self.outflow: np.ndarray[Any, Any] | None = None
        self.error: Exception | None = None
        self.seen: dict[str, Any] = {}

    def __call__(
        self,
        directory: Path,
        job: Path,
        *,
        timeout_s: float,
        threads: int | None = None,
    ) -> dict[str, Any]:
        self.seen = {
            "job": json.loads(job.read_text(encoding="utf-8")),
            "inp": read_inp(directory),
            "network": (directory / "network.inp").read_text(encoding="utf-8"),
            "directory": directory,
            "timeout_s": timeout_s,
            "threads": threads,
            "files": sorted(p.name for p in directory.iterdir()),
        }
        if self.error is not None:
            raise self.error
        write_map(
            directory / "sfincs_map.nc",
            rows=10,
            columns=10,
            x0=0.0,
            y0=0.0,
            dx=10.0,
            depth=np.full((10, 10), self.depth_m),
            outflow=self.outflow,
            rain_m=0.03,
            infiltration_m=0.0,
            end_time_s=7200.0,
            depth_time_s=7200.0,
        )
        write_his(directory / "sfincs_his.nc", names=("centre",), x=(55.0,), y=(55.0,))
        (directory / "sfincs.log").write_text("log\n", encoding="utf-8")
        (directory / "network.rpt").write_text("report\n", encoding="utf-8")
        (directory / "coupling.csv").write_text("time_s\n", encoding="utf-8")
        return self.summary


@pytest.fixture
def model(tmp_path: Path) -> Path:
    folder = tmp_path / "model"
    folder.mkdir()
    write_model(folder, closed_basin())
    return folder


@pytest.fixture
def network(tmp_path: Path) -> Path:
    path = tmp_path / "network.csv"
    path.write_text(NETWORK, encoding="utf-8")
    return path


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Worker:
    """Find a library and replace the process that would load it."""
    fake = Worker(tmp_path)
    status = EngineStatus("sfincs-library", True, "setting", LIBRARY, None, "fake")
    monkeypatch.setattr(
        "hydraulik.operations.couple.detect_sfincs_library", lambda settings: status
    )
    monkeypatch.setattr("hydraulik.coupling.process.run_worker", fake)
    return fake


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def couple(model: Path, network: Path, out: Path, **options: Any) -> CoupleDocument:
    document = couple_model(model=model, network=network, output_dir=out, **options)
    assert isinstance(document, CoupleDocument)
    return document


def test_a_coupled_run_publishes_its_files_and_books_the_water(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    before = names(model)
    out = tmp_path / "coupled"

    document = couple(model, network, out)

    assert names(out) == [
        "coupling.csv",
        "network.inp",
        "network.rpt",
        "sfincs.log",
        "sfincs_his.nc",
        "sfincs_map.nc",
    ]
    assert [f["status"] for f in document.files] == ["written"] * 6
    assert names(model) == before  # the model of the user is never touched
    balance = document.balance
    assert balance["rain_m3"] == pytest.approx(300.0)
    assert balance["total_error_m3"] == pytest.approx(0.0, abs=1e-3)
    assert balance["surface_side_error_m3"] == pytest.approx(0.0, abs=1e-3)
    assert balance["network_side_error_m3"] == pytest.approx(0.0, abs=1e-3)
    assert balance["flags"] == [] and balance["open_boundary"] is False
    assert document.surface["stations"][0]["name"] == "centre"
    assert document.coupling["intervals"] == 7200 and document.nodes[0]["name"] == "J1"
    assert document.notices == []
    seen = worker.seen
    assert seen["directory"].parent.name == ".hydraulik-incoming"
    assert not (out / ".hydraulik-incoming").exists()  # staging is gone
    assert "coupling-job.json" in seen["files"] and "sfincs.precip" in seen["files"]
    assert seen["inp"]["dtmax"] == "1.0"  # kept at most the exchange interval
    assert seen["timeout_s"] == 7200.0 and seen["threads"] is None


def test_the_document_validates_and_the_job_carries_the_defaults(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    from importlib import resources

    schema = json.loads(
        resources.files("hydraulik")
        .joinpath("schemas", "hydraulik-couple-1.schema.json")
        .read_text(encoding="utf-8")
    )

    document = couple(model, network, tmp_path / "coupled")

    Draft202012Validator(schema).validate(document.to_dict())
    job = worker.seen["job"]
    assert job["qext_unit"] == "m3s" and job["library"] == LIBRARY
    assert job["settings"]["interval_s"] == 1 and job["settings"]["relaxation"] == 1.0
    assert job["settings"]["mode"] == "swmm_flooding"
    assert job["settings"]["inlet"]["area_m2"] == pytest.approx(1.167)
    assert [n["name"] for n in job["nodes"]] == ["J1"]
    options = swmm_inp.options(worker.seen["network"])
    assert options["SURCHARGE_METHOD"] == "EXTRAN"
    assert options["ROUTING_STEP"] == "0.5" and options["VARIABLE_STEP"] == "0"


def test_the_coordinator_mode_relaxes_and_uses_the_slot_method(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    couple(model, network, tmp_path / "a", mode="coordinator", exchange_interval_s=2)

    job = worker.seen["job"]
    assert job["settings"]["relaxation"] == 0.1 and job["settings"]["interval_s"] == 2
    assert swmm_inp.options(worker.seen["network"])["SURCHARGE_METHOD"] == "SLOT"
    assert worker.seen["inp"]["dtmax"] == "2.0"
    surcharge = [
        j.surcharge_depth_m for j in swmm_inp.junctions(worker.seen["network"])
    ]
    assert surcharge == [100.0]  # the coordinator holds the water: no flooding


def test_a_balance_that_does_not_close_is_a_warning_that_names_the_unit(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    worker.summary["surface_final_m3"] = 270.0  # 15 m3 of the rain are nowhere

    document = couple(model, network, tmp_path / "coupled")

    assert document.balance["flags"] == ["balance_residual"]
    warning = document.notices[0]
    assert warning["code"] == "balance_residual" and warning["level"] == "warning"
    assert "sfincs.qext_unit" in warning["message"]
    assert document.balance["total_error_percent"] == pytest.approx(5.0)


def test_with_outflow_cells_a_positive_residual_is_the_water_that_left(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    worker.summary["surface_final_m3"] = 270.0
    worker.outflow = np.zeros((10, 10), dtype=bool)
    worker.outflow[0, 4:6] = True

    document = couple(model, network, tmp_path / "coupled")

    assert document.balance["open_boundary"] is True
    assert document.balance["flags"] == []  # the 15 m3 left over the outflow cells
    worker.summary["surface_final_m3"] = 330.0  # but a gain of water is an error
    again = couple(model, network, tmp_path / "again")
    assert again.balance["flags"] == ["balance_gain"]


def test_what_swmm_floods_out_of_nodes_without_a_cell_is_booked_as_lost(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    worker.summary["swmm"]["flooding_m3"] = 4.0
    worker.summary["network_final_m3"] = 1.0  # 4 m3 left the network by flooding

    document = couple(model, network, tmp_path / "coupled")

    assert document.balance["lost_flooding_m3"] == pytest.approx(4.0)
    assert abs(document.balance["network_side_error_m3"]) < 1e-3
    assert "flooding_lost" in [n["code"] for n in document.notices]


def test_oscillation_a_spike_a_cut_and_a_bad_continuity_error_are_reported(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    node = worker.summary["nodes"][0]
    node.update(sign_flips=30, numerical_spike=True, capped_steps=4)
    worker.summary["swmm"]["continuity_error_percent"] = 7.5

    document = couple(model, network, tmp_path / "coupled")

    codes = [n["code"] for n in document.notices]
    assert codes == [
        "continuity_error",
        "exchange_oscillation",
        "numerical_spike",
        "exchange_capped",
    ]


def test_nodes_off_the_domain_are_listed_and_a_network_without_any_is_refused(
    tmp_path: Path, model: Path, worker: Worker
) -> None:
    far = tmp_path / "far.csv"
    far.write_text(
        NETWORK.replace("J1,55,55", "J1,5500,55").replace("OUT,95,55", "OUT,95,55"),
        encoding="utf-8",
    )
    two = tmp_path / "two.csv"
    two.write_text(
        "name,x_m,y_m,rim_m,depth_m,to,diameter_m\n"
        "J1,55,55,0.0,2,J2,0.3\nJ2,5500,55,-0.5,2,OUT,0.3\nOUT,95,55,-1.0,2,,\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidInputError) as caught:
        couple_model(model=model, network=far, output_dir=tmp_path / "a")
    document = couple(model, two, tmp_path / "b")

    assert caught.value.details["reason"] == "no_exchange_nodes"
    assert not (tmp_path / "a").exists()
    assert [n["name"] for n in worker.seen["job"]["nodes"]] == ["J1"]
    assert document.coupling["nodes_outside"] == ["J2"]
    assert "nodes_outside_domain" in [n["code"] for n in document.notices]


def test_your_own_swmm_input_is_run_patched_and_the_copy_says_how(
    tmp_path: Path, model: Path, worker: Worker
) -> None:
    sewer = tmp_path / "sewer.inp"
    sewer.write_text(SEWER, encoding="utf-8")

    document = couple_model(model=model, inp=sewer, output_dir=tmp_path / "coupled")

    assert isinstance(document, CoupleDocument)
    text = worker.seen["network"]
    options = swmm_inp.options(text)
    assert options["FLOW_ROUTING"] == "DYNWAVE"
    assert (options["START_DATE"], options["START_TIME"]) == ("01/01/2000", "00:00:00")
    assert (options["END_DATE"], options["END_TIME"]) == ("01/01/2000", "02:00:00")
    assert options["ROUTING_STEP"] == "0.5" and options["VARIABLE_STEP"] == "0"
    assert options["MIN_SURFAREA"] == "1.167"
    assert {j.surcharge_depth_m for j in swmm_inp.junctions(text)} == {0.0}
    assert sewer.read_text(encoding="utf-8") == SEWER  # yours is untouched
    assert [n["name"] for n in worker.seen["job"]["nodes"]] == ["J1"]  # J2 is far away
    codes = [n["code"] for n in document.notices]
    assert "inp_patched" in codes and "nodes_outside_domain" in codes
    patched = next(n for n in document.notices if n["code"] == "inp_patched")
    assert "FLOW_ROUTING" in patched["message"] and "ROUTING_STEP" in patched["message"]
    assert "nodes_without_coordinates" in codes  # J3 has no [COORDINATES]


def test_the_coordinator_with_extran_in_your_input_is_a_warning(
    tmp_path: Path, model: Path, worker: Worker
) -> None:
    sewer = tmp_path / "sewer.inp"
    sewer.write_text(SEWER, encoding="utf-8")

    document = couple_model(
        model=model, inp=sewer, mode="coordinator", output_dir=tmp_path / "coupled"
    )

    assert isinstance(document, CoupleDocument)
    assert "coordinator_extran" in [n["code"] for n in document.notices]
    surcharge = [
        j.surcharge_depth_m for j in swmm_inp.junctions(worker.seen["network"])
    ]
    assert surcharge == [100.0, 100.0, 100.0]


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({}, "missing_option"),
        ({"network": "a.csv", "inp": "b.inp"}, "exclusive_options"),
        ({"inp": "b.inp", "surcharge_method": "SLOT"}, "option_not_applicable"),
        ({"network": "a.csv", "routing_step_s": 2.0}, "out_of_range"),
        ({"network": "a.csv", "exchange_interval_s": 0}, "out_of_range"),
    ],
)
def test_options_that_do_not_go_together_are_refused(
    tmp_path: Path, model: Path, options: dict[str, Any], reason: str
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        couple_model(model=model, output_dir=tmp_path / "out", **options)

    assert caught.value.details["reason"] == reason


def test_without_the_library_or_pyswmm_nothing_is_done(
    tmp_path: Path, model: Path, network: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "coupled"

    with pytest.raises(MissingDependencyError) as no_library:
        couple_model(model=model, network=network, output_dir=out)
    status = EngineStatus("sfincs-library", True, "setting", LIBRARY, None, "fake")
    monkeypatch.setattr(
        "hydraulik.operations.couple.detect_sfincs_library", lambda settings: status
    )
    monkeypatch.setattr(
        "hydraulik.operations._support.extra_found", lambda module: module != "pyswmm"
    )
    with pytest.raises(MissingDependencyError) as no_swmm:
        couple_model(model=model, network=network, output_dir=out)

    assert no_library.value.details["reason"] == "engine_missing"
    assert "--enable-shared" in str(no_library.value.hint)
    assert no_swmm.value.details["reason"] == "extra_missing"
    assert not out.exists()


def test_check_plans_the_run_and_names_what_is_missing(
    tmp_path: Path, model: Path, network: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "coupled"

    plan = check_command(
        "model couple", model=str(model), network=str(network), output_dir=str(out)
    )

    assert isinstance(plan, PlanDocument)
    assert [b["reason"] for b in plan.blockers] == ["engine_missing"]
    assert "1 of 1 node(s) on an active cell" in plan.steps[0]
    assert [t["name"] for t in plan.targets] == [
        "sfincs_map.nc",
        "sfincs_his.nc",
        "sfincs.log",
        "network.inp",
        "network.rpt",
        "coupling.csv",
    ]
    assert not out.exists()
    status = EngineStatus("sfincs-library", True, "setting", LIBRARY, None, "fake")
    monkeypatch.setattr(
        "hydraulik.operations.couple.detect_sfincs_library", lambda settings: status
    )
    ready = check_command(
        "model couple", model=str(model), network=str(network), output_dir=str(out)
    )
    assert isinstance(ready, PlanDocument) and ready.blockers == []


def test_a_failed_run_publishes_nothing_and_leaves_no_staging(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    worker.error = EngineError("SFINCS failed", reason="bmi_failed")
    out = tmp_path / "coupled"

    with pytest.raises(EngineError) as caught:
        couple_model(model=model, network=network, output_dir=out)

    assert caught.value.details["reason"] == "bmi_failed"
    assert list(out.iterdir()) == []


def test_existing_results_are_a_conflict_until_force(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    out = tmp_path / "coupled"
    couple(model, network, out)

    with pytest.raises(ConflictError) as caught:
        couple(model, network, out)
    again = couple(model, network, out, force=True)

    assert len(caught.value.details["paths"]) == 6
    assert {f["status"] for f in again.files} == {"replaced"}


def test_a_model_that_is_not_a_regular_grid_is_refused(
    tmp_path: Path, model: Path, network: Path, worker: Worker
) -> None:
    inp = model / "sfincs.inp"
    inp.write_text(inp.read_text() + "qtrfile = sfincs.qtr\n")

    with pytest.raises(UnsupportedError) as caught:
        couple_model(model=model, network=network, output_dir=tmp_path / "out")

    assert caught.value.details["reason"] == "model_layout"


def test_the_command_line_prints_one_envelope_and_the_catalog_runs_it(
    tmp_path: Path,
    model: Path,
    network: Path,
    worker: Worker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        [
            "model",
            "couple",
            "--model",
            str(model),
            "--network",
            str(network),
            "-o",
            str(tmp_path / "cli"),
            "--mode",
            "swmm_flooding",
            "--json",
        ]
    )

    envelope = json.loads(capsys.readouterr().out)
    assert code == 0 and envelope["result"]["schema"] == "hydraulik-couple/1"
    assert envelope["status"] == "ok"
    document = run_command(
        "model couple",
        model=str(model),
        network=str(network),
        output_dir=str(tmp_path / "api"),
    )
    assert document.to_dict()["schema"] == "hydraulik-couple/1"
