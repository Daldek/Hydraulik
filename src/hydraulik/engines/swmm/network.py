"""A sewer network as data, and its SWMM input file (ADR-0002).

The network of a model comes from a table (:func:`read_network_table`) or from an INP
file that the user wrote (:mod:`hydraulik.engines.swmm.inp`). This module covers the
table: junctions with a position, a rim and a depth, conduits to the downstream node,
one outfall. :func:`write_inp` renders it for SWMM 5.2 with the settings that the
coupling experiment found stable (README 2.2, 7.2):

* dynamic wave routing with a fixed routing step (default 0.5 s), ``EXTRAN`` or ``SLOT``
  for pressurised flow;
* junction ``SurDepth`` 0 when SWMM floods and the coupler hands the volume back to
  the surface (``spill="swmm_flooding"``), or 100 m so that SWMM never floods by
  itself and the coupler computes the spill (``spill="coordinator"``);
* ``MIN_SURFAREA`` set explicitly (the node area of the exchange law);
* local losses at the ends of every conduit with non-zero defaults, because without
  them a short conduit carries about 30 percent too much (README 7.2);
* an optional flap gate on the outfall and a stage time series for a backwater.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Literal

from hydraulik.exceptions import InputDataError, InvalidInputError, NotFoundError

__all__ = [
    "NETWORK_COLUMNS",
    "SWMM_START",
    "Conduit",
    "Junction",
    "Network",
    "Outfall",
    "SwmmSettings",
    "read_network_table",
    "write_inp",
]

SWMM_START: Final = datetime(2000, 1, 1)
"""Start of every SWMM run: model times are seconds from here, as for SFINCS."""

NETWORK_COLUMNS: Final = ("name", "x_m", "y_m", "rim_m", "depth_m", "to", "diameter_m")
"""Required columns of a network table; ``roughness``, ``length_m``, ``entry_loss`` and
``exit_loss`` are optional."""

Spill = Literal["swmm_flooding", "coordinator"]
Surcharge = Literal["EXTRAN", "SLOT"]


@dataclass(frozen=True)
class Junction:
    """A manhole or an inlet of the network.

    Attributes
    ----------
    name : str
        Name without spaces.
    x_m, y_m : float
        Position in the CRS of the SFINCS grid [m]; it picks the exchange cell.
    rim_m : float
        Elevation of the rim, the ground [m].
    depth_m : float
        Depth of the node below the rim [m]; the invert is ``rim_m - depth_m``.
    """

    name: str
    x_m: float
    y_m: float
    rim_m: float
    depth_m: float

    @property
    def invert_m(self) -> float:
        """float: elevation of the invert [m]."""
        return self.rim_m - self.depth_m


@dataclass(frozen=True)
class Conduit:
    """A circular conduit between two nodes.

    Attributes
    ----------
    name : str
        Name without spaces.
    from_node, to_node : str
        Upstream and downstream node.
    length_m : float
        Length [m].
    diameter_m : float
        Diameter [m].
    roughness : float
        Manning ``n`` [s/m^(1/3)].
    entry_loss, exit_loss : float
        Local loss coefficients at the inlet and the outlet [-].
    """

    name: str
    from_node: str
    to_node: str
    length_m: float
    diameter_m: float
    roughness: float = 0.013
    entry_loss: float = 0.5
    exit_loss: float = 1.0


@dataclass(frozen=True)
class Outfall:
    """The outfall of the network.

    Attributes
    ----------
    name : str
        Name without spaces.
    x_m, y_m : float
        Position [m].
    invert_m : float
        Elevation of the invert [m].
    stage_series : tuple of (float, float)
        ``(time_s, stage_m)`` pairs of an imposed water level (backwater); empty
        for a free outfall.
    gated : bool
        True for a flap gate that stops the flow from the receiving water.
    """

    name: str
    x_m: float
    y_m: float
    invert_m: float
    stage_series: tuple[tuple[float, float], ...] = ()
    gated: bool = False


@dataclass(frozen=True)
class Network:
    """Junctions, conduits and the outfall of a sewer network.

    Attributes
    ----------
    junctions : tuple of Junction
        The nodes that exchange water with the surface.
    conduits : tuple of Conduit
        The links; every junction drains through exactly one.
    outfall : Outfall
        The downstream end.
    title : str
        Free text for the ``[TITLE]`` of the file.
    """

    junctions: tuple[Junction, ...]
    conduits: tuple[Conduit, ...]
    outfall: Outfall
    title: str = "Hydraulik network"
    _names: frozenset[str] = field(
        init=False, repr=False, compare=False, default=frozenset()
    )

    def __post_init__(self) -> None:
        """Check that node names are unique and every conduit finds its nodes."""
        names = [j.name for j in self.junctions] + [self.outfall.name]
        if len(set(names)) != len(names):
            raise InputDataError(
                "node names of the network are not unique",
                details={"names": sorted({n for n in names if names.count(n) > 1})},
                reason="duplicate_node",
            )
        object.__setattr__(self, "_names", frozenset(names))
        for conduit in self.conduits:
            for node in (conduit.from_node, conduit.to_node):
                if node not in self._names:
                    raise InputDataError(
                        f"conduit {conduit.name} refers to the unknown node {node}",
                        details={"conduit": conduit.name, "node": node},
                        reason="unknown_node",
                    )

    @property
    def exchange_nodes(self) -> dict[str, tuple[float, float]]:
        """dict: junction name to its position ``(x_m, y_m)``."""
        return {j.name: (j.x_m, j.y_m) for j in self.junctions}


@dataclass(frozen=True)
class SwmmSettings:
    """Options of a SWMM run.

    Attributes
    ----------
    duration_s : float
        Length of the run [s].
    routing_step_s : float
        Fixed routing step [s]; 0.5 s removed the residual oscillation (README 3.8).
    surcharge_method : {"EXTRAN", "SLOT"}
        Method for pressurised flow. ``SLOT`` loses 2 to 17 percent of the water in
        sustained pressurised flow, ``EXTRAN`` diverges under explicit coupling unless
        SWMM floods (README 3.10).
    spill : {"swmm_flooding", "coordinator"}
        Who computes the spill from a full node (see the module text).
    min_surface_area_m2 : float
        ``MIN_SURFAREA``, the node area [m2].
    """

    duration_s: float
    routing_step_s: float = 0.5
    surcharge_method: Surcharge = "EXTRAN"
    spill: Spill = "swmm_flooding"
    min_surface_area_m2: float = 1.167


def _fail(row: int, column: str, why: str, value: object) -> InputDataError:
    return InputDataError(
        f"network table, row {row}, column {column}: {why}",
        details={"row": row, "column": column, "value": str(value)},
        hint=f"Columns: {', '.join(NETWORK_COLUMNS)} (optional: roughness, length_m, "
        "entry_loss, exit_loss).",
        reason="invalid_network_table",
    )


def read_network_table(path: str | Path, *, title: str | None = None) -> Network:
    r"""Read a network table (CSV) into a :class:`Network`.

    One row per node, upstream first. A row with an empty ``to`` is the outfall (exactly
    one). Every other row is a junction and the conduit from it to ``to``, with the
    diameter of that row; the length is the distance between the two nodes unless the
    column ``length_m`` gives it. The outfall takes ``rim_m - depth_m`` as its invert.

    Parameters
    ----------
    path : str or Path
        CSV file with the columns of :data:`NETWORK_COLUMNS`.
    title : str or None, optional
        ``[TITLE]`` of the SWMM file; the file name by default.

    Returns
    -------
    Network
        The network.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If a column is missing, a number cannot be read, there is not exactly one
        outfall, or a conduit refers to an unknown node.

    Examples
    --------
    >>> import tempfile, pathlib
    >>> head = "name,x_m,y_m,rim_m,depth_m,to,diameter_m"
    >>> table = head + "\\nJ1,1,0,10,2,OUT,0.6\\nOUT,5,0,9,2,,\\n"
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     _ = (pathlib.Path(tmp) / "n.csv").write_text(table)
    ...     network = read_network_table(pathlib.Path(tmp) / "n.csv")
    >>> [c.name for c in network.conduits]
    ['C_J1']
    """
    source = Path(path)
    if not source.is_file():
        raise NotFoundError(
            f"network table not found: {source}",
            details={"path": str(source)},
            reason="path_missing",
        )
    with source.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        missing = [c for c in NETWORK_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise InputDataError(
                f"network table lacks the columns: {', '.join(missing)}",
                details={"path": str(source), "missing": missing},
                hint=f"Columns: {', '.join(NETWORK_COLUMNS)}.",
                reason="invalid_network_table",
            )
        rows = list(reader)
    nodes: dict[str, dict[str, str]] = {}
    for number, row in enumerate(rows, start=2):
        name = (row["name"] or "").strip()
        if not name or " " in name:
            raise _fail(number, "name", "a name without spaces is required", name)
        nodes[name] = row

    def number_of(
        row: dict[str, str], line: int, column: str, default: float | None = None
    ) -> float:
        raw = (row.get(column) or "").strip()
        if not raw:
            if default is None:
                raise _fail(line, column, "a number is required", raw)
            return default
        try:
            value = float(raw)
        except ValueError:
            raise _fail(line, column, "not a number", raw) from None
        if not math.isfinite(value):
            raise _fail(line, column, "not finite", raw)
        return value

    junctions: list[Junction] = []
    conduits: list[Conduit] = []
    outfalls: list[Outfall] = []
    for line, row in enumerate(rows, start=2):
        name = row["name"].strip()
        x, y = number_of(row, line, "x_m"), number_of(row, line, "y_m")
        rim, depth = number_of(row, line, "rim_m"), number_of(row, line, "depth_m")
        if depth <= 0.0:
            raise _fail(line, "depth_m", "must be positive", depth)
        target = (row["to"] or "").strip()
        if not target:
            outfalls.append(Outfall(name, x, y, rim - depth))
            continue
        if target not in nodes:
            raise _fail(line, "to", "names no node of the table", target)
        diameter = number_of(row, line, "diameter_m")
        if diameter <= 0.0:
            raise _fail(line, "diameter_m", "must be positive", diameter)
        downstream = nodes[target]
        default_length = math.hypot(
            number_of(downstream, line, "x_m") - x,
            number_of(downstream, line, "y_m") - y,
        )
        length = number_of(row, line, "length_m", default_length)
        if length <= 0.0:
            raise _fail(
                line, "length_m", "must be positive (two nodes at one place?)", length
            )
        junctions.append(Junction(name, x, y, rim, depth))
        conduits.append(
            Conduit(
                f"C_{name}",
                name,
                target,
                length,
                diameter,
                roughness=number_of(row, line, "roughness", 0.013),
                entry_loss=number_of(row, line, "entry_loss", 0.5),
                exit_loss=number_of(row, line, "exit_loss", 1.0),
            )
        )
    if len(outfalls) != 1:
        raise InputDataError(
            f"the network table needs exactly one outfall (a row with an empty 'to'), "
            f"found {len(outfalls)}",
            details={"path": str(source), "outfalls": len(outfalls)},
            reason="invalid_network_table",
        )
    return Network(tuple(junctions), tuple(conduits), outfalls[0], title or source.name)


def _clock(seconds: float) -> tuple[str, str]:
    """Return the SWMM date and time of ``seconds`` after :data:`SWMM_START`."""
    moment = SWMM_START + timedelta(seconds=seconds)
    return moment.strftime("%m/%d/%Y"), moment.strftime("%H:%M:%S")


def write_inp(
    network: Network,
    settings: SwmmSettings,
    options: Mapping[str, str | float] | None = None,
) -> str:
    """Render the SWMM input file of a network.

    Parameters
    ----------
    network : Network
        The network.
    settings : SwmmSettings
        Duration, routing step, surcharge method, spill mode, node area.
    options : Mapping[str, str or float] or None, optional
        More ``[OPTIONS]`` of SWMM (``HEAD_TOLERANCE``, ``INERTIAL_DAMPING`` ...) that
        replace the defaults of the same name.

    Returns
    -------
    str
        The text of the INP file, SWMM 5.2, units CMS.

    Raises
    ------
    InvalidInputError
        If the duration or the routing step is not positive, or the stage series of the
        outfall is not increasing in time.

    Examples
    --------
    >>> junction = Junction("J1", 1.0, 0.0, 10.0, 2.0)
    >>> network = Network(
    ...     (junction,),
    ...     (Conduit("C1", "J1", "OUT", 4.0, 0.6),),
    ...     Outfall("OUT", 5.0, 0.0, 8.0),
    ... )
    >>> "SURCHARGE_METHOD     EXTRAN" in write_inp(network, SwmmSettings(60.0))
    True
    """
    if settings.duration_s <= 0 or settings.routing_step_s <= 0:
        raise InvalidInputError(
            "duration_s and routing_step_s must be positive",
            details={"option": "duration_s", "value": settings.duration_s},
            reason="out_of_range",
        )
    series = network.outfall.stage_series
    if any(b[0] <= a[0] for a, b in zip(series, series[1:], strict=False)):
        raise InvalidInputError(
            "the stage series of the outfall must increase in time",
            details={"option": "stage_series"},
            reason="invalid_stage_series",
        )
    surcharge_depth_m = 0.0 if settings.spill == "swmm_flooding" else 100.0
    end_date, end_time = _clock(settings.duration_s)
    start_date, start_time = _clock(0.0)
    merged: dict[str, str | float] = {
        "FLOW_UNITS": "CMS",
        "INFILTRATION": "HORTON",
        "FLOW_ROUTING": "DYNWAVE",
        "START_DATE": start_date,
        "START_TIME": start_time,
        "REPORT_START_DATE": start_date,
        "REPORT_START_TIME": start_time,
        "END_DATE": end_date,
        "END_TIME": end_time,
        "REPORT_STEP": "00:01:00",
        "WET_STEP": "00:00:01",
        "DRY_STEP": "00:00:01",
        "ROUTING_STEP": f"{settings.routing_step_s:g}",
        "VARIABLE_STEP": 0,
        "ALLOW_PONDING": "NO",
        "INERTIAL_DAMPING": "PARTIAL",
        "NORMAL_FLOW_LIMITED": "BOTH",
        "SURCHARGE_METHOD": settings.surcharge_method,
        "MIN_SURFAREA": f"{settings.min_surface_area_m2:g}",
    }
    merged.update(options or {})
    lines = [f"[TITLE]\n{network.title}\n", "[OPTIONS]"]
    lines += [f"{key:<20} {value}" for key, value in merged.items()]
    lines += ["", "[JUNCTIONS]", ";;Name Invert MaxDepth InitDepth SurDepth Aponded"]
    lines += [
        f"{j.name:<8} {j.invert_m:.4f} {j.depth_m:.4f} 0 {surcharge_depth_m:.1f} 0"
        for j in network.junctions
    ]
    out = network.outfall
    lines += ["", "[OUTFALLS]", ";;Name Invert Type Stage Gated"]
    gated = "YES" if out.gated else "NO"
    if series:
        lines.append(f"{out.name:<8} {out.invert_m:.4f} TIMESERIES STAGE {gated}")
    else:
        lines.append(f"{out.name:<8} {out.invert_m:.4f} FREE {gated}")
    lines += [
        "",
        "[CONDUITS]",
        ";;Name From To Length Roughness InOffset OutOffset InitFlow MaxFlow",
    ]
    lines += [
        f"{c.name:<10} {c.from_node:<8} {c.to_node:<8} {c.length_m:.3f} "
        f"{c.roughness:g} 0 0 0 0"
        for c in network.conduits
    ]
    lines += ["", "[XSECTIONS]", ";;Link Shape Geom1 Geom2 Geom3 Geom4 Barrels"]
    lines += [
        f"{c.name:<10} CIRCULAR {c.diameter_m:.4f} 0 0 0 1" for c in network.conduits
    ]
    lines += ["", "[LOSSES]", ";;Link Kentry Kexit Kavg Flap Seepage"]
    lines += [
        f"{c.name:<10} {c.entry_loss:g} {c.exit_loss:g} 0 NO 0"
        for c in network.conduits
    ]
    if series:
        lines += ["", "[TIMESERIES]", ";;Name Date Time Value"]
        for seconds, stage in series:
            date, clock = _clock(seconds)
            lines.append(f"STAGE {date} {clock} {stage:.3f}")
    lines += ["", "[COORDINATES]", ";;Node X Y"]
    lines += [f"{j.name:<8} {j.x_m:.3f} {j.y_m:.3f}" for j in network.junctions]
    lines.append(f"{out.name:<8} {out.x_m:.3f} {out.y_m:.3f}")
    lines += ["", "[REPORT]", "INPUT NO", "CONTROLS NO", "NODES NONE", "LINKS NONE", ""]
    return "\n".join(lines)
