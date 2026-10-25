"""The tables of ``hydrolog route network`` as the inflow of a sewer, on the real SWMM.

The files come from the real Hydrolog command (``tests/fixtures/hydrolog``, see
``tests/unit/test_hydrolog_handoff.py``): the hydrograph that leaves each node of a
small river network. ``swmm run`` takes any of them as it is.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from hydraulik import run_network
from hydraulik.data.tables import read_hydrograph

pytest.importorskip("pyswmm")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NETWORK = FIXTURES / "swmm" / "network_chain.csv"
HYDROLOG = FIXTURES / "hydrolog"
NODES: list[dict[str, Any]] = json.loads((HYDROLOG / "result.json").read_text("utf-8"))[
    "nodes"
]


@pytest.mark.parametrize("node", NODES, ids=[n["id"] for n in NODES])
def test_the_table_of_any_node_runs_through_the_sewer_with_its_volume_and_peak(
    tmp_path: Path, node: dict[str, Any]
) -> None:
    table = HYDROLOG / "out" / f"{node['id']}.csv"

    document = run_network(
        network=NETWORK, inflow=table, inflow_node="J1", output_dir=tmp_path / "swmm"
    )

    body = document.to_dict()
    series = read_hydrograph(table)
    assert body["source"]["inflow"]["volume_m3"] == pytest.approx(node["volume_m3"])
    assert body["source"]["inflow"]["duration_s"] == series.times_s[-1]
    assert body["duration_s"] == series.times_s[-1] + 600.0  # ten minutes to drain
    totals = body["totals"]
    assert totals["external_inflow_m3"] == pytest.approx(node["volume_m3"], rel=0.01)
    assert totals["flooding_m3"] == 0.0  # the pipes carry 0.4 m3/s, the peak is 0.2
    assert totals["outflow_m3"] == pytest.approx(node["volume_m3"], rel=0.05)
    inlet = next(n for n in body["nodes"] if n["name"] == "J1")
    assert inlet["peak_inflow_m3s"] == pytest.approx(node["peak_m3s"], rel=0.02)
    assert document.notices == []
