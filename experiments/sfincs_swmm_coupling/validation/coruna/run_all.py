"""Run A Coruna configurations, each in its own process (SFINCS global state).

Usage: SFINCS_LIBRARY=/path/to/libsfincs.so CORUNA_DATA=/path/to/dataset \
       python run_all.py [--workers N] [run ...]

Runs execute in parallel (default 4 workers), so the reported wall times
include the load of the other runs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import coruna_setup as cs

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RESULTS = HERE / "results"


def run_one(name: str, library: str) -> tuple[str, dict | None]:
    run_dir = RUNS / name
    completed = subprocess.run(
        [sys.executable, str(HERE / "run_coruna.py"), name, str(run_dir), library],
        capture_output=True,
        text=True,
        check=False,  # a failed run is reported, the others still run
        env={**os.environ, "OMP_NUM_THREADS": "1"},
    )
    (RUNS / f"{name}.log").write_text(completed.stdout + completed.stderr)
    if completed.returncode != 0:
        return name, None
    return name, json.loads((run_dir / "result.json").read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="*")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    library = os.environ.get("SFINCS_LIBRARY")
    if not library or not Path(library).is_file():
        sys.exit("Set SFINCS_LIBRARY to the path of the compiled libsfincs.so")
    cs.data_dir()  # fails early without CORUNA_DATA
    RUNS.mkdir(exist_ok=True)
    names = args.runs or list(cs.RUNS)
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name, result in pool.map(lambda n: run_one(n, library), names):
            if result is None:
                print(f"{name:12} FAILED, see {RUNS / name}.log", flush=True)
                continue
            results[name] = result
            print(
                f"{name:12} surface error {result['surface_side_error_m3'] * 1e3:+.4f} L"
                f" | network error {result['network_side_error_m3'] * 1e3:+.4f} L"
                f" | wall {result['wall_time_s']:.0f} s",
                flush=True,
            )
    RESULTS.mkdir(exist_ok=True)
    summary = RESULTS / "summary.json"
    old = json.loads(summary.read_text()) if summary.exists() else {}
    old.update(results)
    summary.write_text(json.dumps(old, indent=2))


if __name__ == "__main__":
    main()
