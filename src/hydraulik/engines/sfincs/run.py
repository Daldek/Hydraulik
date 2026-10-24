"""Running SFINCS on a model directory (ADR-0003).

The engine is the executable or the Docker image that
:func:`hydraulik.engines.detect.detect_sfincs` found. SFINCS reads ``sfincs.inp`` from
its working directory and writes its results there, so :func:`run_sfincs` runs in the
directory it is given and the caller decides what that directory is (the staging
directory of :class:`hydraulik.output.Writer`, so nothing reaches the output
directory before the run has succeeded).

The output of the program is streamed: the percentage that SFINCS prints is passed
to ``progress``, the last lines are kept for the error of a failed run, and the run is
stopped when it exceeds the timeout, when the caller is interrupted or terminated.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hydraulik.engines.detect import SfincsInstall
from hydraulik.exceptions import EngineError, InvalidInputError

__all__ = ["LOG_TAIL_LINES", "SfincsRunInfo", "run_sfincs"]

logger = logging.getLogger(__name__)

LOG_TAIL_LINES: Final = 40
"""Number of lines of the program output that an error of the run carries."""

_PROGRESS = re.compile(r"^\s*(\d+)% complete")
_ERROR_LINE = re.compile(r"^\s*(Error|ERROR)\s*:\s*(?P<message>.+)$")
_STOP_GRACE_S: Final = 5.0


@dataclass(frozen=True)
class SfincsRunInfo:
    """What a finished run reports.

    Attributes
    ----------
    kind : {"exe", "docker"}
        How SFINCS was started.
    returncode : int
        Exit code of the program (0 for a run that finished).
    elapsed_s : float
        Wall time of the run [s].
    log_tail : str
        The last lines of the program output.
    """

    kind: str
    returncode: int
    elapsed_s: float
    log_tail: str


def _container_user() -> list[str]:
    """Return ``--user uid:gid`` so that the files of the run belong to the caller."""
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:  # Windows: Docker Desktop maps the owner
        return []
    return ["--user", f"{getuid()}:{getgid()}"]


def _command(
    install: SfincsInstall, directory: Path, threads: int | None, container: str
) -> list[str]:
    """Return the command line that runs SFINCS on ``directory``."""
    if install.kind == "exe":
        return list(install.command)
    if not install.image:
        raise InvalidInputError(
            "a Docker install of SFINCS needs an image",
            details={"option": "sfincs.image"},
            reason="image_missing",
        )
    command = [*install.command, "run", "--rm", "--name", container]
    command += ["-v", f"{directory}:/data", *_container_user()]
    if threads is not None:
        command += ["-e", f"OMP_NUM_THREADS={threads}"]
    command.append(install.image)
    return command


def _stop(
    process: subprocess.Popen[str], install: SfincsInstall, container: str
) -> None:
    """Stop the program and, for Docker, the container that outlives its client."""
    if install.kind == "docker":
        try:
            subprocess.run(
                [*install.command, "kill", container],
                capture_output=True,
                check=False,
                timeout=_STOP_GRACE_S * 2,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.warning("could not kill the container %s", container)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=_STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _reason_line(tail: deque[str]) -> str | None:
    """Return the text of the last ``Error :`` line of the program output."""
    for line in reversed(tail):
        found = _ERROR_LINE.match(line)
        if found:
            return found["message"].strip()
    return None


def run_sfincs(
    install: SfincsInstall,
    directory: str | Path,
    *,
    timeout_s: float,
    threads: int | None = None,
    progress: Callable[[int], None] | None = None,
) -> SfincsRunInfo:
    """Run SFINCS on a model directory and wait for it.

    Parameters
    ----------
    install : SfincsInstall
        The engine: an executable or a Docker image (``detect_sfincs``). A ``command``
        of several words is run as given, so a launcher can be part of it.
    directory : str or Path
        The model directory with ``sfincs.inp``; SFINCS writes its results into it.
    timeout_s : float
        Seconds the run may take; the program (and the container) is stopped after
        that and the run fails.
    threads : int or None, optional
        OpenMP threads (``OMP_NUM_THREADS``); all cores when ``None``.
    progress : callable or None, optional
        Called with the percentage (0 to 100) each time SFINCS prints it.

    Returns
    -------
    SfincsRunInfo
        The exit code, the wall time and the end of the output of a run that finished
        with exit code 0.

    Raises
    ------
    EngineError
        If the program cannot be started (reason ``engine_unavailable``), exits with a
        non-zero code (``engine_failed``; the message is the ``Error :`` line of
        SFINCS) or exceeds ``timeout_s`` (``engine_timeout``). ``details.log_tail``
        carries the end of the output.
    KeyboardInterrupt, TerminatedError
        Re-raised after the program was stopped.

    Examples
    --------
    >>> import sys, tempfile
    >>> install = SfincsInstall("exe", (sys.executable, "-c", "print('50% complete')"))
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     run_sfincs(install, tmp, timeout_s=30).returncode
    0
    """
    folder = Path(directory).resolve()
    container = f"hydraulik-sfincs-{secrets.token_hex(4)}"
    command = _command(install, folder, threads, container)
    environment = dict(os.environ)
    if threads is not None:
        environment["OMP_NUM_THREADS"] = str(threads)
    logger.info("running SFINCS (%s) in %s", install.kind, folder)
    started = time.monotonic()
    try:
        process = subprocess.Popen(  # noqa: S603 - the program is the detected engine
            command,
            cwd=folder,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        raise EngineError(
            f"SFINCS could not be started: {exc}",
            details={"command": command[:1], "kind": install.kind},
            hint="Check `hydraulik engines check` and the permissions of the program.",
            reason="engine_unavailable",
        ) from exc
    tail: deque[str] = deque(maxlen=LOG_TAIL_LINES)

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            tail.append(line.rstrip("\r\n"))
            found = _PROGRESS.match(line)
            if found and progress is not None:
                progress(int(found[1]))

    reader = threading.Thread(target=pump, name="sfincs-output", daemon=True)
    reader.start()
    try:
        returncode = process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _stop(process, install, container)
        reader.join(_STOP_GRACE_S)
        raise EngineError(
            f"SFINCS did not finish within {timeout_s:g} s and was stopped",
            details={"timeout_s": timeout_s, "log_tail": "\n".join(tail)},
            hint="Raise sfincs.timeout_s (HYDRAULIK_SFINCS_TIMEOUT_S) or coarsen it.",
            reason="engine_timeout",
        ) from None
    except BaseException:
        _stop(process, install, container)
        raise
    reader.join(_STOP_GRACE_S)
    elapsed = time.monotonic() - started
    log_tail = "\n".join(tail)
    if returncode != 0:
        raise EngineError(
            _reason_line(tail) or f"SFINCS exited with code {returncode}",
            details={
                "returncode": returncode,
                "kind": install.kind,
                "log_tail": log_tail,
            },
            hint="Read details.log_tail; sfincs.log in the directory has all of it.",
            reason="engine_failed",
        )
    return SfincsRunInfo(install.kind, returncode, elapsed, log_tail)
