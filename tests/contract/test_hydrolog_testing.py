"""What ``hydrolog.testing`` builds is what Hydraulik reads (DEV-10.6).

The files that Hydraulik takes from Hydrolog are the hydrograph tables of ``route
network --output-dir`` and the ``precip hietogram`` envelope. Hydrolog builds both with
its own code (``hydrolog.testing``), so these tests read the builders' output with
Hydraulik's readers and compare it with the recorded real output of ``tests/fixtures``
(the fixtures stay: they prove what one Hydrolog commit wrote). A change of a format of
Hydrolog breaks these tests when the pin of the ``rainfall`` extra moves to it, not at
a user.

The Hydrolog that the extra pins (v0.7.0) has no ``hydrolog.testing``; the module skips
until the pin moves to the routing release (``docs/PROGRESS.md``). To run it before, put
a Hydrolog checkout of ``feature/routing-network`` first on ``PYTHONPATH``.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from hydraulik import build_rainfall
from hydraulik.data.rainfall import read_hietogram_document
from hydraulik.data.tables import read_hydrograph, read_rain_table

testing = pytest.importorskip(
    "hydrolog.testing",
    reason="the pinned Hydrolog (v0.7.0) has no hydrolog.testing; bump the pin",
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RECORDED = FIXTURES / "hydrolog"
RECORD: dict[str, Any] = json.loads((RECORDED / "result.json").read_text("utf-8"))
HIETOGRAM = FIXTURES / "rain" / "hietogram_euler_ii.json"


def test_the_case_that_hydrolog_builds_is_the_one_that_was_recorded(
    tmp_path: Path,
) -> None:
    case = testing.build_network_fixture(tmp_path / "case")

    assert json.loads(case.network_file.read_text("utf-8")) == json.loads(
        (RECORDED / "network.json").read_text("utf-8")
    )
    assert case.inflows_file.read_bytes() == (RECORDED / "inflows.csv").read_bytes()
    assert list(case.nodes) == RECORD["order"]
    for node in case.nodes:
        built = (case.output_dir / f"{node}.csv").read_bytes()
        assert built == (RECORDED / "out" / f"{node}.csv").read_bytes(), node


@pytest.mark.parametrize(
    "node", RECORD["nodes"], ids=[n["id"] for n in RECORD["nodes"]]
)
def test_a_built_table_has_the_peak_the_time_and_the_volume_the_record_gives(
    tmp_path: Path, node: dict[str, Any]
) -> None:
    case = testing.build_network_fixture(tmp_path / "case")

    series = read_hydrograph(case.output_dir / f"{node['id']}.csv")

    peak = max(series.discharge_m3s)
    assert peak == node["peak_m3s"]
    assert (
        series.times_s[series.discharge_m3s.index(peak)] / 60.0
        == (node["time_to_peak_min"])
    )
    assert series.volume_m3 == pytest.approx(node["volume_m3"], rel=1e-12)


def test_the_table_of_a_routed_network_keeps_the_volume_of_its_sources(
    tmp_path: Path,
) -> None:
    times = [0, 10, 20, 30, 40, 50]
    network = testing.network_document(
        testing.subcatchment(
            "A", times_min=times, discharge_m3s=[0, 0.4, 1.6, 0.9, 0.3, 0]
        ),
        testing.reach("R", "A", method="lag", lag_min=25),
        testing.outlet("R"),
    )

    files = testing.write_network_tables(tmp_path / "out", network)

    assert [p.name for p in files] == ["A.csv", "R.csv", "OUT.csv"]
    source, routed = (read_hydrograph(tmp_path / "out" / f"{n}.csv") for n in "AR")
    assert routed.volume_m3 == pytest.approx(source.volume_m3, rel=1e-9)
    assert routed.times_s[0] == 0.0
    assert routed.times_s[-1] > source.times_s[-1]  # the reach extends the time axis
    assert routed.at(routed.times_s[-1] + 1.0) == 0.0


def test_the_envelope_that_hydrolog_builds_gives_the_rain_that_was_recorded(
    tmp_path: Path,
) -> None:
    built = testing.write_hietogram_envelope(tmp_path / "built.json")

    made, recorded = read_hietogram_document(built), read_hietogram_document(HIETOGRAM)

    assert made == recorded
    assert made.hietogram_type == "euler_ii"


def test_a_built_envelope_is_converted_into_the_rain_table_of_its_shape(
    tmp_path: Path,
) -> None:
    path = testing.write_hietogram_envelope(
        tmp_path / "block.json",
        hietogram_type="block",
        total_mm=30.0,
        duration_min=45.0,
        timestep_min=5.0,
    )

    document = build_rainfall(hietogram=path, output=tmp_path / "rain.csv")

    body = document.to_dict()
    table = read_rain_table(tmp_path / "rain.csv")
    assert (body["source"], body["hietogram_type"]) == ("hietogram", "block")
    assert (body["timestep_min"], body["n_steps"]) == (5.0, 9)
    assert table.total_mm == pytest.approx(30.0)
    assert table.depth_mm == pytest.approx((30.0 / 9,) * 9)


def test_the_result_of_a_built_envelope_alone_is_as_good_as_the_envelope(
    tmp_path: Path,
) -> None:
    envelope = testing.hietogram_envelope(hietogram_type="triangular", total_mm=20.0)
    (tmp_path / "result.json").write_text(json.dumps(envelope["result"]), "utf-8")
    (tmp_path / "envelope.json").write_text(json.dumps(envelope), "utf-8")

    assert read_hietogram_document(tmp_path / "result.json") == read_hietogram_document(
        tmp_path / "envelope.json"
    )
