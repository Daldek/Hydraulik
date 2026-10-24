"""``model run``: run SFINCS on a model directory and read what it computed."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from hydraulik.documents import PlanDocument, RunDocument
from hydraulik.engines.detect import detect_sfincs
from hydraulik.engines.sfincs.inp import (
    MAP_NAME,
    planned_outputs,
    precip_depth_mm,
    read_inp,
)
from hydraulik.engines.sfincs.run import run_sfincs
from hydraulik.exceptions import EngineError, MissingDependencyError, UnsupportedError
from hydraulik.operations._results import summarise
from hydraulik.operations._support import (
    blocker,
    extra_blocker,
    file_dicts,
    missing_extras,
    require_extras,
    stage_model,
)
from hydraulik.output import Writer, plan_directory
from hydraulik.settings import load_settings

__all__ = ["run_model"]

logger = logging.getLogger(__name__)


def run_model(
    *,
    model: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> RunDocument | PlanDocument:
    """Run SFINCS on a model directory and write its results to ``output_dir``.

    The model files are copied to the staging directory of the writer and SFINCS runs
    there; the map, the station file and the log are moved into ``output_dir`` only
    when the run has finished, its status is zero and the map can be read. The result
    carries the maxima, the flooded areas and the water balance of the run.

    Parameters
    ----------
    model : path-like
        The model directory (``hydraulik model build``), with ``sfincs.inp``.
    output_dir : path-like
        Directory for ``sfincs_map.nc``, ``sfincs_his.nc`` (when the model has
        observation points) and ``sfincs.log``; created when missing. It may be the
        model directory itself.
    force : bool, optional
        Replace result files that exist.
    check : bool, optional
        Plan without effects: list the files, the engine that would run and whatever
        would stop the run.

    Returns
    -------
    RunDocument or PlanDocument
        ``hydraulik-run/1``, or the ``hydraulik-plan/1`` of ``check``.

    Raises
    ------
    NotFoundError
        If ``model`` has no ``sfincs.inp``.
    UnsupportedError
        If the model does not write NetCDF output (``outputformat = net``).
    MissingDependencyError
        If no SFINCS is found or netCDF4 is missing (reason ``engine_missing`` or
        ``extra_missing``).
    ConflictError
        If an output exists without ``force``, or the directory is inside a store.
    EngineError
        If SFINCS fails, times out, or writes a map whose status is not zero.

    Examples
    --------
    >>> run_model(model="no-such-model", output_dir="out")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.NotFoundError: sfincs.inp not found: no-such-model/sfincs.inp
    """
    folder = Path(model)
    inp = read_inp(folder)
    if inp.get("outputformat", "bin") != "net":
        raise UnsupportedError(
            f"the model writes {inp.get('outputformat', 'bin')!r} output, not NetCDF",
            details={"option": "outputformat", "value": inp.get("outputformat", "bin")},
            hint="Set outputformat = net in sfincs.inp; Hydraulik reads NetCDF.",
            reason="output_format",
        )
    outputs = planned_outputs(inp)
    plan = plan_directory(output_dir, outputs, force=force)
    settings = load_settings()
    status, install = detect_sfincs(settings)
    timeout_s = float(settings.value("sfincs.timeout_s"))
    threads = settings.value("sfincs.threads")
    if check:
        blockers = []
        if install is None:
            blockers.append(blocker("engine_missing", status.detail, status.hint))
        blockers += [
            extra_blocker(name) for name in missing_extras(("numpy", "netCDF4"))
        ]
        version = status.version or "version unknown"
        where = (
            "SFINCS is not available"
            if install is None
            else f"{install.kind} {status.location} ({version})"
        )
        return PlanDocument.from_write_plan(
            plan,
            steps=[
                f"copy the files of {folder} to the staging directory",
                f"run {where} with a timeout of {timeout_s:g} s",
                f"read {MAP_NAME}: maxima, flooded areas and the water balance",
                f"move {', '.join(outputs)} into {plan.directory}",
            ],
            blockers=blockers,
        )
    if install is None:
        raise MissingDependencyError(
            status.detail,
            details={"engine": "sfincs"},
            hint=status.hint,
            reason="engine_missing",
        )
    require_extras("numpy", "netCDF4")
    precip = inp.get("precipfile")
    expected_rain_mm = precip_depth_mm(folder / precip) if precip else None
    last_logged = -10

    def progress(percent: int) -> None:
        nonlocal last_logged
        if percent >= last_logged + 10:
            logger.info("SFINCS %d %% complete", percent)
            last_logged = percent

    with Writer(plan) as writer:
        stage_model(folder, writer.staging, outputs)
        info = run_sfincs(
            install,
            writer.staging,
            timeout_s=timeout_s,
            threads=None if threads is None else int(threads),
            progress=progress,
        )
        produced = writer.staging / MAP_NAME
        if not produced.is_file():
            raise EngineError(
                f"SFINCS finished without writing {MAP_NAME}",
                details={"log_tail": info.log_tail},
                hint="Read details.log_tail; the model may not write NetCDF output.",
                reason="engine_failed",
            )
        results = summarise(
            produced,
            writer.staging / outputs[1] if len(outputs) == 3 else None,
            expected_rain_mm=expected_rain_mm,
            source=plan.directory / MAP_NAME,
        )
        if results.engine["status"] not in (None, 0):
            raise EngineError(
                f"SFINCS reports status {results.engine['status']}, not 0",
                details={"status": results.engine["status"], "log_tail": info.log_tail},
                hint="Read details.log_tail and sfincs.log of the model.",
                reason="engine_failed",
            )
        records = writer.commit()
    document = RunDocument(
        engine={
            "kind": install.kind,
            "location": status.location,
            "version": status.version,
            "build_revision": results.engine["build_revision"],
        },
        elapsed_s=info.elapsed_s,
        results=results.to_dict(),
        files=file_dicts(records),
    )
    document.notices.extend(results.notices)
    return document
