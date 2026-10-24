"""The coupling loop: a SFINCS surface and a SWMM network exchange volumes (ADR-0005).

The loop is the explicit scheme of the feasibility test (extraction note 3), one
exchange interval ``dt_c`` at a time:

1. read the water level ``zs`` of every exchange cell and the head ``H`` of its node;
2. compute the exchange discharge ``Q`` (positive from the surface into the network)
   with :func:`~hydraulik.coupling.laws.exchange_discharge_m3s`, relax it, and limit
   what is taken from a cell to the water that stands there over the longest interval
   SFINCS may take (it clips the level at the bed and would create water);
3. impose ``-Q`` on the cell and advance SFINCS to the end of the interval; SFINCS
   overshoots the target by up to one adaptive step, so the volume that left the surface
   is ``V = Q * (t_new - t_old)``;
4. give SWMM exactly ``V / dt_c`` as lateral inflow and advance it by ``dt_c``;
5. hand back what SWMM flooded out of a full node: in ``swmm_flooding`` mode the node
   has no surcharge depth, SWMM floods it and the flooded volume returns to the cell
   over the next interval; in ``coordinator`` mode the node holds the water and the
   exchange law itself spills it (a negative ``Q``).

Exchanging volumes instead of rates makes the interface mass-conservative by
construction; what remains is a time shift of at most one SFINCS step.

The loop knows two small protocols, :class:`Surface` and :class:`Network`, not the
engines: :class:`~hydraulik.engines.sfincs.bmi.SfincsSurface` and
:class:`~hydraulik.engines.swmm.run.SwmmStepper` implement them, and the tests drive the
loop with fakes.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

from hydraulik.coupling.laws import (
    Inlet,
    exchange_discharge_m3s,
    limit_to_available_water,
    relax,
)
from hydraulik.exceptions import EngineError, InvalidInputError

__all__ = [
    "CouplerResult",
    "CouplerSettings",
    "ExchangeNode",
    "Mode",
    "Network",
    "NodeResult",
    "Surface",
    "couple",
]

logger = logging.getLogger(__name__)

Mode = Literal["swmm_flooding", "coordinator"]

_EPS: Final = 1e-9


class Surface(Protocol):
    """The surface model: a grid of cells with a bed, a level and an external source."""

    @property
    def time_s(self) -> float:
        """float: model time [s from the start]."""

    @property
    def end_s(self) -> float:
        """float: end of the simulation [s from the start]."""

    @property
    def max_step_s(self) -> float:
        """float: the longest time step the model may take [s]."""

    def locate(self, x_m: float, y_m: float) -> int | None:
        """Return the cell that holds a point, or ``None`` outside the domain."""

    def bed_m(self, cell: int) -> float:
        """Return the bed level of a cell [m]."""

    def level_m(self, cell: int) -> float:
        """Return the water level of a cell [m]."""

    def area_m2(self, cell: int) -> float:
        """Return the area of a cell [m2]."""

    def set_source_m3s(self, cell: int, discharge_m3s: float) -> None:
        """Set the water that enters a cell from outside [m3/s]; it stays in force."""

    def advance_to(self, time_s: float) -> float:
        """Advance to ``time_s`` and return the time reached (at least that)."""

    def stored_volume_m3(self) -> float:
        """Return the water on the surface [m3]."""


class Network(Protocol):
    """The sewer network: nodes with a head and a rim, advanced in whole strides."""

    @property
    def stride_s(self) -> int:
        """int: seconds one :meth:`advance` covers."""

    @property
    def time_s(self) -> float:
        """float: elapsed simulated time [s]."""

    def head_m(self, name: str) -> float:
        """Return the hydraulic head of a node [m]."""

    def rim_m(self, name: str) -> float:
        """Return the rim of a node [m]."""

    def add_inflow(self, name: str, discharge_m3s: float) -> None:
        """Set the lateral inflow of a node for the next strides [m3/s]."""

    def flooding_volume_m3(self, name: str) -> float:
        """Return the water that flooded out of a node since the start [m3]."""

    def outfall_flow_m3s(self) -> float:
        """Return the flow out of the network through the outfalls [m3/s]."""

    def stored_volume_m3(self) -> float:
        """Return the water in the network [m3]."""

    def advance(self) -> bool:
        """Advance one stride; False when that stride ended the run."""


@dataclass(frozen=True)
class ExchangeNode:
    """A node of the network that may exchange water with the surface.

    Attributes
    ----------
    name : str
        Node name in the network.
    x_m, y_m : float
        Position in the CRS of the surface model [m].
    """

    name: str
    x_m: float
    y_m: float


@dataclass(frozen=True)
class CouplerSettings:
    """How the loop runs.

    Attributes
    ----------
    interval_s : int
        The exchange interval ``dt_c`` [s], a whole multiple of the network stride.
    mode : {"swmm_flooding", "coordinator"}
        Who computes the spill from a full node (module text).
    relaxation : float
        ``w`` in (0, 1]: the discharge is ``w Q + (1 - w) Q_previous``; 1 is none.
    rim_tolerance_m : float
        Largest difference between the rim of a node and the bed of its cell [m].
    inlet : Inlet
        Geometry and coefficients of the exchange law, the same for every node.
    """

    interval_s: int = 1
    mode: Mode = "swmm_flooding"
    relaxation: float = 1.0
    rim_tolerance_m: float = 0.1
    inlet: Inlet = field(default_factory=Inlet)


@dataclass
class NodeResult:
    """What happened at one exchange node.

    Attributes
    ----------
    name : str
        Node name.
    cell : int
        Position of its cell in the arrays of the surface.
    ground_m : float
        Bed level of the cell [m], the ground the exchange law measures depth from.
    zs_m, head_m : list of float
        Water level of the cell and head of the node at the end of each interval [m].
    exchange_m3s : list of float
        Net discharge from the surface into the network in each interval [m3/s]
        (negative: water returned to the surface).
    spill_m3s : list of float
        Water returned to the surface from SWMM's flooding in each interval [m3/s].
    exchanged_m3 : float
        Net volume from the surface into the network [m3].
    flooded_m3 : float
        Volume SWMM flooded out of the node [m3].
    returned_m3 : float
        Volume handed back to the surface [m3].
    pending_m3 : float
        Flooded but not yet handed back at the end [m3].
    capped_steps : int
        Intervals in which the discharge was cut to the water in the cell.
    """

    name: str
    cell: int
    ground_m: float = 0.0
    zs_m: list[float] = field(default_factory=list)
    head_m: list[float] = field(default_factory=list)
    exchange_m3s: list[float] = field(default_factory=list)
    spill_m3s: list[float] = field(default_factory=list)
    exchanged_m3: float = 0.0
    flooded_m3: float = 0.0
    returned_m3: float = 0.0
    pending_m3: float = 0.0
    capped_steps: int = 0


@dataclass
class CouplerResult:
    """The outcome of a coupled run.

    Attributes
    ----------
    times_s, surface_times_s : list of float
        End of each interval, and the time SFINCS reached [s].
    nodes : list of NodeResult
        The exchange nodes.
    outside : list of str
        Nodes that lie outside the active domain and exchange nothing.
    outfall_net_m3, outfall_gross_inflow_m3 : float
        Net volume through the outfalls (positive: left the network), and the volume
        that entered the network from them [m3].
    surface_final_m3, network_final_m3 : float
        Water on the surface and in the network at the end [m3].
    """

    times_s: list[float] = field(default_factory=list)
    surface_times_s: list[float] = field(default_factory=list)
    nodes: list[NodeResult] = field(default_factory=list)
    outside: list[str] = field(default_factory=list)
    outfall_net_m3: float = 0.0
    outfall_gross_inflow_m3: float = 0.0
    surface_final_m3: float = 0.0
    network_final_m3: float = 0.0

    @property
    def intervals(self) -> int:
        """int: the number of exchange intervals that ran."""
        return len(self.times_s)

    @property
    def overshoot_s(self) -> list[float]:
        """List of float: how far SFINCS went beyond the end of each interval [s]."""
        return [
            reached - target
            for reached, target in zip(self.surface_times_s, self.times_s, strict=True)
        ]

    @property
    def exchanged_m3(self) -> float:
        """float: net volume from the surface into the network, all nodes [m3]."""
        return sum(node.exchanged_m3 for node in self.nodes)

    @property
    def pending_m3(self) -> float:
        """float: flooded by SWMM and not yet back on the surface, all nodes [m3]."""
        return sum(node.pending_m3 for node in self.nodes)

    @property
    def flooded_m3(self) -> float:
        """float: SWMM's flooding at the exchange nodes [m3]."""
        return sum(node.flooded_m3 for node in self.nodes)


def _check_settings(network: Network, settings: CouplerSettings) -> None:
    """Refuse settings the loop cannot honour."""
    if settings.interval_s < 1 or settings.interval_s % network.stride_s != 0:
        raise InvalidInputError(
            f"the exchange interval is {settings.interval_s} s; it must be a whole "
            f"multiple of the {network.stride_s} s stride of the network",
            details={"option": "exchange_interval_s", "value": settings.interval_s},
            reason="out_of_range",
        )
    if not 0.0 < settings.relaxation <= 1.0:
        raise InvalidInputError(
            f"the relaxation is {settings.relaxation:g}; it must be above 0 and at "
            "most 1",
            details={"option": "relaxation", "value": settings.relaxation},
            reason="out_of_range",
        )


def couple(
    surface: Surface,
    network: Network,
    nodes: Sequence[ExchangeNode],
    settings: CouplerSettings,
) -> CouplerResult:
    """Run the coupled simulation to the end of the surface model.

    Parameters
    ----------
    surface : Surface
        The surface model, started and not yet advanced.
    network : Network
        The network, opened and not yet advanced; its run must end with the surface's.
    nodes : sequence of ExchangeNode
        The nodes that may exchange water with the surface.
    settings : CouplerSettings
        Interval, mode, relaxation, tolerance and the exchange law.

    Returns
    -------
    CouplerResult
        The series of every node and the volumes of the run. Neither engine is
        finalised: the caller does that (SWMM's report, SFINCS's last output).

    Raises
    ------
    InvalidInputError
        If the settings are out of range, no node lies on an active cell
        (``no_exchange_nodes``), or the rim of a node differs from the bed of its cell
        by more than the tolerance (``rim_mismatch``, every offending node is listed).
        No step has been taken then.
    EngineError
        If SFINCS does not advance, or SWMM ends or lags behind the exchange interval.
    """
    _check_settings(network, settings)
    result = CouplerResult()
    cells: dict[str, int] = {}
    for node in nodes:
        cell = surface.locate(node.x_m, node.y_m)
        if cell is None:
            result.outside.append(node.name)
        else:
            cells[node.name] = cell
    if not cells:
        raise InvalidInputError(
            "no node of the network lies on an active cell of the surface model",
            details={"nodes": [node.name for node in nodes][:50]},
            hint="Check that the network and the model use the same CRS, and that the "
            "domain of the model covers the nodes.",
            reason="no_exchange_nodes",
        )
    grounds = {name: surface.bed_m(cell) for name, cell in cells.items()}
    mismatched = [
        {
            "node": name,
            "rim_m": round(network.rim_m(name), 4),
            "bed_m": round(grounds[name], 4),
        }
        for name in cells
        if abs(network.rim_m(name) - grounds[name]) > settings.rim_tolerance_m
    ]
    if mismatched:
        raise InvalidInputError(
            f"the rim of {len(mismatched)} node(s) differs from the bed of the cell "
            f"by more than {settings.rim_tolerance_m:g} m, for example "
            f"{mismatched[0]['node']}: rim {mismatched[0]['rim_m']} m, bed "
            f"{mismatched[0]['bed_m']} m",
            details={
                "nodes": mismatched[:50],
                "rim_tolerance_m": settings.rim_tolerance_m,
            },
            hint="Set the rim of each node to the bed of its cell, or raise "
            "--rim-tolerance-m: the exchange law measures the surface depth from "
            "the bed.",
            reason="rim_mismatch",
        )
    by_cell: dict[int, list[str]] = {}
    for name, cell in cells.items():
        by_cell.setdefault(cell, []).append(name)
    results = {
        name: NodeResult(name, cell, grounds[name]) for name, cell in cells.items()
    }
    result.nodes = list(results.values())

    flooding_mode = settings.mode == "swmm_flooding"
    interval = float(settings.interval_s)
    window_s = interval + surface.max_step_s
    stride = network.stride_s
    end_s = surface.end_s
    previous = dict.fromkeys(cells, 0.0)
    pending = dict.fromkeys(cells, 0.0)
    flooded_seen = dict.fromkeys(cells, 0.0)
    outfall_flow = 0.0
    k = 0
    while k * interval < end_s - _EPS:
        target_s = min((k + 1) * interval, end_s)
        length_s = target_s - k * interval
        start_s = surface.time_s
        spill = {
            name: pending[name] / length_s if flooding_mode else 0.0 for name in cells
        }
        discharge: dict[str, float] = {}
        for name, cell in cells.items():
            law = exchange_discharge_m3s(
                settings.inlet,
                surface.level_m(cell),
                grounds[name],
                network.head_m(name),
            )
            if flooding_mode:
                law = max(law, 0.0)  # spills come from SWMM's flooding, not from here
            discharge[name] = relax(law, previous[name], settings.relaxation)
        for cell, names in by_cell.items():
            wanted = sum(max(discharge[name], 0.0) for name in names)
            allowed, limited = limit_to_available_water(
                wanted,
                surface.level_m(cell) - surface.bed_m(cell),
                surface.area_m2(cell),
                window_s,
            )
            if limited:
                for name in names:
                    if discharge[name] > 0.0:
                        discharge[name] *= allowed / wanted
                        results[name].capped_steps += 1
            surface.set_source_m3s(
                cell, sum(spill[name] - discharge[name] for name in names)
            )
        previous.update(discharge)

        reached_s = surface.advance_to(target_s)
        advanced_s = reached_s - start_s
        if advanced_s <= 0.0:
            raise EngineError(
                f"SFINCS did not advance: it was at {start_s:g} s and is at "
                f"{reached_s:g} s after a call to {target_s:g} s",
                details={"time_s": start_s, "target_s": target_s},
                reason="bmi_failed",
            )
        for name in cells:
            taken = discharge[name] * advanced_s
            returned = spill[name] * advanced_s
            record = results[name]
            pending[name] -= returned
            record.returned_m3 += returned
            record.exchanged_m3 += taken - returned
            network.add_inflow(name, taken / length_s)

        ended = False
        for _ in range(round(length_s / stride)):
            running = network.advance()
            flow = network.outfall_flow_m3s()
            volume = 0.5 * (outfall_flow + flow) * stride  # trapezoid, as SWMM books it
            result.outfall_net_m3 += volume
            result.outfall_gross_inflow_m3 += max(-volume, 0.0)
            outfall_flow = flow
            if not running:  # SWMM says so on the stride that reaches its end
                ended = True
                break
        if abs(network.time_s - target_s) > 1e-6 or (ended and target_s < end_s - _EPS):
            raise EngineError(
                f"SWMM is at {network.time_s:g} s, the exchange interval ends at "
                f"{target_s:g} s",
                details={"swmm_s": network.time_s, "target_s": target_s},
                hint="The SWMM run must last as long as the SFINCS run.",
                reason="swmm_time",
            )
        for name in cells:
            flooded = network.flooding_volume_m3(name)
            if flooding_mode:
                pending[name] += flooded - flooded_seen[name]
            flooded_seen[name] = flooded
        result.times_s.append(target_s)
        result.surface_times_s.append(reached_s)
        for name, cell in cells.items():
            record = results[name]
            record.zs_m.append(surface.level_m(cell))
            record.head_m.append(network.head_m(name))
            record.exchange_m3s.append(discharge[name] - spill[name])
            record.spill_m3s.append(spill[name])
        k += 1
    for name in cells:
        results[name].flooded_m3 = flooded_seen[name]
        results[name].pending_m3 = pending[name]
    result.surface_final_m3 = surface.stored_volume_m3()
    result.network_final_m3 = network.stored_volume_m3()
    logger.info(
        "coupled %d intervals of %g s, %d node(s) outside the domain",
        result.intervals,
        interval,
        len(result.outside),
    )
    return result
