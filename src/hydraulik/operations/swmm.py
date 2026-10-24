"""``swmm run``: run a SWMM sewer network with an inflow hydrograph (ADR-0002)."""

from __future__ import annotations

import dataclasses
import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from hydraulik.data.tables import Hydrograph, read_hydrograph
from hydraulik.documents import PlanDocument, SwmmDocument, notice
from hydraulik.engines.swmm import inp as inp_module
from hydraulik.engines.swmm.network import (
    Network,
    SwmmSettings,
    read_network_table,
    write_inp,
)
from hydraulik.engines.swmm.run import SwmmSummary, run_swmm
from hydraulik.exceptions import InvalidInputError, NotFoundError
from hydraulik.operations._support import (
    extra_blocker,
    extra_version,
    file_dicts,
    missing_extras,
    require_extras,
)
from hydraulik.output import Writer, plan_directory

__all__ = ["run_network"]

INP_NAME: Final = "network.inp"
REPORT_NAME: Final = "network.rpt"
OUTPUT_NAMES: Final = (INP_NAME, REPORT_NAME)
"""Files of a run, in plan order; SWMM's binary output stays in staging."""

DEFAULT_RECESSION_MIN: Final = 10.0
"""Minutes the run of a network table lasts after the inflow ends."""

CONTINUITY_WARNING_PERCENT: Final = 5.0
"""A flow-routing continuity error above this [percent] is a warning."""

Surcharge = Literal["EXTRAN", "SLOT"]


@dataclass(frozen=True)
class _Job:
    """Everything a run needs, read and checked before anything is written."""

    kind: Literal["network", "inp"]
    path: Path
    text: str
    network: Network | None
    inflow_path: Path | None
    inflow_node: str | None
    hydrograph: Hydrograph | None
    duration_s: int | None
    settings: SwmmSettings | None


def _refuse(
    option: str, why: str, reason: str, hint: str | None = None
) -> InvalidInputError:
    return InvalidInputError(
        f"--{option.replace('_', '-')}: {why}",
        details={"option": option},
        hint=hint,
        reason=reason,
    )


def _prepare(
    *,
    network: str | os.PathLike[str] | None,
    inp: str | os.PathLike[str] | None,
    inflow: str | os.PathLike[str] | None,
    inflow_node: str | None,
    recession_min: float | None,
    routing_step_s: float | None,
    surcharge_method: Surcharge | None,
) -> _Job:
    """Read the sources and check the combination of options."""
    if (network is None) == (inp is None):
        raise InvalidInputError(
            "give exactly one of --network and --inp",
            details={"option": "network" if network is None else "inp"},
            hint="--network is a network table, --inp your own SWMM input (CMS).",
            reason="missing_option" if network is None else "exclusive_options",
        )
    if (inflow is None) != (inflow_node is None):
        raise _refuse(
            "inflow_node" if inflow_node is None else "inflow",
            "--inflow and --inflow-node go together",
            "missing_option",
            "The hydrograph enters at one node: name it with --inflow-node.",
        )
    if network is not None and inflow is None:
        raise _refuse(
            "inflow",
            "a network table has no inflow of its own",
            "inflow_required",
            "Give --inflow (a hydrograph table) and --inflow-node.",
        )
    table_only = {
        "recession_min": recession_min,
        "routing_step_s": routing_step_s,
        "surcharge_method": surcharge_method,
    }
    if inp is not None:
        for name, value in table_only.items():
            if value is not None:
                raise _refuse(
                    name,
                    "applies to a network table; your SWMM input keeps its own",
                    "option_not_applicable",
                    "Set it in the SWMM input file.",
                )
    hydrograph = read_hydrograph(Path(inflow)) if inflow is not None else None
    chosen = network if network is not None else inp
    assert chosen is not None  # exactly one of the two was given
    source = Path(chosen)
    if not source.is_file():
        raise NotFoundError(
            f"SWMM source not found: {source}",
            details={"path": str(source)},
            reason="path_missing",
        )
    if inp is not None:
        text = source.read_text(encoding="utf-8", errors="replace")
        inp_module.require_metric(text)
        return _Job(
            "inp",
            source,
            text,
            None,
            None if inflow is None else Path(inflow),
            inflow_node,
            hydrograph,
            None,
            None,
        )
    assert hydrograph is not None and inflow is not None
    table = read_network_table(source)
    if inflow_node not in {j.name for j in table.junctions}:
        raise InvalidInputError(
            f"the network table has no junction {inflow_node!r}",
            details={
                "option": "inflow_node",
                "value": inflow_node,
                "allowed": [j.name for j in table.junctions][:50],
            },
            hint="Name a junction of the table; the outfall takes no inflow.",
            reason="unknown_node",
        )
    end_s = hydrograph.times_s[-1] + 60.0 * (
        DEFAULT_RECESSION_MIN if recession_min is None else recession_min
    )
    duration_s = max(1, math.ceil(end_s))
    settings = SwmmSettings(
        float(duration_s),
        routing_step_s=0.5 if routing_step_s is None else routing_step_s,
        surcharge_method="EXTRAN" if surcharge_method is None else surcharge_method,
    )
    return _Job(
        "network",
        source,
        write_inp(table, settings),
        table,
        Path(inflow),
        inflow_node,
        hydrograph,
        duration_s,
        settings,
    )


def _notices(job: _Job, summary: SwmmSummary) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    error = summary.continuity_error_percent
    if abs(error) > CONTINUITY_WARNING_PERCENT:
        found.append(
            notice(
                "warning",
                "continuity_error",
                f"SWMM's flow routing continuity error is {error:.2f} %, above "
                f"{CONTINUITY_WARNING_PERCENT:g} %: read {REPORT_NAME} before using "
                "the result",
            )
        )
    flooded = [node for node in summary.nodes if node.flooded]
    if flooded:
        worst = max(flooded, key=lambda node: node.flooding_volume_m3)
        found.append(
            notice(
                "info",
                "flooding",
                f"{len(flooded)} node(s) flooded, {summary.flooding_m3:.1f} m3 left "
                f"the network; the most at {worst.name} "
                f"({worst.flooding_volume_m3:.1f} m3)",
            )
        )
    hydrograph = job.hydrograph
    if hydrograph is not None and hydrograph.times_s[-1] > summary.duration_s:
        found.append(
            notice(
                "warning",
                "inflow_cut",
                f"the hydrograph lasts {hydrograph.times_s[-1]:g} s but the run "
                f"{summary.duration_s:g} s: the rest of it did not enter the network",
            )
        )
    return found


def run_network(
    *,
    network: str | os.PathLike[str] | None = None,
    inp: str | os.PathLike[str] | None = None,
    inflow: str | os.PathLike[str] | None = None,
    inflow_node: str | None = None,
    recession_min: float | None = None,
    routing_step_s: float | None = None,
    surcharge_method: Surcharge | None = None,
    output_dir: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> SwmmDocument | PlanDocument:
    """Run a SWMM sewer network and write its input and report to ``output_dir``.

    The source is a network table (one row per node, :mod:`hydraulik.engines.swmm`
    renders it for SWMM 5.2 in SI units) or your own SWMM input in SI units. An inflow
    hydrograph enters at one node. The run happens in staging; ``network.inp`` and
    ``network.rpt`` reach ``output_dir`` only after SWMM finished.

    Parameters
    ----------
    network : path-like or None, optional
        Network table (CSV). Exactly one of ``network`` and ``inp``.
    inp : path-like or None, optional
        A SWMM input file with ``FLOW_UNITS CMS``. It is run where it is (relative
        file references keep working) and copied to ``network.inp``.
    inflow : path-like or None, optional
        Hydrograph table (``time_min``, ``discharge_m3s``) applied as the lateral
        inflow of ``inflow_node``. Required with ``network``.
    inflow_node : str or None, optional
        The node that receives the inflow. Required with ``inflow``.
    recession_min : float or None, optional
        Network table only: minutes the run lasts after the last time of the
        hydrograph; 10 when not given.
    routing_step_s : float or None, optional
        Network table only: SWMM's fixed routing step [s]; 0.5 when not given.
    surcharge_method : {"EXTRAN", "SLOT"} or None, optional
        Network table only: how SWMM treats pressurised flow; ``EXTRAN`` when not
        given (``SLOT`` loses water in sustained pressurised flow, ADR-0002).
    output_dir : path-like
        Directory for ``network.inp`` and ``network.rpt``; created when missing.
    force : bool, optional
        Replace files that exist.
    check : bool, optional
        Plan without effects.

    Returns
    -------
    SwmmDocument or PlanDocument
        ``hydraulik-swmm/1`` with the totals and the peaks of every node and conduit,
        or the ``hydraulik-plan/1`` of ``check``. The notices carry a continuity error
        above 5 %, flooded nodes and an inflow that is longer than the run.

    Raises
    ------
    InvalidInputError
        If the combination of options is wrong (reasons ``missing_option``,
        ``exclusive_options``, ``inflow_required``, ``option_not_applicable``) or the
        inflow node is not in the network (``unknown_node``).
    NotFoundError
        If a source file does not exist.
    InputDataError
        If a table is malformed or SWMM rejects the input (``invalid_inp``).
    UnsupportedError
        If the SWMM input is not in SI units.
    MissingDependencyError
        If pyswmm is not installed (extra ``swmm``).
    ConflictError
        If an output exists without ``force``, or the directory is inside a store.

    Examples
    --------
    >>> run_network(inp="no-such.inp", output_dir="out")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.NotFoundError: SWMM source not found: no-such.inp
    """
    job = _prepare(
        network=network,
        inp=inp,
        inflow=inflow,
        inflow_node=inflow_node,
        recession_min=recession_min,
        routing_step_s=routing_step_s,
        surcharge_method=surcharge_method,
    )
    plan = plan_directory(output_dir, OUTPUT_NAMES, force=force)
    version = extra_version("pyswmm")
    if check:
        generated = job.kind == "network"
        steps = [
            f"read the {'network table' if generated else 'SWMM input'} {job.path}",
            (
                f"write {INP_NAME} (SWMM 5.2, SI units, {job.duration_s} s)"
                if generated
                else f"copy {job.path} to {INP_NAME}"
            ),
        ]
        if job.hydrograph is not None:
            steps.append(
                f"apply {job.inflow_path} ({job.hydrograph.volume_m3:.1f} m3) as the "
                f"inflow of {job.inflow_node}"
            )
        steps += [
            f"run SWMM through pyswmm {version or '(not installed)'} in strides of 1 s",
            f"write {REPORT_NAME}, read the totals and the peaks of every node",
            f"move {', '.join(OUTPUT_NAMES)} into {plan.directory}",
        ]
        return PlanDocument.from_write_plan(
            plan,
            steps=steps,
            blockers=[extra_blocker(name) for name in missing_extras(("pyswmm",))],
        )
    require_extras("pyswmm")
    inflows = (
        {job.inflow_node: job.hydrograph}
        if job.hydrograph is not None and job.inflow_node is not None
        else None
    )
    with Writer(plan) as writer:
        staged_inp = writer.staged_path(INP_NAME)
        if job.kind == "network":
            staged_inp.write_text(job.text, encoding="utf-8")
            run_path = staged_inp
        else:
            shutil.copyfile(job.path, staged_inp)
            run_path = job.path
        summary = run_swmm(
            run_path,
            writer.staged_path(REPORT_NAME),
            writer.staging / "network.out",
            inflows=inflows,
        )
        records = writer.commit()
    source: dict[str, Any] = {"kind": job.kind, "path": str(job.path)}
    if job.hydrograph is not None:
        source["inflow"] = {
            "path": str(job.inflow_path),
            "node": job.inflow_node,
            "volume_m3": job.hydrograph.volume_m3,
            "duration_s": job.hydrograph.times_s[-1],
        }
    document = SwmmDocument(
        engine={
            "name": "pyswmm",
            "version": version,
            "toolkit": extra_version("swmm-toolkit"),
        },
        source=source,
        duration_s=summary.duration_s,
        totals={
            "external_inflow_m3": summary.external_inflow_m3,
            "outflow_m3": summary.outflow_m3,
            "flooding_m3": summary.flooding_m3,
            "final_storage_m3": summary.final_storage_m3,
            "continuity_error_percent": summary.continuity_error_percent,
        },
        nodes=[dataclasses.asdict(node) for node in summary.nodes],
        conduits=[dataclasses.asdict(link) for link in summary.links],
        files=file_dicts(records),
    )
    document.notices.extend(_notices(job, summary))
    return document
