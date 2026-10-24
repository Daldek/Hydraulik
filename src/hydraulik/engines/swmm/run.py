"""Running a SWMM input through pyswmm and reading what it computed (ADR-0002).

SWMM is the engine that comes with the ``pyswmm`` wheel (extra ``swmm``); nothing is
installed or found elsewhere. :class:`SwmmStepper` advances one simulation in strides of
whole seconds (the unit of ``Simulation.step_advance``). A plain run
(:func:`run_swmm`) and the coupler (:mod:`hydraulik.coupling.coupler`) drive the same
object, so what the coupler reads (heads, flooding, the flow through the outfalls) is
what a run reports.

All quantities are metric: the input must say ``FLOW_UNITS CMS``. Volumes in
``statistics`` are in cubic metres; ``routing_stats["final_storage"]`` of pyswmm is in
cubic feet whatever the unit of the file, so the storage is summed from the volumes of
nodes and links instead.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from hydraulik._optional import require
from hydraulik.data.tables import Hydrograph
from hydraulik.engines.swmm import inp as inp_module
from hydraulik.exceptions import InputDataError, InvalidInputError, NotFoundError

__all__ = [
    "SwmmLinkStats",
    "SwmmNodeStats",
    "SwmmStepper",
    "SwmmSummary",
    "run_swmm",
]

logger = logging.getLogger(__name__)

_ERROR_LINE = re.compile(r"^\s*ERROR\s+\d+:.*$", re.MULTILINE)


@dataclass(frozen=True)
class SwmmNodeStats:
    """What SWMM reports of one node.

    Attributes
    ----------
    name : str
        Node name.
    kind : {"junction", "outfall", "storage", "divider"}
        Type of the node.
    max_depth_m, max_head_m : float
        Largest depth above the invert and largest head [m].
    peak_inflow_m3s : float
        Largest total inflow [m3/s].
    peak_flooding_m3s, flooding_volume_m3, flooding_hours : float
        Largest flooding rate [m3/s], flooded volume [m3] and duration [h]; SWMM
        floods a node whose water rises above its rim plus ``SurDepth``.
    """

    name: str
    kind: str
    max_depth_m: float
    max_head_m: float
    peak_inflow_m3s: float
    peak_flooding_m3s: float
    flooding_volume_m3: float
    flooding_hours: float

    @property
    def flooded(self) -> bool:
        """bool: True when the node flooded at all."""
        return self.flooding_volume_m3 > 0.0


@dataclass(frozen=True)
class SwmmLinkStats:
    """What SWMM reports of one conduit.

    Attributes
    ----------
    name : str
        Link name.
    peak_flow_m3s : float
        Largest flow [m3/s].
    peak_velocity_ms : float
        Largest velocity [m/s].
    peak_depth_m : float
        Largest depth [m].
    surcharged_hours : float
        Time the conduit was surcharged [h].
    """

    name: str
    peak_flow_m3s: float
    peak_velocity_ms: float
    peak_depth_m: float
    surcharged_hours: float


@dataclass(frozen=True)
class SwmmSummary:
    """The result of a finished SWMM run.

    Attributes
    ----------
    duration_s : float
        Simulated time [s].
    external_inflow_m3, outflow_m3, flooding_m3 : float
        Water that entered at nodes (the inflows given to the run), left through the
        outfalls and flooded out of nodes [m3].
    final_storage_m3 : float
        Water in nodes and conduits at the end [m3].
    continuity_error_percent : float
        SWMM's own flow-routing continuity error [percent].
    nodes : tuple of SwmmNodeStats
        Every node.
    links : tuple of SwmmLinkStats
        Every conduit.
    """

    duration_s: float
    external_inflow_m3: float
    outflow_m3: float
    flooding_m3: float
    final_storage_m3: float
    continuity_error_percent: float
    nodes: tuple[SwmmNodeStats, ...]
    links: tuple[SwmmLinkStats, ...]


def _opening_error(report: Path, exc: Exception) -> InputDataError:
    """Turn the bare exception of pyswmm into an error that quotes the report."""
    text = ""
    if report.is_file():
        text = report.read_text(encoding="utf-8", errors="replace")
    errors = [line.strip() for line in _ERROR_LINE.findall(text)]
    shown = errors[:5] or [str(exc).strip() or "SWMM could not open the input"]
    return InputDataError(
        shown[0],
        details={"report": str(report), "errors": shown},
        hint="Fix the input file; the report lists every error SWMM found.",
        reason="invalid_inp",
    )


class SwmmStepper:
    """One SWMM simulation, advanced in strides of whole seconds.

    Use as a context manager; :meth:`finish` ends the run, writes the report and returns
    the summary, and leaving the block closes SWMM whatever happened.

    Parameters
    ----------
    inp : str or Path
        The SWMM input (``FLOW_UNITS CMS``).
    report, out : str or Path
        Where SWMM writes its text report and its binary output.
    stride_s : int, optional
        Length of one step of :meth:`advance` [s]; SWMM's routing step may be smaller.

    Raises
    ------
    MissingDependencyError
        If pyswmm is not installed (extra ``swmm``).
    NotFoundError
        If the input does not exist.
    UnsupportedError
        If the input is not in SI units (reason ``flow_units``).
    InputDataError
        If SWMM cannot open the input (reason ``invalid_inp``).
    InvalidInputError
        If ``stride_s`` is not a positive whole number.
    """

    def __init__(
        self,
        inp: str | Path,
        report: str | Path,
        out: str | Path,
        *,
        stride_s: int = 1,
    ) -> None:
        if isinstance(stride_s, bool) or not isinstance(stride_s, int) or stride_s < 1:
            raise InvalidInputError(
                "the stride of SWMM is a whole number of seconds, at least 1",
                details={"option": "stride_s", "value": str(stride_s)},
                reason="out_of_range",
            )
        source = Path(inp)
        if not source.is_file():
            raise NotFoundError(
                f"SWMM input not found: {source}",
                details={"path": str(source)},
                reason="path_missing",
            )
        pyswmm = require("pyswmm", "swmm")
        inp_module.require_metric(source.read_text(encoding="utf-8", errors="replace"))
        self.stride_s = stride_s
        self._closed = False
        self._finished = False
        self._ended = False
        try:
            self._sim: Any = pyswmm.Simulation(str(source), str(report), str(out))
        except Exception as exc:  # noqa: BLE001 - pyswmm raises a bare Exception
            raise _opening_error(Path(report), exc) from exc
        try:
            self._sim.step_advance(stride_s)
            self._sim.start()
            # pyswmm's containers are iterators that run dry: read each once
            self._nodes: dict[str, Any] = {n.nodeid: n for n in pyswmm.Nodes(self._sim)}
            self._links: dict[str, Any] = {k.linkid: k for k in pyswmm.Links(self._sim)}
            self._pyswmm = pyswmm
            self._start = self._sim.start_time
            self.end_s = (self._sim.end_time - self._start).total_seconds()
            self._outfall_in: list[Any] = []
            self._outfall_out: list[Any] = []
            outfalls = {n for n, node in self._nodes.items() if node.is_outfall()}
            for link in self._links.values():
                upstream, downstream = link.connections
                if downstream in outfalls:
                    self._outfall_in.append(link)
                elif upstream in outfalls:
                    self._outfall_out.append(link)
        except BaseException:
            self._sim.close()
            self._closed = True
            raise

    def __enter__(self) -> SwmmStepper:
        """Return the stepper."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close SWMM if :meth:`finish` did not."""
        self.close()

    def close(self) -> None:
        """Close the simulation (no report is written); safe to call twice."""
        if not self._closed:
            self._sim.close()
            self._closed = True

    @property
    def time_s(self) -> float:
        """float: elapsed simulated time [s]."""
        return float((self._sim.current_time - self._start).total_seconds())

    @property
    def ended(self) -> bool:
        """bool: True when SWMM reached the end of the run."""
        return self._ended

    def _node(self, name: str) -> Any:
        """Return the pyswmm object of a node."""
        return self._nodes[name]

    @property
    def node_names(self) -> tuple[str, ...]:
        """Tuple of str: every node of the model."""
        return tuple(self._nodes)

    def advance(self) -> bool:
        """Advance SWMM by one stride.

        Returns
        -------
        bool
            True when SWMM can go on, False when this stride ended the run.
        """
        try:
            next(self._sim)
        except StopIteration:
            self._ended = True
            return False
        return True

    def head_m(self, name: str) -> float:
        """Return the hydraulic head of a node [m]."""
        return float(self._node(name).head)

    def rim_m(self, name: str) -> float:
        """Return the rim of a node, invert plus full depth [m]."""
        node = self._node(name)
        return float(node.invert_elevation + node.full_depth)

    def add_inflow(self, name: str, discharge_m3s: float) -> None:
        """Set the lateral inflow of a node for the next stride [m3/s].

        The value replaces the previous one; a negative value takes water out.
        """
        self._node(name).generated_inflow(discharge_m3s)

    def flooding_volume_m3(self, name: str) -> float:
        """Return the water that flooded out of a node since the start [m3]."""
        return float(self._node(name).statistics["flooding_volume"])

    def outfall_flow_m3s(self) -> float:
        """Return the flow out of the network through the outfalls [m3/s].

        Positive leaves the network; a backwater from the receiving water is negative.
        """
        leaving = sum(float(link.flow) for link in self._outfall_in)
        entering = sum(float(link.flow) for link in self._outfall_out)
        return leaving - entering

    def stored_volume_m3(self) -> float:
        """Return the water in all nodes and conduits now [m3]."""
        return sum(float(node.volume) for node in self._nodes.values()) + sum(
            float(link.volume) for link in self._links.values()
        )

    def finish(self) -> SwmmSummary:
        """End the run: write the report, read the statistics, close SWMM.

        Returns
        -------
        SwmmSummary
            Totals, node and conduit statistics and the continuity error.
        """
        stats = self._pyswmm.SystemStats(self._sim).routing_stats
        nodes = tuple(self._node_stats(node) for node in self._nodes.values())
        links = tuple(
            self._link_stats(link) for link in self._links.values() if link.is_conduit()
        )
        summary = SwmmSummary(
            duration_s=self.time_s,
            external_inflow_m3=float(stats["external_inflow"]),
            outflow_m3=float(stats["outflow"]),
            flooding_m3=float(stats["flooding"]),
            final_storage_m3=self.stored_volume_m3(),
            continuity_error_percent=float(stats["routing_error"]),
            nodes=nodes,
            links=links,
        )
        self._sim.report()
        self._sim.close()
        self._closed = True
        self._finished = True
        return summary

    @staticmethod
    def _node_stats(node: Any) -> SwmmNodeStats:
        stats = node.statistics
        kind = (
            "outfall"
            if node.is_outfall()
            else "storage"
            if node.is_storage()
            else "divider"
            if node.is_divider()
            else "junction"
        )
        return SwmmNodeStats(
            name=node.nodeid,
            kind=kind,
            max_depth_m=float(stats["max_depth"]),
            max_head_m=float(node.invert_elevation + stats["max_depth"]),
            peak_inflow_m3s=float(stats["peak_total_inflow"]),
            peak_flooding_m3s=float(stats["peak_flooding_rate"]),
            flooding_volume_m3=float(stats["flooding_volume"]),
            flooding_hours=float(stats["flooding_duration"]),
        )

    @staticmethod
    def _link_stats(link: Any) -> SwmmLinkStats:
        stats = link.conduit_statistics
        return SwmmLinkStats(
            name=link.linkid,
            peak_flow_m3s=float(stats["peak_flow"]),
            peak_velocity_ms=float(stats["peak_velocity"]),
            peak_depth_m=float(stats["peak_depth"]),
            surcharged_hours=float(stats["time_surcharged"]),
        )


def run_swmm(
    inp: str | Path,
    report: str | Path,
    out: str | Path,
    *,
    inflows: Mapping[str, Hydrograph] | None = None,
    stride_s: int = 1,
) -> SwmmSummary:
    """Run a SWMM input to its end, with optional inflow hydrographs at nodes.

    Each inflow is applied as the lateral inflow of its node, at the value of the
    hydrograph in the middle of every stride (so the volume is that of the series).

    Parameters
    ----------
    inp : str or Path
        The SWMM input (``FLOW_UNITS CMS``).
    report, out : str or Path
        Where SWMM writes its report and its binary output.
    inflows : Mapping[str, Hydrograph] or None, optional
        Node name to the discharge hydrograph [m3/s] that enters there; time is
        elapsed time from the start of the run.
    stride_s : int, optional
        Length of one step [s].

    Returns
    -------
    SwmmSummary
        The totals and the statistics of the run.

    Raises
    ------
    InvalidInputError
        If an inflow names a node that is not in the model (reason ``unknown_node``).
    NotFoundError, UnsupportedError, InputDataError, MissingDependencyError
        As :class:`SwmmStepper`.
    """
    with SwmmStepper(inp, report, out, stride_s=stride_s) as stepper:
        wanted = dict(inflows or {})
        unknown = sorted(set(wanted) - set(stepper.node_names))
        if unknown:
            raise InvalidInputError(
                f"the model has no node {', '.join(unknown)}",
                details={"option": "inflow_node", "value": unknown[0]},
                hint="Node names are those of the SWMM input or the network table.",
                reason="unknown_node",
            )
        while True:
            middle = stepper.time_s + stepper.stride_s / 2.0
            for name, series in wanted.items():
                stepper.add_inflow(name, series.at(middle))
            if not stepper.advance():
                break
        return stepper.finish()
