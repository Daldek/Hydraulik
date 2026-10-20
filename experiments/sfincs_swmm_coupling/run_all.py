"""Run every scenario in its own process (SFINCS keeps global state per process).

Usage: SFINCS_LIBRARY=/path/to/libsfincs.so python run_all.py [scenario ...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import case_setup as cs

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RESULTS = HERE / "results"


def main(names: list[str]) -> None:
    library = os.environ.get("SFINCS_LIBRARY")
    if not library or not Path(library).is_file():
        sys.exit("Set SFINCS_LIBRARY to the path of the compiled libsfincs.so")
    results = {}
    for name in names or list(cs.SCENARIOS):
        run_dir = RUNS / name
        print(f"--- running {name}: {cs.SCENARIOS[name].description}", flush=True)
        completed = subprocess.run(
            [sys.executable, str(HERE / "coupler.py"), name, str(run_dir), library],
            capture_output=True,
            text=True,
            check=False,  # a failed scenario is reported, the others still run
        )
        (RUNS / f"{name}.log").write_text(completed.stdout + completed.stderr)
        if completed.returncode != 0:
            print(f"    FAILED (exit {completed.returncode}), see {RUNS / name}.log")
            continue
        result = json.loads((run_dir / "result.json").read_text())
        results[name] = result
        print(
            f"    mass error {result['mass_error_pct_of_inflow']:+.4f} % | "
            f"exchanged {result['exchanged_total_m3']:.2f} m3 | "
            f"wall {result['wall_time_s']:.1f} s"
        )
    RESULTS.mkdir(exist_ok=True)
    summary = RESULTS / "summary.json"
    old = json.loads(summary.read_text()) if summary.exists() else {}
    old.update(results)
    summary.write_text(json.dumps(old, indent=2))


if __name__ == "__main__":
    RUNS.mkdir(exist_ok=True)
    main(sys.argv[1:])
