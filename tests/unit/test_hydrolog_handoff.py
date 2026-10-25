"""The hydrograph tables of ``hydrolog route network`` are read as they are.

``tests/fixtures/hydrolog`` holds a network document, its inflows and the files that the
real command wrote from them (Hydrolog ``feature/routing-network``, commit 081fda2,
``hydrolog route network --network-file network.json --inflows-file inflows.csv
--output-dir out``). ``result.json`` is the result of that run without its machine
paths: the peak, the time to the peak and the volume that Hydrolog gives for every node,
and the SHA-256 of every file. Nothing of it was edited by hand.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hydraulik.data.tables import read_hydrograph

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrolog"
RECORD: dict[str, Any] = json.loads((FIXTURE / "result.json").read_text("utf-8"))
NODES = [node["id"] for node in RECORD["nodes"]]


def test_the_fixture_files_are_the_bytes_that_hydrolog_wrote() -> None:
    assert [f["name"] for f in RECORD["files"]] == [f"{node}.csv" for node in NODES]
    for entry in RECORD["files"]:
        data = (FIXTURE / "out" / entry["name"]).read_bytes()
        assert len(data) == entry["size_bytes"], entry["name"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["name"]


@pytest.mark.parametrize("node", RECORD["nodes"], ids=NODES)
def test_a_node_table_has_the_peak_the_time_and_the_volume_that_hydrolog_reports(
    node: dict[str, Any],
) -> None:
    series = read_hydrograph(FIXTURE / "out" / f"{node['id']}.csv")

    peak = max(series.discharge_m3s)
    assert peak == node["peak_m3s"]
    at_peak = series.times_s[series.discharge_m3s.index(peak)]
    assert at_peak / 60.0 == node["time_to_peak_min"]
    assert series.volume_m3 == pytest.approx(node["volume_m3"], rel=1e-12)
    assert series.times_s[0] == 0.0


def test_the_tail_of_a_routed_table_is_read_with_its_exponent_notation() -> None:
    text = (FIXTURE / "out" / "OUT.csv").read_text("utf-8")
    series = read_hydrograph(FIXTURE / "out" / "OUT.csv")

    assert "e-05" in text  # Hydrolog writes the settling tail as 6.29...e-05
    assert 0.0 < series.discharge_m3s[-1] < 1e-4
    assert series.at(series.times_s[-1] + 1.0) == 0.0  # nothing is held after the end
