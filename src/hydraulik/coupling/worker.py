"""The process that runs one coupled simulation (ADR-0005).

SFINCS keeps its state in global variables and writes to the standard output of its
process, so ``hydraulik model couple`` does not call the library in its own process: it
writes a job file and starts ``python -m hydraulik.coupling.worker JOB`` in the staging
directory. The worker opens SWMM and the SFINCS library, runs the loop of
:mod:`hydraulik.coupling.coupler`, finalises both engines (SFINCS writes its map and its
log, SWMM its report), writes the series of the exchange (``coupling.csv``) and the
summary the parent needs (``coupling.json``, or the error document of what went wrong),
and exits with 0 or 1. The parent reads the files; nothing but its exit code and those
two files crosses the process boundary.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np

from hydraulik.coupling.coupler import (
    CouplerResult,
    CouplerSettings,
    ExchangeNode,
    NodeResult,
    couple,
)
from hydraulik.coupling.diagnostics import (
    DEFAULT_HOLD_S,
    held_maximum,
    is_numerical_spike,
    sign_flips,
    sustained_spill,
)
from hydraulik.coupling.laws import Inlet
from hydraulik.data.tables import Hydrograph
from hydraulik.exceptions import InputDataError, error_document

__all__ = ["RESULT_NAME", "SERIES_NAME", "CoupleJob", "main", "run_job", "summarise"]

RESULT_NAME: Final = "coupling.json"
"""The summary (or the error) the worker leaves in the job directory."""

SERIES_NAME: Final = "coupling.csv"
"""The series of the exchange, one row per interval and node."""

SERIES_COLUMNS: Final = (
    "time_s",
    "surface_time_s",
    "node",
    "zs_m",
    "head_m",
    "exchange_m3s",
    "spill_m3s",
)


@dataclass(frozen=True)
class CoupleJob:
    """Everything the worker needs, as plain data.

    Attributes
    ----------
    library : str
        The SFINCS shared library.
    qext_unit : {"m3s", "ms"}
        The unit of ``qext`` in that library.
    directory : str
        The model directory: SFINCS runs in it and writes its results into it.
    inp, report, out : str
        The SWMM input and where SWMM writes its report and its binary output.
    nodes : tuple of ExchangeNode
        The nodes that may exchange water.
    settings : CouplerSettings
        The loop.
    inflows : dict of str to Hydrograph
        Discharge that enters a node of the network from outside, node name to its
        series (time from the start of the run).
    hold_s : float
        ``T`` of the held maximum of the head [s].
    """

    library: str
    qext_unit: str
    directory: str
    inp: str
    report: str
    out: str
    nodes: tuple[ExchangeNode, ...]
    settings: CouplerSettings
    inflows: dict[str, Hydrograph] = field(default_factory=dict)
    hold_s: float = DEFAULT_HOLD_S

    def to_json(self) -> str:
        """Return the job as JSON text."""
        return json.dumps(dataclasses.asdict(self), indent=2)

    @classmethod
    def read(cls, path: Path) -> CoupleJob:
        """Read a job file written by :meth:`to_json`.

        Raises
        ------
        InputDataError
            If the file is not a job (reason ``invalid_job``).
        """
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
            settings = dict(body.pop("settings"))
            inlet = Inlet(**settings.pop("inlet"))
            nodes = tuple(ExchangeNode(**item) for item in body.pop("nodes"))
            inflows = {
                name: Hydrograph(
                    tuple(float(t) for t in item["times_s"]),
                    tuple(float(q) for q in item["discharge_m3s"]),
                )
                for name, item in body.pop("inflows", {}).items()
            }
            return cls(
                nodes=nodes,
                inflows=inflows,
                settings=CouplerSettings(inlet=inlet, **settings),
                **body,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise InputDataError(
                f"{path.name} is not a coupling job: {exc}",
                details={"path": str(path)},
                reason="invalid_job",
            ) from exc


def _node_summary(
    node: NodeResult, times: np.ndarray[Any, Any], hold_s: float
) -> dict[str, Any]:
    """Return the volumes and the diagnostics of one node."""
    head = np.asarray(node.head_m)
    held = held_maximum(times, head, hold_s)
    spill = sustained_spill(times, node.spill_m3s, hold_s)
    return {
        "name": node.name,
        "cell": node.cell,
        "ground_m": node.ground_m,
        "exchanged_m3": node.exchanged_m3,
        "flooded_m3": node.flooded_m3,
        "returned_m3": node.returned_m3,
        "pending_m3": node.pending_m3,
        "capped_steps": node.capped_steps,
        "peak_exchange_m3s": float(np.max(node.exchange_m3s)),
        "peak_return_m3s": max(
            float(np.max(node.spill_m3s)), float(-np.min(node.exchange_m3s)), 0.0
        ),
        "max_level_m": float(np.max(node.zs_m)),
        "max_head_m": float(head.max()),
        "held_max_head_m": held,
        "numerical_spike": is_numerical_spike(float(head.max()), held),
        "sign_flips": sign_flips(node.exchange_m3s),
        "spill": {
            "total_m3": spill.total_m3,
            "sustained_m3": spill.sustained_m3,
            "sustained": spill.sustained,
            "longest_s": spill.longest_s,
        },
    }


def summarise(
    result: CouplerResult, swmm: dict[str, Any], hold_s: float
) -> dict[str, Any]:
    """Return the summary the parent reads: volumes, SWMM's totals, node diagnostics.

    Parameters
    ----------
    result : CouplerResult
        The run of the loop.
    swmm : dict
        The summary of SWMM's finished run (``dataclasses.asdict`` of
        :class:`~hydraulik.engines.swmm.run.SwmmSummary`).
    hold_s : float
        ``T`` of the held maximum of the head [s].

    Returns
    -------
    dict
        JSON-compatible; the keys are those of ``coupling.json``.
    """
    times = np.asarray(result.times_s)
    overshoot = np.asarray(result.overshoot_s)
    return {
        "intervals": result.intervals,
        "surface_time_s": result.surface_times_s[-1] if result.surface_times_s else 0.0,
        "overshoot_s": {
            "mean": float(overshoot.mean()) if overshoot.size else 0.0,
            "max": float(overshoot.max()) if overshoot.size else 0.0,
        },
        "network_inflow_m3": result.network_inflow_m3,
        "inflows_m3": dict(result.inflows_m3),
        "outfall_net_m3": result.outfall_net_m3,
        "outfall_gross_inflow_m3": result.outfall_gross_inflow_m3,
        "surface_final_m3": result.surface_final_m3,
        "network_final_m3": result.network_final_m3,
        "exchanged_m3": result.exchanged_m3,
        "pending_m3": result.pending_m3,
        "flooded_m3": result.flooded_m3,
        "outside": list(result.outside),
        "nodes": [_node_summary(node, times, hold_s) for node in result.nodes],
        "swmm": swmm,
    }


def write_series(path: Path, result: CouplerResult) -> None:
    """Write the series of the exchange as CSV, one row per interval and node."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(SERIES_COLUMNS)
        for index, (time_s, surface_s) in enumerate(
            zip(result.times_s, result.surface_times_s, strict=True)
        ):
            for node in result.nodes:
                writer.writerow(
                    [
                        f"{time_s:g}",
                        f"{surface_s:.3f}",
                        node.name,
                        f"{node.zs_m[index]:.5f}",
                        f"{node.head_m[index]:.5f}",
                        f"{node.exchange_m3s[index]:.8f}",
                        f"{node.spill_m3s[index]:.8f}",
                    ]
                )


def run_job(job: CoupleJob, *, surface: Any = None) -> dict[str, Any]:
    """Run the coupled simulation of a job and write its files.

    SFINCS runs in ``job.directory`` (the process changes into it while the model is
    open); its map and log, SWMM's report and ``coupling.csv`` are there afterwards.

    Parameters
    ----------
    job : CoupleJob
        What to run.
    surface : Surface or None, optional
        A surface model to use instead of the SFINCS library (tests); it is not
        finalised here.

    Returns
    -------
    dict
        The summary (see :func:`summarise`).

    Raises
    ------
    HydraulikError
        Whatever SWMM, SFINCS or the loop raise.
    """
    from hydraulik.engines.swmm.run import SwmmStepper

    directory = Path(job.directory)
    with SwmmStepper(job.inp, job.report, job.out, stride_s=1) as stepper:
        if surface is not None:
            result = couple(surface, stepper, job.nodes, job.settings, job.inflows)
        else:
            from hydraulik.engines.sfincs.bmi import SfincsSurface

            with SfincsSurface(
                job.library,
                directory,
                qext_unit=job.qext_unit,  # type: ignore[arg-type]
            ) as sfincs:
                result = couple(sfincs, stepper, job.nodes, job.settings, job.inflows)
                sfincs.finalize()  # writes the map and the log before SWMM's report
        summary = stepper.finish()
    write_series(directory / SERIES_NAME, result)
    return summarise(result, dataclasses.asdict(summary), job.hold_s)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the job named on the command line and leave ``coupling.json`` beside it.

    Parameters
    ----------
    argv : sequence of str or None, optional
        The job file; ``sys.argv[1:]`` when ``None``.

    Returns
    -------
    int
        0 when the run finished, 1 when it failed (the error document is in the file).
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write("usage: python -m hydraulik.coupling.worker JOB.json\n")
        return 2
    job_path = Path(args[0]).resolve()
    result_path = job_path.parent / RESULT_NAME
    try:
        job = CoupleJob.read(job_path)
        result_path = Path(job.directory) / RESULT_NAME
        body: dict[str, Any] = {"status": "ok", **run_job(job)}
        code = 0
    except BaseException as exc:  # noqa: BLE001 - every failure goes to the parent
        body = {"status": "error", "error": error_document(exc)}
        code = 1
    result_path.write_text(json.dumps(body), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
