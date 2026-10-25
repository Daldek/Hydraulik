"""Starting the coupling worker and reading what it left (ADR-0005).

The parent side of :mod:`hydraulik.coupling.worker`: it starts ``python -m
hydraulik.coupling.worker JOB`` in the staging directory with the output of the process
in a file (SFINCS prints to the standard output of its process, which must never reach
the JSON of the command), waits for it with a timeout, stops it when the caller is
interrupted or terminated, and turns its ``coupling.json`` into a summary or an error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any, Final

from hydraulik.coupling.worker import RESULT_NAME
from hydraulik.exceptions import EngineError, rebuild_error

__all__ = ["LOG_NAME", "LOG_TAIL_LINES", "run_worker"]

LOG_NAME: Final = "coupling.log"
"""The output of the worker process, in the job directory (staging, never published)."""

LOG_TAIL_LINES: Final = 40
"""Lines of that output an error of the run carries."""

_STOP_GRACE_S: Final = 5.0


def _tail(path: Path) -> str:
    """Return the last lines of the worker's output."""
    if not path.is_file():
        return ""
    with path.open(encoding="utf-8", errors="replace") as handle:
        return "\n".join(line.rstrip("\r\n") for line in deque(handle, LOG_TAIL_LINES))


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Stop the worker and wait for it."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=_STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_worker(
    directory: Path, job: Path, *, timeout_s: float, threads: int | None = None
) -> dict[str, Any]:
    """Run the coupling worker on a job and return its summary.

    Parameters
    ----------
    directory : Path
        The job directory (staging): the process runs there, and ``coupling.json`` and
        :data:`LOG_NAME` appear there.
    job : Path
        The job file (:meth:`hydraulik.coupling.worker.CoupleJob.to_json`).
    timeout_s : float
        Seconds the run may take; the process is stopped after that.
    threads : int or None, optional
        OpenMP threads of SFINCS (``OMP_NUM_THREADS``); all cores when ``None``.

    Returns
    -------
    dict
        The summary of ``coupling.json`` of a run that finished.

    Raises
    ------
    HydraulikError
        The error the worker reported, with its code, details and hint.
    EngineError
        If the process cannot be started (reason ``engine_unavailable``), exceeds the
        timeout (``engine_timeout``), or ends without a usable result
        (``engine_failed``); ``details.log_tail`` carries the end of its output.
    KeyboardInterrupt, TerminatedError
        Re-raised after the process was stopped.
    """
    log = directory / LOG_NAME
    result = directory / RESULT_NAME
    environment = dict(os.environ)
    if threads is not None:
        environment["OMP_NUM_THREADS"] = str(threads)
    command = [sys.executable, "-m", "hydraulik.coupling.worker", str(job)]
    with log.open("wb") as output:
        try:
            process = subprocess.Popen(  # noqa: S603 - our own module
                command,
                cwd=directory,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            raise EngineError(
                f"the coupling process could not be started: {exc}",
                details={"command": command[:3]},
                reason="engine_unavailable",
            ) from exc
        try:
            code = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _stop(process)
            raise EngineError(
                f"the coupled run did not finish within {timeout_s:g} s: stopped",
                details={"timeout_s": timeout_s, "log_tail": _tail(log)},
                hint="Raise sfincs.timeout_s (HYDRAULIK_SFINCS_TIMEOUT_S), or coarsen "
                "the model.",
                reason="engine_timeout",
            ) from None
        except BaseException:
            _stop(process)
            raise
    try:
        body: dict[str, Any] = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        body = {}
    if body.get("status") == "ok" and code == 0:
        return body
    error = body.get("error")
    if body.get("status") == "error" and isinstance(error, dict):
        raise rebuild_error(
            str(error.get("code", "internal_error")),
            str(error.get("message", "the coupled run failed")),
            details=error.get("details"),
            hint=error.get("hint"),
        )
    raise EngineError(
        f"the coupling process ended with code {code} and left no result",
        details={"returncode": code, "log_tail": _tail(log)},
        hint="Read details.log_tail; the SFINCS library may have crashed.",
        reason="engine_failed",
    )
