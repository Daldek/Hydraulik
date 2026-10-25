"""``model couple``: SFINCS and a SWMM network exchange water (ADR-0005)."""

from __future__ import annotations

import dataclasses
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from hydraulik.coupling.coupler import CouplerSettings, ExchangeNode
from hydraulik.coupling.laws import (
    DEFAULT_NODE_AREA_M2,
    RUBINATO_ORIFICE_COEFFICIENT,
    RUBINATO_WEIR_COEFFICIENT,
    Inlet,
)
from hydraulik.data.tables import Hydrograph, read_hydrograph
from hydraulik.documents import CoupleDocument, PlanDocument, notice
from hydraulik.engines.detect import detect_sfincs_library
from hydraulik.engines.sfincs.inp import (
    MAP_NAME,
    STATIONS_NAME,
    patch_inp,
    planned_outputs,
    precip_depth_mm,
    read_inp,
    tstop_s,
)
from hydraulik.engines.swmm import inp as inp_module
from hydraulik.engines.swmm.network import (
    SWMM_START,
    SwmmSettings,
    read_network_table,
    write_inp,
)
from hydraulik.exceptions import (
    InvalidInputError,
    MissingDependencyError,
    NotFoundError,
    UnsupportedError,
)
from hydraulik.operations._support import (
    blocker,
    extra_blocker,
    extra_found,
    extra_version,
    file_dicts,
    missing_extras,
    refuse_option,
    require_extras,
    stage_model,
    unknown_inflow_node,
)
from hydraulik.operations.swmm import CONTINUITY_WARNING_PERCENT
from hydraulik.output import Writer, plan_directory
from hydraulik.settings import load_settings

__all__ = ["couple_model"]

INP_NAME: Final = "network.inp"
REPORT_NAME: Final = "network.rpt"
SERIES_NAME: Final = "coupling.csv"
JOB_NAME: Final = "coupling-job.json"
"""The job file, in staging only."""

DEFAULT_RIM_TOLERANCE_M: Final = 0.1
"""Largest difference between a node's rim and the bed of its cell [m] (my choice: DEMs
and surveyed rims differ by centimetres to decimetres)."""

DEFAULT_COORDINATOR_RELAXATION: Final = 0.1
"""Under-relaxation of the coordinator mode (README 3.9 of the feasibility test)."""

OSCILLATION_FLIPS: Final = 20
"""More sign changes than this of the exchange of one node are called an oscillation."""

_PACKAGES = ("numpy", "netCDF4", "pyswmm")
Mode = Literal["swmm_flooding", "coordinator"]
Surcharge = Literal["EXTRAN", "SLOT"]

_SWMM_KEYS = (
    "FLOW_ROUTING",
    "START_DATE",
    "START_TIME",
    "END_DATE",
    "END_TIME",
    "REPORT_START_DATE",
    "REPORT_START_TIME",
    "ROUTING_STEP",
    "VARIABLE_STEP",
    "MIN_SURFAREA",
)
"""The ``[OPTIONS]`` that a coupling sets in your SWMM input (the junction ``SurDepth``
too): the exchange needs a fixed step of at most one stride and a clock that matches
SFINCS."""


@dataclass(frozen=True)
class _Job:
    """Everything a coupled run needs, read and checked before anything is written."""

    folder: Path
    sfincs_inp: dict[str, str]
    duration_s: float
    kind: Literal["network", "inp"]
    source: Path
    text: str
    nodes: tuple[ExchangeNode, ...]
    outside: tuple[str, ...]
    no_coordinates: tuple[str, ...]
    settings: CouplerSettings
    surcharge: str | None
    patched: tuple[str, ...]
    outputs: tuple[str, ...]
    inflow: Hydrograph | None
    inflow_path: Path | None
    inflow_node: str | None


def _clock(seconds: float) -> tuple[str, str]:
    from datetime import timedelta

    moment = SWMM_START + timedelta(seconds=seconds)
    return moment.strftime("%m/%d/%Y"), moment.strftime("%H:%M:%S")


def _patch_user_inp(
    text: str, *, duration_s: float, routing_step_s: float, area_m2: float, mode: Mode
) -> str:
    """Set what a coupling needs in the user's SWMM input; everything else is theirs."""
    start_date, start_time = _clock(0.0)
    end_date, end_time = _clock(duration_s)
    patched = inp_module.patch_options(
        text,
        {
            "FLOW_ROUTING": "DYNWAVE",
            "START_DATE": start_date,
            "START_TIME": start_time,
            "END_DATE": end_date,
            "END_TIME": end_time,
            "REPORT_START_DATE": start_date,
            "REPORT_START_TIME": start_time,
            "ROUTING_STEP": f"{routing_step_s:g}",
            "VARIABLE_STEP": 0,
            "MIN_SURFAREA": f"{area_m2:g}",
        },
    )
    return inp_module.patch_junction_surcharge(
        patched, 0.0 if mode == "swmm_flooding" else 100.0
    )


def _prepare(
    *,
    model: str | os.PathLike[str],
    network: str | os.PathLike[str] | None,
    inp: str | os.PathLike[str] | None,
    inflow: str | os.PathLike[str] | None,
    inflow_node: str | None,
    exchange_interval_s: int | None,
    mode: Mode | None,
    relaxation: float | None,
    rim_tolerance_m: float | None,
    node_area_m2: float | None,
    weir_coefficient: float | None,
    orifice_coefficient: float | None,
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
    if inp is not None and surcharge_method is not None:
        raise refuse_option(
            "surcharge_method",
            "applies to a network table; your SWMM input keeps its own",
            "option_not_applicable",
            "Set SURCHARGE_METHOD in the SWMM input file.",
        )
    if (inflow is None) != (inflow_node is None):
        raise refuse_option(
            "inflow_node" if inflow_node is None else "inflow",
            "--inflow and --inflow-node go together",
            "missing_option",
            "The hydrograph enters at one node: name it with --inflow-node.",
        )
    chosen_mode: Mode = "swmm_flooding" if mode is None else mode
    weight = (
        (1.0 if chosen_mode == "swmm_flooding" else DEFAULT_COORDINATOR_RELAXATION)
        if relaxation is None
        else relaxation
    )
    step_s = 0.5 if routing_step_s is None else routing_step_s
    if not 0.0 < step_s <= 1.0:
        raise refuse_option(
            "routing_step_s",
            "SWMM's routing step must be above 0 and at most 1 s, the stride of the "
            "exchange",
            "out_of_range",
        )
    interval = 1 if exchange_interval_s is None else exchange_interval_s
    if interval < 1:
        raise refuse_option(
            "exchange_interval_s",
            "the interval is a whole number of s, at least 1",
            "out_of_range",
        )
    settings = CouplerSettings(
        interval_s=interval,
        mode=chosen_mode,
        relaxation=weight,
        rim_tolerance_m=(
            DEFAULT_RIM_TOLERANCE_M if rim_tolerance_m is None else rim_tolerance_m
        ),
        inlet=Inlet(
            DEFAULT_NODE_AREA_M2 if node_area_m2 is None else node_area_m2,
            RUBINATO_WEIR_COEFFICIENT if weir_coefficient is None else weir_coefficient,
            RUBINATO_ORIFICE_COEFFICIENT
            if orifice_coefficient is None
            else orifice_coefficient,
        ),
    )

    folder = Path(model)
    sfincs_inp = read_inp(folder)
    if sfincs_inp.get("outputformat", "bin") != "net":
        raise UnsupportedError(
            f"the model writes {sfincs_inp.get('outputformat', 'bin')!r} output, not "
            "NetCDF",
            details={"option": "outputformat"},
            hint="Set outputformat = net in sfincs.inp; Hydraulik reads NetCDF.",
            reason="output_format",
        )
    duration_s = tstop_s(sfincs_inp)
    chosen = Path(network if network is not None else inp)  # type: ignore[arg-type]
    if not chosen.is_file():
        raise NotFoundError(
            f"SWMM source not found: {chosen}",
            details={"path": str(chosen)},
            reason="path_missing",
        )
    hydrograph = read_hydrograph(Path(inflow)) if inflow is not None else None
    patched: tuple[str, ...] = ()
    no_coordinates: list[str] = []
    surcharge: str | None
    if network is not None:
        table = read_network_table(chosen)
        if inflow_node is not None and inflow_node not in {
            j.name for j in table.junctions
        }:
            raise unknown_inflow_node(
                inflow_node, [j.name for j in table.junctions], junctions_only=True
            )
        surcharge = surcharge_method or (
            "EXTRAN" if chosen_mode == "swmm_flooding" else "SLOT"
        )
        text = write_inp(
            table,
            SwmmSettings(
                duration_s,
                routing_step_s=step_s,
                surcharge_method=surcharge,
                spill=chosen_mode,
                min_surface_area_m2=settings.inlet.area_m2,
            ),
        )
        candidates = [ExchangeNode(j.name, j.x_m, j.y_m) for j in table.junctions]
        kind: Literal["network", "inp"] = "network"
    else:
        original = chosen.read_text(encoding="utf-8", errors="replace")
        inp_module.require_metric(original)
        known = inp_module.node_names(original)
        if inflow_node is not None and inflow_node not in known:
            raise unknown_inflow_node(inflow_node, known, junctions_only=False)
        text = _patch_user_inp(
            original,
            duration_s=duration_s,
            routing_step_s=step_s,
            area_m2=settings.inlet.area_m2,
            mode=chosen_mode,
        )
        surcharge = inp_module.options(text).get("SURCHARGE_METHOD", "EXTRAN").upper()
        coordinates = inp_module.coordinates(text)
        candidates = []
        for junction in inp_module.junctions(text):
            if junction.name in coordinates:
                candidates.append(
                    ExchangeNode(junction.name, *coordinates[junction.name])
                )
            else:
                no_coordinates.append(junction.name)
        patched = (*_SWMM_KEYS, "SurDepth")
        kind = "inp"
    nodes: list[ExchangeNode] = []
    outside: list[str] = []
    if extra_found("numpy"):
        from hydraulik.engines.sfincs.layout import ModelLayout

        layout = ModelLayout.read(folder)
        for node in candidates:
            if layout.cell_of(node.x_m, node.y_m) is None:
                outside.append(node.name)
            else:
                nodes.append(node)
        if not nodes:
            raise InvalidInputError(
                "no node of the network lies on an active cell of the SFINCS model",
                details={"nodes": [n.name for n in candidates][:50]},
                hint="Check that the network and the model use the same CRS, and that "
                "the domain of the model covers the nodes.",
                reason="no_exchange_nodes",
            )
    else:
        nodes = candidates
    outputs = (*planned_outputs(sfincs_inp), INP_NAME, REPORT_NAME, SERIES_NAME)
    return _Job(
        folder,
        sfincs_inp,
        duration_s,
        kind,
        chosen,
        text,
        tuple(nodes),
        tuple(outside),
        tuple(no_coordinates),
        settings,
        surcharge,
        patched,
        outputs,
        hydrograph,
        None if inflow is None else Path(inflow),
        inflow_node,
    )


def _notices(
    job: _Job, summary: dict[str, Any], balance: dict[str, Any]
) -> list[dict[str, str]]:
    """Return the notices of a finished run."""
    found: list[dict[str, str]] = []
    percent = balance["total_error_percent"]
    messages = {
        "balance_residual": (
            f"the water balance of the coupled run does not close: the residual is "
            f"{percent:.2f} % of the water that entered; check sfincs.qext_unit and "
            "sfincs.log before using the result"
        ),
        "balance_gain": (
            f"the coupled run gained water: the residual is {percent:.2f} % although "
            "water can only leave; check sfincs.qext_unit"
        ),
        "rain_mismatch": "the rain SFINCS applied differs from the precipitation file",
        "time_mismatch": "the last depth map is not at the end of the run",
        "no_rain_output": (
            "the map has no accumulated rain (storecumprcp was off): no balance"
        ),
    }
    for flag in balance["flags"]:
        found.append(notice("warning", flag, messages[flag]))
    series = job.inflow
    if series is not None and series.times_s[-1] > job.duration_s:
        found.append(
            notice(
                "warning",
                "inflow_cut",
                f"the hydrograph lasts {series.times_s[-1]:g} s but the run "
                f"{job.duration_s:g} s: the rest of it did not enter the network",
            )
        )
    swmm = summary["swmm"]
    error = swmm["continuity_error_percent"]
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
    swinging = [
        n["name"] for n in summary["nodes"] if n["sign_flips"] > OSCILLATION_FLIPS
    ]
    if swinging:
        found.append(
            notice(
                "warning",
                "exchange_oscillation",
                f"the exchange changes direction more than {OSCILLATION_FLIPS} times "
                f"at {', '.join(swinging[:5])}: a limit cycle; shorten "
                "--exchange-interval-s or lower --relaxation",
            )
        )
    spiking = [n["name"] for n in summary["nodes"] if n["numerical_spike"]]
    if spiking:
        found.append(
            notice(
                "warning",
                "numerical_spike",
                f"the head at {', '.join(spiking[:5])} has a spike above the head held "
                "for 10 s: SWMM makes such spikes at the onset of pressurised "
                "flow; use held_max_head_m of the node, not max_head_m",
            )
        )
    capped = [n["name"] for n in summary["nodes"] if n["capped_steps"] > 0]
    if capped:
        found.append(
            notice(
                "info",
                "exchange_capped",
                f"the water taken from the surface was cut to what stood in the cell "
                f"at {', '.join(capped[:5])}",
            )
        )
    if job.outside:
        found.append(
            notice(
                "warning",
                "nodes_outside_domain",
                f"{len(job.outside)} node(s) lie outside the active domain and "
                f"exchange nothing: {', '.join(job.outside[:5])}",
            )
        )
    if job.no_coordinates:
        found.append(
            notice(
                "warning",
                "nodes_without_coordinates",
                f"{len(job.no_coordinates)} junction(s) of the SWMM input have no "
                f"[COORDINATES] and exchange nothing: "
                f"{', '.join(job.no_coordinates[:5])}",
            )
        )
    if balance["lost_flooding_m3"] > 0.0:
        found.append(
            notice(
                "warning",
                "flooding_lost",
                f"{balance['lost_flooding_m3']:.1f} m3 flooded out of nodes that have "
                "no cell on the surface and did not return to it",
            )
        )
    if job.settings.mode == "coordinator" and job.surcharge == "EXTRAN":
        found.append(
            notice(
                "warning",
                "coordinator_extran",
                "the coordinator mode with SURCHARGE_METHOD EXTRAN diverges when the "
                "network is pressurised; use SLOT (it loses 2 to 17 % of the water)",
            )
        )
    if job.kind == "inp":
        found.append(
            notice(
                "info",
                "inp_patched",
                "your SWMM input was run with these options set for the coupling, and "
                f"SurDepth of every junction: {', '.join(job.patched[:-1])}; the copy "
                f"is {INP_NAME}",
            )
        )
    return found


def _document(
    job: _Job,
    summary: dict[str, Any],
    staging: Path,
    *,
    library: str | None,
    qext_unit: str,
    elapsed_s: float,
) -> CoupleDocument:
    """Read the map of the run, book the water and build the result document."""
    from hydraulik.coupling.balance import BALANCE_WARNING_PERCENT, coupled_balance
    from hydraulik.engines.sfincs.results import (
        depth_statistics,
        read_map,
        read_stations,
        surface_balance,
    )
    from hydraulik.operations._results import (
        DEFAULT_THRESHOLDS_M,
        describe_depth,
        describe_grid,
        describe_stations,
    )

    run = read_map(staging / MAP_NAME)
    his = staging / STATIONS_NAME
    precip = job.sfincs_inp.get("precipfile")
    expected = precip_depth_mm(job.folder / precip) if precip else None
    surface = surface_balance(run, expected_rain_mm=expected)
    stats = depth_statistics(run, DEFAULT_THRESHOLDS_M)
    swmm = summary["swmm"]
    returned_to_surface = (
        summary["flooded_m3"] if job.settings.mode == "swmm_flooding" else 0.0
    )
    lost = max(swmm["flooding_m3"] - returned_to_surface, 0.0)
    coupled = coupled_balance(
        rain_m3=surface.rain_m3,
        inflow_m3=0.0,
        infiltration_m3=surface.infiltration_m3,
        surface_m3=summary["surface_final_m3"],
        network_m3=summary["network_final_m3"],
        outfall_net_m3=summary["outfall_net_m3"],
        exchanged_m3=summary["exchanged_m3"],
        outfall_gross_inflow_m3=summary["outfall_gross_inflow_m3"],
        pending_m3=summary["pending_m3"],
        lost_flooding_m3=lost if lost > 1e-9 else 0.0,
        network_inflow_m3=summary["network_inflow_m3"],
    )
    flags = [f for f in surface.flags if f not in ("balance_residual", "balance_gain")]
    percent = coupled.total_error_percent
    if not surface.open_boundary and abs(percent) > BALANCE_WARNING_PERCENT:
        flags.append("balance_residual")
    if surface.open_boundary and percent < -BALANCE_WARNING_PERCENT:
        flags.append("balance_gain")
    balance = {
        **dataclasses.asdict(coupled),
        "open_boundary": surface.open_boundary,
        "expected_rain_m3": surface.expected_rain_m3,
        "flags": flags,
    }
    exceeded = summary["overshoot_s"]
    coupling: dict[str, Any] = {
        "mode": job.settings.mode,
        "exchange_interval_s": job.settings.interval_s,
        "relaxation": job.settings.relaxation,
        "rim_tolerance_m": job.settings.rim_tolerance_m,
        "inlet": dataclasses.asdict(job.settings.inlet),
        "intervals": summary["intervals"],
        "overshoot_s": {"mean": exceeded["mean"], "max": exceeded["max"]},
        "capped_steps": sum(n["capped_steps"] for n in summary["nodes"]),
        "nodes_outside": [*job.outside, *job.no_coordinates],
    }
    if job.inflow is not None:
        coupling["inflow"] = {
            "path": str(job.inflow_path),
            "node": job.inflow_node,
            "volume_m3": job.inflow.volume_m3,
            "given_m3": summary["network_inflow_m3"],
            "duration_s": job.inflow.times_s[-1],
        }
    document = CoupleDocument(
        engine={
            "sfincs": {
                "library": library,
                "build_revision": run.build_revision,
                "qext_unit": qext_unit,
            },
            "swmm": {
                "name": "pyswmm",
                "version": extra_version("pyswmm"),
                "toolkit": extra_version("swmm-toolkit"),
            },
        },
        coupling=coupling,
        balance=balance,
        surface={
            "grid": describe_grid(run, stats),
            "depth": describe_depth(stats),
            "stations": describe_stations(read_stations(his) if his.is_file() else ()),
        },
        network={
            "duration_s": swmm["duration_s"],
            "totals": {
                key: swmm[key]
                for key in (
                    "external_inflow_m3",
                    "outflow_m3",
                    "flooding_m3",
                    "final_storage_m3",
                    "continuity_error_percent",
                )
            },
            "nodes": swmm["nodes"],
            "conduits": swmm["links"],
        },
        nodes=summary["nodes"],
        elapsed_s=elapsed_s,
        files=[],
    )
    document.notices.extend(_notices(job, summary, balance))
    return document


def couple_model(
    *,
    model: str | os.PathLike[str],
    network: str | os.PathLike[str] | None = None,
    inp: str | os.PathLike[str] | None = None,
    inflow: str | os.PathLike[str] | None = None,
    inflow_node: str | None = None,
    exchange_interval_s: int | None = None,
    mode: Mode | None = None,
    relaxation: float | None = None,
    rim_tolerance_m: float | None = None,
    node_area_m2: float | None = None,
    weir_coefficient: float | None = None,
    orifice_coefficient: float | None = None,
    routing_step_s: float | None = None,
    surcharge_method: Surcharge | None = None,
    output_dir: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> CoupleDocument | PlanDocument:
    """Run SFINCS and a SWMM network together; they exchange water every interval.

    The nodes of the network exchange water with the SFINCS cell they lie on. The
    coupling runs in a process of its own with the SFINCS library (``libsfincs``, built
    by you with ``--enable-shared``) and pyswmm; the files of the run are written to
    staging and reach ``output_dir`` only when it succeeded.

    Parameters
    ----------
    model : path-like
        The SFINCS model directory (``model build``), a regular grid.
    network, inp : path-like or None, optional
        A network table, or your own SWMM input in SI units; exactly one. The
        coordinates of the nodes are in the CRS of the model; the rim of a node must be
        within ``rim_tolerance_m`` of the bed of its cell. Your SWMM input is run with a
        fixed routing step, a clock that matches the model and the ``SurDepth`` of the
        mode (a notice lists them).
    inflow : path-like or None, optional
        Hydrograph table (``time_min``, ``discharge_m3s``; the table of a node of
        ``hydrolog route network``): water that comes from outside the model, for
        example from a catchment that the grid does not cover, and enters
        ``inflow_node``. Time is elapsed time from the start of the model run, as in
        the rain table; what lies beyond the end of the run is cut (a notice).
    inflow_node : str or None, optional
        The node that receives the inflow: a junction of a network table, any node of
        your SWMM input. It need not lie on the model. ``inflow`` and ``inflow_node``
        go together.
    exchange_interval_s : int or None, optional
        The exchange interval [s], a whole number; 1 when not given.
    mode : {"swmm_flooding", "coordinator"} or None, optional
        Who computes the spill from a full node: SWMM floods it and the volume returns
        to the cell (default), or the exchange law spills it with relaxation.
    relaxation : float or None, optional
        Weight of the new discharge, above 0 and at most 1; 1 (``swmm_flooding``) or
        0.1 (``coordinator``) when not given.
    rim_tolerance_m : float or None, optional
        Largest difference between a rim and its bed [m]; 0.1 when not given.
    node_area_m2, weir_coefficient, orifice_coefficient : float or None, optional
        The exchange law (Rubinato et al. 2017): the node area (also SWMM's
        ``MIN_SURFAREA``), ``C_w`` and ``C_o``; 1.167, 0.54 and 0.167 when not given.
    routing_step_s : float or None, optional
        SWMM's fixed routing step [s], at most 1; 0.5 when not given.
    surcharge_method : {"EXTRAN", "SLOT"} or None, optional
        Network table only: ``EXTRAN`` in ``swmm_flooding`` mode, ``SLOT`` in
        ``coordinator`` mode when not given.
    output_dir : path-like
        Directory for the results; created when missing.
    force : bool, optional
        Replace files that exist.
    check : bool, optional
        Plan without effects: the files, the nodes on the domain and what is missing.

    Returns
    -------
    CoupleDocument or PlanDocument
        ``hydraulik-couple/1`` with the water balance, the surface and network results
        and the exchange of every node, or the ``hydraulik-plan/1`` of ``check``.

    Raises
    ------
    InvalidInputError
        If the options do not go together, an inflow node is not in the network
        (``unknown_node``), no node lies on the domain (``no_exchange_nodes``) or a rim
        differs from its bed (``rim_mismatch``).
    NotFoundError
        If the model or the network does not exist.
    UnsupportedError
        If the model is not a regular grid in binary input mode, or the SWMM input is
        not in SI units.
    MissingDependencyError
        If the SFINCS library (``sfincs.library``) or pyswmm, numpy or netCDF4 is
        missing; this is checked before any work.
    EngineError
        If SFINCS or SWMM fails, or the run exceeds ``sfincs.timeout_s``.
    ConflictError
        If an output exists without ``force``, or the directory is inside a store.

    Examples
    --------
    >>> couple_model(model="no-such-model", network="n.csv", output_dir="out")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.NotFoundError: sfincs.inp not found: no-such-model/sfincs.inp
    """
    job = _prepare(
        model=model,
        network=network,
        inp=inp,
        inflow=inflow,
        inflow_node=inflow_node,
        exchange_interval_s=exchange_interval_s,
        mode=mode,
        relaxation=relaxation,
        rim_tolerance_m=rim_tolerance_m,
        node_area_m2=node_area_m2,
        weir_coefficient=weir_coefficient,
        orifice_coefficient=orifice_coefficient,
        routing_step_s=routing_step_s,
        surcharge_method=surcharge_method,
    )
    plan = plan_directory(output_dir, job.outputs, force=force)
    settings = load_settings()
    library = detect_sfincs_library(settings)
    if check:
        blockers = [extra_blocker(name) for name in missing_extras(_PACKAGES)]
        if not library.found:
            blockers.insert(0, blocker("engine_missing", library.detail, library.hint))
        steps = [
            f"read the SFINCS model {job.folder}: {job.duration_s:g} s, "
            f"{len(job.nodes)} of {len(job.nodes) + len(job.outside)} node(s) on "
            "an active cell",
            f"{'write' if job.kind == 'network' else 'patch'} {INP_NAME} "
            f"({job.settings.mode}, "
            f"SurDepth {0 if job.settings.mode == 'swmm_flooding' else 100})",
        ]
        if job.inflow is not None:
            lasts = job.inflow.times_s[-1]
            cut = (
                f"; it lasts {lasts:g} s and the run {job.duration_s:g} s, so the "
                "rest is cut"
                if lasts > job.duration_s
                else ""
            )
            steps.append(
                f"apply {job.inflow_path} ({job.inflow.volume_m3:.1f} m3) as the "
                f"inflow of {job.inflow_node}{cut}"
            )
        steps += [
            f"couple SFINCS ({library.location or 'library not found'}) and SWMM "
            f"every {job.settings.interval_s} s in a process of its own",
            f"write {', '.join(job.outputs)} and move them into {plan.directory}",
        ]
        return PlanDocument.from_write_plan(plan, steps=steps, blockers=blockers)
    if not library.found:
        raise MissingDependencyError(
            library.detail,
            details={"engine": "sfincs-library"},
            hint=library.hint,
            reason="engine_missing",
        )
    require_extras(*_PACKAGES)
    from hydraulik.coupling.process import run_worker
    from hydraulik.coupling.worker import CoupleJob

    qext_unit = str(settings.value("sfincs.qext_unit"))
    threads = settings.value("sfincs.threads")
    with Writer(plan) as writer:
        stage_model(job.folder, writer.staging, job.outputs)
        patch_inp(
            writer.staging,
            {
                "dtmax": min(
                    float(job.sfincs_inp.get("dtmax", "60")),
                    float(job.settings.interval_s),
                )
            },
        )
        staged_inp = writer.staged_path(INP_NAME)
        staged_inp.write_text(job.text, encoding="utf-8")
        job_file = writer.staging / JOB_NAME
        job_file.write_text(
            CoupleJob(
                library=str(library.location),
                qext_unit=qext_unit,
                directory=str(writer.staging),
                inp=str(staged_inp),
                report=str(writer.staged_path(REPORT_NAME)),
                out=str(writer.staging / "network.out"),
                nodes=job.nodes,
                settings=job.settings,
                inflows=(
                    {}
                    if job.inflow is None or job.inflow_node is None
                    else {job.inflow_node: job.inflow}
                ),
            ).to_json(),
            encoding="utf-8",
        )
        started = time.monotonic()
        summary = run_worker(
            writer.staging,
            job_file,
            timeout_s=float(settings.value("sfincs.timeout_s")),
            threads=None if threads is None else int(threads),
        )
        document = _document(
            job,
            summary,
            writer.staging,
            library=library.location,
            qext_unit=qext_unit,
            elapsed_s=time.monotonic() - started,
        )
        document.files = file_dicts(writer.commit())
    return document
