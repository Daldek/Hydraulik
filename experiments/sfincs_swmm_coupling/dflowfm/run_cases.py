"""Build and run the D-Flow FM cases, recording wall time and completion.

The GNU build of D-Flow FM used here crashes while freeing memory after the
run (ec_filereader.F90, segfault in flowfinalize); the outputs are complete by
then. A run therefore counts as finished when its map file reaches tStop.

Usage: DFLOWFM_RUNNER=/path/to/run_dflowfm.sh python run_cases.py [scenario ...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import netCDF4

from build_case import build

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
SCENARIOS = ["DQ0", "DQ1", "DQ2", "DQ3", "DQ1_inlet", "DQ2_inlet", "DQ3_inlet"]


def map_end_time(run_dir: Path) -> float:
    path = run_dir / "DFM_OUTPUT_case" / "case_map.nc"
    if not path.exists():
        return float("nan")
    with netCDF4.Dataset(path) as dataset:
        return float(dataset["time"][-1])


def main(names: list[str]) -> None:
    runner = os.environ.get("DFLOWFM_RUNNER")
    if not runner or not Path(runner).is_file():
        sys.exit("Set DFLOWFM_RUNNER to the run_dflowfm.sh of the D-Flow FM build")
    timings = {}
    for name in names or SCENARIOS:
        run_dir = RUNS / name
        mdu = build(name, run_dir)
        start = time.perf_counter()
        completed = subprocess.run(
            [runner, "--autostartstop", mdu.name],
            cwd=run_dir,
            capture_output=True,
            text=True,
            check=False,  # see module docstring: exit code is not reliable
            env={**os.environ, "OMP_NUM_THREADS": "1"},
        )
        wall = time.perf_counter() - start
        (run_dir / "run.log").write_text(completed.stdout + completed.stderr)
        end = map_end_time(run_dir)
        timings[name] = {
            "wall_time_s": wall,
            "exit_code": completed.returncode,
            "map_end_s": end,
        }
        print(
            f"{name:10} exit {completed.returncode:4d}  map until {end:7.1f} s  wall {wall:6.1f} s"
        )
    out = HERE / "results" / "timings.json"
    out.parent.mkdir(exist_ok=True)
    old = json.loads(out.read_text()) if out.exists() else {}
    old.update(timings)
    out.write_text(json.dumps(old, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
