"""Writing a SFINCS regular-grid model (ADR-0004).

The writer produces the files of SFINCS v2.4.1 in binary input mode, the default
(``inputformat = bin``), checked against the sources ``sfincs_input.f90``,
``sfincs_domain.f90`` and ``sfincs_infiltration.f90``:

* ``sfincs.ind``: int32 ``np`` (the number of active cells), then ``np`` int32 cell
  indices ``(m - 1) * nmax + n`` (1-based, ``n`` the row from the south edge, ``m`` the
  column from the west edge), in the order of increasing ``m`` and then ``n``;
* ``sfincs.msk`` (int8), ``sfincs.dep`` (float32 [m]), ``sfincs.man`` (float32 Manning
  ``n``) and ``sfincs.scs`` (float32 ``S = 1000/CN - 10`` in inches): one value per
  active cell in that same order;
* ``sfincs.precip``: ``time [s]`` and ``intensity [mm/h]`` in text. SFINCS extrapolates
  the last segment linearly, so a series that ends falling goes negative and removes
  water without a warning (extraction note 4): every series ends with a flat segment
  that reaches ``tstop``;
* ``sfincs.obs``: ``x y "name"`` of the observation points (SFINCS keeps a name only
  when it is quoted and calls the others ``station_001``, ``station_002``, ...);
* ``sfincs.inp``: the ``key = value`` file.

Arrays are shaped ``(rows, columns)`` with row 0 at the **south** edge, as SFINCS
stores them; :func:`hydraulik.terrain.grid` flips a north-up raster into that order.
The writer needs numpy, hence the ``model`` extra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from hydraulik.exceptions import InvalidInputError

__all__ = [
    "FILES",
    "TREF",
    "ModelInputs",
    "PrecipSeries",
    "RegularGrid",
    "active_order",
    "precip_breakpoints",
    "render_inp",
    "write_model",
]

TREF: Final = datetime(2000, 1, 1)
"""Reference time of every model; all times in the files are seconds from here."""

FILES: Final = {
    "inp": "sfincs.inp",
    "index": "sfincs.ind",
    "mask": "sfincs.msk",
    "elevation": "sfincs.dep",
    "manning": "sfincs.man",
    "curve_number": "sfincs.scs",
    "precip": "sfincs.precip",
    "observations": "sfincs.obs",
}
"""File names of a model directory by role."""

STEP_HOLD_S: Final = 1.0
"""A block of rain is written from its start to ``STEP_HOLD_S`` before its end, so the
linear interpolation of SFINCS reproduces the block (the volume is exact to within
``0.5 * STEP_HOLD_S * |jump|`` per step change)."""

Float = NDArray[np.float64]
Bool = NDArray[np.bool_]


@dataclass(frozen=True)
class RegularGrid:
    """A regular SFINCS grid without rotation.

    Attributes
    ----------
    x0_m, y0_m : float
        Lower-left corner of the grid, the edge of the first cell [m].
    dx_m : float
        Cell size [m]; cells are square.
    columns, rows : int
        ``mmax`` and ``nmax``.
    epsg : int
        EPSG code of the projected CRS (metres).
    """

    x0_m: float
    y0_m: float
    dx_m: float
    columns: int
    rows: int
    epsg: int = 2180

    @property
    def shape(self) -> tuple[int, int]:
        """tuple: ``(rows, columns)``, the shape of every array of the model."""
        return (self.rows, self.columns)

    def cell_of(self, x_m: float, y_m: float) -> tuple[int, int] | None:
        """Return the ``(row, column)`` of the cell that holds a point, or ``None``.

        Parameters
        ----------
        x_m, y_m : float
            Position in the CRS of the grid [m].

        Returns
        -------
        tuple of (int, int) or None
            0-based row from the south edge and column from the west edge.

        Examples
        --------
        >>> RegularGrid(0.0, 0.0, 2.0, 10, 5).cell_of(3.0, 1.0)
        (0, 1)
        """
        column = int((x_m - self.x0_m) // self.dx_m)
        row = int((y_m - self.y0_m) // self.dx_m)
        if 0 <= column < self.columns and 0 <= row < self.rows:
            return (row, column)
        return None

    def centre_of(self, row: int, column: int) -> tuple[float, float]:
        """Return the centre ``(x_m, y_m)`` of a cell."""
        return (
            self.x0_m + (column + 0.5) * self.dx_m,
            self.y0_m + (row + 0.5) * self.dx_m,
        )


@dataclass(frozen=True)
class PrecipSeries:
    """Uniform rain as breakpoints of a linearly interpolated series.

    Attributes
    ----------
    times_s : tuple of float
        Time of each breakpoint [s from ``TREF``], increasing.
    intensity_mm_h : tuple of float
        Rain intensity at each breakpoint [mm/h], not negative.
    """

    times_s: tuple[float, ...]
    intensity_mm_h: tuple[float, ...]

    def depth_mm(self) -> float:
        """float: the depth [mm] SFINCS integrates (trapezoids of the breakpoints)."""
        t = np.asarray(self.times_s, dtype=float)
        i = np.asarray(self.intensity_mm_h, dtype=float)
        return float(np.sum(0.5 * (i[1:] + i[:-1]) * np.diff(t)) / 3600.0)


def precip_breakpoints(
    step_depth_mm: Float | list[float],
    timestep_s: float,
    tstop_s: float,
    *,
    start_s: float = 0.0,
) -> PrecipSeries:
    """Turn the rain depth of each step into the breakpoints SFINCS expects.

    Each step is written at its start and :data:`STEP_HOLD_S` before its end; the rain
    stops with a zero at the end of the last step and a zero at ``tstop_s``, so the
    series ends flat (extraction note 4).

    Parameters
    ----------
    step_depth_mm : array-like
        Depth of rain in each step [mm], for example ``HietogramResult.intensities_mm``.
    timestep_s : float
        Length of a step [s].
    tstop_s : float
        End of the simulation [s from ``TREF``]; at least the end of the rain.
    start_s : float, optional
        Time the first step starts [s from ``TREF``].

    Returns
    -------
    PrecipSeries
        The breakpoints.

    Raises
    ------
    InvalidInputError
        If a depth is negative, the step is not positive or ``tstop_s`` is before the
        end of the rain.

    Examples
    --------
    >>> series = precip_breakpoints([1.0, 2.0], 600.0, 3600.0)
    >>> round(series.depth_mm(), 3)
    2.999
    >>> series.intensity_mm_h[-2:]
    (0.0, 0.0)
    """
    depth = np.asarray(step_depth_mm, dtype=float)
    if timestep_s <= 0 or depth.size == 0 or (depth < 0).any():
        raise InvalidInputError(
            "rain steps need a positive timestep and non-negative depths",
            details={"option": "step_depth_mm"},
            reason="invalid_rain",
        )
    end_s = start_s + depth.size * timestep_s
    if tstop_s < end_s:
        raise InvalidInputError(
            f"the simulation ends at {tstop_s:g} s, before the rain at {end_s:g} s",
            details={"option": "tstop_s", "value": tstop_s},
            hint="Lengthen the simulation (the recession after the rain).",
            reason="out_of_range",
        )
    intensity = depth * 3600.0 / timestep_s
    times: list[float] = []
    values: list[float] = []
    for index, value in enumerate(intensity):
        t0 = start_s + index * timestep_s
        times += [t0, t0 + timestep_s - min(STEP_HOLD_S, timestep_s / 2)]
        values += [float(value), float(value)]
    times.append(end_s)
    values.append(0.0)
    if tstop_s > end_s:
        times.append(float(tstop_s))
        values.append(0.0)
    else:  # the rain lasts to tstop: keep the last segment flat
        times.append(end_s + STEP_HOLD_S)
        values.append(0.0)
    return PrecipSeries(tuple(times), tuple(values))


@dataclass
class ModelInputs:
    """Everything a regular-grid SFINCS model is made of.

    Attributes
    ----------
    grid : RegularGrid
        The grid.
    elevation_m : ndarray
        Bed level of each cell [m], shape ``grid.shape``, row 0 at the south.
    active : ndarray of bool
        Cells that are part of the domain; the others are inactive (``msk = 0``).
    precip : PrecipSeries
        Uniform rain.
    tstop_s : float
        End of the simulation [s from ``TREF``].
    outflow : ndarray of bool or None
        Active cells where water leaves freely (``msk = 3``): the water depth is kept
        at zero there. ``None`` closes the whole boundary.
    manning : float or ndarray
        Manning ``n`` [s/m^(1/3)], uniform or per cell.
    curve_number : ndarray or None
        SCS curve number of each cell (30 to 100); NaN or 100 for no infiltration.
        ``None`` switches infiltration off.
    initial_abstraction : float
        ``sfacinf``, the share of ``S`` that is the initial abstraction.
    observation_points : tuple of (x_m, y_m, name)
        Points whose water level SFINCS writes to ``sfincs_his.nc``.
    huthresh_m : float
        Wet/dry threshold [m]; one place feeds the solver and, later, a subgrid table.
    dtmax_s : float
        Upper bound of the adaptive time step [s].
    alpha : float
        CFL factor.
    advection : bool
        Momentum advection (SSWE): needed for supercritical flow in the mountains.
    dtout_s, dthisout_s : float
        Interval of the map output and of the point output [s].
    extra : dict
        More ``sfincs.inp`` keys; they replace the generated ones.
    """

    grid: RegularGrid
    elevation_m: Float
    active: Bool
    precip: PrecipSeries
    tstop_s: float
    outflow: Bool | None = None
    manning: float | Float = 0.04
    curve_number: Float | None = None
    initial_abstraction: float = 0.2
    observation_points: tuple[tuple[float, float, str], ...] = ()
    huthresh_m: float = 0.05
    dtmax_s: float = 60.0
    alpha: float = 0.5
    advection: bool = True
    dtout_s: float = 600.0
    dthisout_s: float = 60.0
    extra: dict[str, str | float | int] = field(default_factory=dict)

    def validate(self) -> None:
        """Check shapes and values before anything is written.

        Raises
        ------
        InvalidInputError
            If an array has the wrong shape, no cell is active, an outflow cell is
            not active, a Manning value or a curve number is out of range, or the
            observation points are outside the grid.
        """
        shape = self.grid.shape
        arrays: dict[str, NDArray[np.generic] | None] = {
            "elevation_m": self.elevation_m,
            "active": self.active,
            "outflow": self.outflow,
            "curve_number": self.curve_number,
        }
        if isinstance(self.manning, np.ndarray):
            arrays["manning"] = self.manning
        for name, array in arrays.items():
            if array is not None and array.shape != shape:
                raise InvalidInputError(
                    f"{name} has shape {array.shape}, the grid has {shape}",
                    details={"option": name, "value": str(array.shape)},
                    reason="shape_mismatch",
                )
        if not self.active.any():
            raise InvalidInputError(
                "no cell of the grid is active",
                details={"option": "active"},
                hint="Check that the domain polygon overlaps the elevation raster.",
                reason="empty_domain",
            )
        if self.outflow is not None and (self.outflow & ~self.active).any():
            raise InvalidInputError(
                "an outflow cell lies outside the active domain",
                details={"option": "outflow"},
                reason="outflow_outside_domain",
            )
        if isinstance(self.manning, np.ndarray):
            roughness = self.manning[self.active]
        else:
            roughness = np.asarray([self.manning], dtype=float)
        if np.any(~np.isfinite(roughness)) or np.any(roughness <= 0):
            raise InvalidInputError(
                "Manning n must be positive and finite on every active cell",
                details={"option": "manning"},
                reason="out_of_range",
            )
        if not np.all(np.isfinite(self.elevation_m[self.active])):
            raise InvalidInputError(
                "an active cell has no elevation",
                details={"option": "elevation_m"},
                hint="Fill the gaps of the DEM or shrink the domain.",
                reason="elevation_gap",
            )
        if self.curve_number is not None:
            cn = self.curve_number[self.active & np.isfinite(self.curve_number)]
            if cn.size and (cn.min() < 30.0 or cn.max() > 100.0):
                raise InvalidInputError(
                    "curve numbers must be 30 to 100, "
                    f"found {cn.min():g} to {cn.max():g}",
                    details={"option": "curve_number"},
                    reason="out_of_range",
                )
        for _, _, name in self.observation_points:
            if not name or '"' in name or "\n" in name:
                raise InvalidInputError(
                    f"observation point name {name!r} is empty or has a quote",
                    details={"option": "observation_points", "value": name},
                    reason="invalid_station_name",
                )
        for x, y, name in self.observation_points:
            if self.grid.cell_of(x, y) is None:
                raise InvalidInputError(
                    f"observation point {name} lies outside the grid",
                    details={"option": "observation_points", "value": name},
                    reason="outside_grid",
                )


def active_order(active: Bool) -> NDArray[np.intp]:
    """Return the 0-based positions of the active cells in SFINCS order.

    SFINCS counts the cells with the row index running fastest (``m`` outer, ``n``
    inner), which is Fortran order of the ``(rows, columns)`` array.

    Parameters
    ----------
    active : ndarray of bool
        The mask, shape ``(rows, columns)``.

    Returns
    -------
    ndarray
        Positions into ``array.ravel(order="F")`` of the active cells.

    Examples
    --------
    >>> import numpy as np
    >>> active_order(np.array([[True, False], [True, True]])).tolist()
    [0, 1, 3]
    """
    return np.flatnonzero(active.ravel(order="F"))


def _per_cell(array: Float, active: Bool) -> Float:
    return np.asarray(array, dtype=np.float64).ravel(order="F")[active_order(active)]


def render_inp(inputs: ModelInputs, *, files: dict[str, str]) -> str:
    """Render ``sfincs.inp``.

    Parameters
    ----------
    inputs : ModelInputs
        The model.
    files : dict
        Names of the files that exist, by role (a subset of :data:`FILES`).

    Returns
    -------
    str
        The ``key = value`` text.
    """
    grid = inputs.grid
    tstop = TREF + timedelta(seconds=inputs.tstop_s)
    keys: dict[str, str | float | int] = {
        "mmax": grid.columns,
        "nmax": grid.rows,
        "dx": grid.dx_m,
        "dy": grid.dx_m,
        "x0": grid.x0_m,
        "y0": grid.y0_m,
        "rotation": 0,
        "epsg": grid.epsg,
        "tref": TREF.strftime("%Y%m%d %H%M%S"),
        "tstart": TREF.strftime("%Y%m%d %H%M%S"),
        "tstop": tstop.strftime("%Y%m%d %H%M%S"),
        "inputformat": "bin",
        "outputformat": "net",
        "indexfile": files["index"],
        "mskfile": files["mask"],
        "depfile": files["elevation"],
        "precipfile": files["precip"],
        "alpha": inputs.alpha,
        "huthresh": inputs.huthresh_m,
        "dtmax": inputs.dtmax_s,
        "advection": int(inputs.advection),
        "dtout": inputs.dtout_s,
        "dtmaxout": inputs.tstop_s,
        "dthisout": inputs.dthisout_s,
        "storecumprcp": 1,
        "storevelmax": 1,
    }
    if "manning" in files:
        keys["manningfile"] = files["manning"]
    else:
        keys["manning"] = float(np.asarray(inputs.manning).reshape(-1)[0])
    if "curve_number" in files:
        keys["scsfile"] = files["curve_number"]
        keys["sfacinf"] = inputs.initial_abstraction
    if "observations" in files:
        keys["obsfile"] = files["observations"]
    keys.update(inputs.extra)
    return "".join(f"{key:<16}= {value}\n" for key, value in keys.items())


def planned_files(inputs: ModelInputs) -> dict[str, str]:
    """Return the role to file name of the files the model will have.

    Parameters
    ----------
    inputs : ModelInputs
        The model.

    Returns
    -------
    dict
        A subset of :data:`FILES`: ``sfincs.man`` only for a Manning array,
        ``sfincs.scs`` only with a curve number, ``sfincs.obs`` only with points.
    """
    roles = ["inp", "index", "mask", "elevation", "precip"]
    if isinstance(inputs.manning, np.ndarray):
        roles.append("manning")
    if inputs.curve_number is not None:
        roles.append("curve_number")
    if inputs.observation_points:
        roles.append("observations")
    return {role: FILES[role] for role in roles}


def write_model(directory: Path, inputs: ModelInputs) -> dict[str, str]:
    """Write the files of a model into a directory.

    Parameters
    ----------
    directory : Path
        An existing directory (the staging directory of a build).
    inputs : ModelInputs
        The model; it is validated first.

    Returns
    -------
    dict
        Role to file name of what was written (see :func:`planned_files`).

    Raises
    ------
    InvalidInputError
        If the inputs do not validate (see :meth:`ModelInputs.validate`).
    """
    inputs.validate()
    files = planned_files(inputs)
    order = active_order(inputs.active)
    (directory / files["index"]).write_bytes(
        np.int32(order.size).tobytes() + (order + 1).astype(np.int32).tobytes()
    )
    mask = np.where(inputs.active, 1, 0).astype(np.int8)
    if inputs.outflow is not None:
        mask[inputs.outflow] = 3
    (directory / files["mask"]).write_bytes(mask.ravel(order="F")[order].tobytes())
    (directory / files["elevation"]).write_bytes(
        _per_cell(inputs.elevation_m, inputs.active).astype(np.float32).tobytes()
    )
    if "manning" in files:
        (directory / files["manning"]).write_bytes(
            _per_cell(np.asarray(inputs.manning), inputs.active)
            .astype(np.float32)
            .tobytes()
        )
    if inputs.curve_number is not None:
        cn = _per_cell(inputs.curve_number, inputs.active)
        # CN 100 and "no data" mean no storage: S = 0, all rain is runoff.
        cn = np.where(np.isfinite(cn), np.clip(cn, 1.0, 100.0), 100.0)
        s_inches = 1000.0 / cn - 10.0
        (directory / files["curve_number"]).write_bytes(
            s_inches.astype(np.float32).tobytes()
        )
    (directory / files["precip"]).write_text(
        "".join(
            f"{t:10.1f} {i:12.5f}\n"
            for t, i in zip(
                inputs.precip.times_s, inputs.precip.intensity_mm_h, strict=True
            )
        ),
        encoding="utf-8",
    )
    if "observations" in files:
        (directory / files["observations"]).write_text(
            "".join(
                f'{x:.3f} {y:.3f} "{name}"\n'
                for x, y, name in inputs.observation_points
            ),
            encoding="utf-8",
        )
    (directory / files["inp"]).write_text(
        render_inp(inputs, files=files), encoding="utf-8"
    )
    return files
