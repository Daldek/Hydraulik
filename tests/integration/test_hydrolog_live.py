"""The real ``hydrolog route network`` still writes the tables of the fixture (live).

Put a Hydrolog that has ``route network`` first on ``PATH`` (the release after v0.7.0,
or a checkout with ``feature/routing-network``) and run ``pytest -m live``. ``uv run``
puts the environment of this project first and its Hydrolog is v0.7.0, which has no
``route network`` (the test then skips): call ``.venv/bin/python -m pytest`` with the
``PATH`` set. The command runs on the network document and the inflows of
``tests/fixtures/hydrolog``; every table it writes must be the table of the fixture: the
same header, the same times and the same discharges. When Hydrolog changes its numbers
on purpose, make the fixture again with the command of ``result.json`` and record the
Hydrolog commit there.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from hydraulik.data.tables import read_hydrograph

HYDROLOG = shutil.which("hydrolog")
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrolog"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        HYDROLOG is None, reason="put hydrolog on PATH to run this test"
    ),
]


def test_the_tables_that_hydrolog_writes_today_are_the_tables_of_the_fixture(
    tmp_path: Path,
) -> None:
    assert HYDROLOG is not None
    arguments = [
        HYDROLOG,
        "route",
        "network",
        "--network-file",
        str(FIXTURE / "network.json"),
        "--inflows-file",
        str(FIXTURE / "inflows.csv"),
    ]
    if subprocess.run([*arguments[:3], "--help"], capture_output=True).returncode:
        pytest.skip("this Hydrolog has no `route network`")

    done = subprocess.run(
        [*arguments, "--output-dir", str(tmp_path / "out"), "--json", "--lang", "en"],
        capture_output=True,
        text=True,
    )

    assert done.returncode == 0, done.stderr
    expected = sorted(p.name for p in (FIXTURE / "out").glob("*.csv"))
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == expected
    for name in expected:
        table = tmp_path / "out" / name
        assert table.read_text("utf-8").splitlines()[0] == "time_min,discharge_m3s"
        made, kept = read_hydrograph(table), read_hydrograph(FIXTURE / "out" / name)
        assert made.times_s == kept.times_s, name
        assert made.discharge_m3s == pytest.approx(kept.discharge_m3s, rel=1e-9), name
