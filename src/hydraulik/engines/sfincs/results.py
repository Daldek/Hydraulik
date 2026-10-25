"""Reading the results of a SFINCS run: maps, stations, water balance (ADR-0004).

SFINCS writes ``sfincs_map.nc`` (one value per cell, rows counted from the **south**
edge: dimension ``n`` is the row, ``m`` the column) and ``sfincs_his.nc`` (series at
the observation points). Checked on SFINCS v2.4.1 and ``main``:

* ``zs``, ``zsmax`` and ``hmax`` are masked wherever the water is shallower than
  ``huthresh``, so a maximum depth below that threshold is not in the file;
* ``h`` (the water depth at each output time) is **not** masked, so the water that
  stays on the surface at the end is exact; ``cumprcp`` and ``cuminf`` are the rain
  and the infiltration accumulated to ``tstop`` (``storecumprcp = 1``);
* the file carries the grid (``corner_x``, ``corner_y``), the CRS and every input key
  (variable ``inp``), so a result needs nothing else to be read or exported.

The balance is ``rain - infiltration - stored = residual``. With a closed boundary the
residual is the error of the run; with outflow cells (``msk = 3``) it is the water
that left, and only a negative residual (water gained) is an error. Output needs the
``sfincs`` extra (numpy and netCDF4), a GeoTIFF export also the ``model`` extra.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
from numpy.typing import NDArray

from hydraulik._optional import require
from hydraulik.engines.sfincs.model import RegularGrid
from hydraulik.exceptions import (
    InputDataError,
    InvalidInputError,
    NotFoundError,
    UnsupportedError,
)
from hydraulik.terrain.grid import write_grid_raster

__all__ = [
    "BALANCE_WARNING_PERCENT",
    "EXPORT_VARIABLES",
    "DepthStatistics",
    "MapRun",
    "Station",
    "SurfaceBalance",
    "depth_statistics",
    "export_geotiff",
    "read_map",
    "read_stations",
    "surface_balance",
    "write_stations_csv",
]

BALANCE_WARNING_PERCENT: Final = 1.0
"""Residual [percent of the rain] above which the balance is flagged (spec 6)."""

Float = NDArray[np.float64]
Bool = NDArray[np.bool_]

ExportVariable = Literal["max_depth", "max_velocity", "final_depth", "infiltration"]
EXPORT_VARIABLES: Final[dict[str, str]] = {
    "max_depth": "Maximum water depth [m]; cells under huthresh are no data",
    "max_velocity": "Maximum flow velocity [m/s]",
    "final_depth": "Water depth at the last output time [m]",
    "infiltration": "Infiltration accumulated to the end of the run [m]",
}
"""Maps that :func:`export_geotiff` writes, with their meaning."""


@dataclass(frozen=True)
class MapRun:
    """The map of a finished run, every array shaped ``(rows, columns)``, row 0 south.

    Attributes
    ----------
    path : Path
        The ``sfincs_map.nc`` that was read.
    grid : RegularGrid
        Position, cell size and CRS of the grid.
    active, outflow : ndarray of bool
        Active cells (``msk > 0``) and outflow cells (``msk == 3``).
    bed_m : ndarray
        Bed level [m], NaN outside the domain.
    depth_m : ndarray
        Water depth at the last output time [m], NaN outside the domain.
    depth_time_s : float
        Time of that output [s from the start].
    max_depth_m : ndarray
        Maximum depth [m]; NaN where it stayed under ``huthresh_m`` or outside the
        domain.
    max_velocity_ms : ndarray
        Maximum velocity [m/s], NaN outside the domain.
    rain_m, infiltration_m : ndarray
        Rain and infiltration accumulated to ``end_time_s`` [m], NaN outside.
    end_time_s : float
        Time the accumulated maps refer to (``tstop``) [s from the start].
    huthresh_m : float or None
        The wet/dry threshold of the run [m], from the inputs stored in the file.
    status : int or None
        SFINCS' own status of the run (0 is no error).
    runtime_s, average_dt_s : float or None
        Wall time and mean time step of the run [s].
    build_revision : str or None
        The SFINCS version that wrote the file.
    """

    path: Path
    grid: RegularGrid
    active: Bool
    outflow: Bool
    bed_m: Float
    depth_m: Float
    depth_time_s: float
    max_depth_m: Float
    max_velocity_ms: Float
    rain_m: Float
    infiltration_m: Float
    end_time_s: float
    huthresh_m: float | None
    status: int | None
    runtime_s: float | None
    average_dt_s: float | None
    build_revision: str | None

    @property
    def cell_area_m2(self) -> float:
        """float: area of one cell [m2]."""
        return self.grid.dx_m * self.grid.dx_m


def _filled(variable: Any, index: int | None = None) -> Float:
    """Return a NetCDF variable (the frame ``index`` of it) with gaps as NaN."""
    data = variable[:] if index is None else variable[index]
    return np.asarray(np.ma.filled(np.ma.asarray(data, dtype=float), np.nan))


def _scalar(dataset: Any, name: str) -> float | None:
    if name not in dataset.variables:
        return None
    value = np.ma.filled(np.ma.asarray(dataset[name][:], dtype=float), np.nan)
    flat = np.asarray(value).ravel()
    return float(flat[0]) if flat.size and np.isfinite(flat[0]) else None


def _open(path: Path) -> Any:
    netcdf4 = require("netCDF4", "sfincs")
    if not path.is_file():
        raise NotFoundError(
            f"SFINCS result not found: {path}",
            details={"path": str(path)},
            hint="Name the directory that `hydraulik model run` wrote.",
            reason="path_missing",
        )
    try:
        return netcdf4.Dataset(path)
    except OSError as exc:
        raise InputDataError(
            f"{path.name} is not a readable NetCDF file: {exc}",
            details={"path": str(path)},
            reason="invalid_netcdf",
        ) from exc


def read_map(path: str | Path) -> MapRun:
    """Read ``sfincs_map.nc`` of a regular-grid run.

    Parameters
    ----------
    path : str or Path
        The map file.

    Returns
    -------
    MapRun
        The grid, the masks and the maps, with gaps and masked cells as NaN.

    Raises
    ------
    MissingDependencyError
        If netCDF4 is not installed (extra ``sfincs``).
    NotFoundError
        If the file does not exist.
    InputDataError
        If the file is not NetCDF or lacks the variables of a SFINCS map.
    UnsupportedError
        If the map is not a regular grid without rotation (a quadtree or subgrid
        model) or the CRS is missing.
    """
    source = Path(path)
    dataset = _open(source)
    with dataset:
        needed = ("corner_x", "corner_y", "msk", "zb", "h", "time")
        missing = [n for n in needed if n not in dataset.variables]
        if missing or not {"n", "m"} <= set(dataset.dimensions):
            raise UnsupportedError(
                f"{source.name} is not the map of a regular SFINCS grid",
                details={"path": str(source), "missing": missing},
                hint="Hydraulik reads regular-grid models written by `model build`.",
                reason="map_layout",
            )
        corner_x, corner_y = _filled(dataset["corner_x"]), _filled(dataset["corner_y"])
        dx = float(corner_x[0, 1] - corner_x[0, 0])
        dy = float(corner_y[1, 0] - corner_y[0, 0])
        rotated = abs(float(corner_x[1, 0] - corner_x[0, 0])) > 1e-6 * max(dx, 1.0)
        if rotated or not math.isclose(dx, dy, rel_tol=1e-6) or dx <= 0:
            raise UnsupportedError(
                f"{source.name} has a rotated or non-square grid",
                details={"dx_m": dx, "dy_m": dy},
                reason="map_layout",
            )
        epsg = _scalar_attribute(dataset, "crs", "epsg")
        if epsg is None:
            raise UnsupportedError(
                f"{source.name} has no CRS",
                details={"path": str(source)},
                hint="Write the model with an EPSG code (`epsg` in sfincs.inp).",
                reason="crs_missing",
            )
        rows, columns = (
            int(dataset.dimensions["n"].size),
            int(dataset.dimensions["m"].size),
        )
        grid = RegularGrid(
            float(corner_x[0, 0]), float(corner_y[0, 0]), dx, columns, rows, int(epsg)
        )
        mask = np.ma.filled(np.ma.asarray(dataset["msk"][:]), 0).astype(int)
        active = mask > 0
        outside = ~active

        def masked(array: Float) -> Float:
            return np.where(outside, np.nan, array)

        depth_times = _filled(dataset["time"])
        depth = masked(_filled(dataset["h"], -1))
        accumulated = "timemax" in dataset.variables
        end_time = (
            float(_filled(dataset["timemax"])[-1]) if accumulated else float("nan")
        )

        def last(name: str) -> Float:
            if name not in dataset.variables:
                return np.full(grid.shape, np.nan)
            return masked(_filled(dataset[name], -1))

        huthresh = (
            _scalar_attribute(dataset, "inp", "huthresh")
            if "inp" in dataset.variables
            else None
        )
        status = _scalar(dataset, "status")
        return MapRun(
            path=source,
            grid=grid,
            active=active,
            outflow=mask == 3,
            bed_m=masked(_filled(dataset["zb"])),
            depth_m=depth,
            depth_time_s=float(depth_times[-1]),
            max_depth_m=last("hmax"),
            max_velocity_ms=last("vmax"),
            rain_m=last("cumprcp"),
            infiltration_m=last("cuminf"),
            end_time_s=end_time,
            huthresh_m=None if huthresh is None else round(float(huthresh), 6),
            status=None if status is None else int(status),
            runtime_s=_scalar(dataset, "total_runtime"),
            average_dt_s=_scalar(dataset, "average_dt"),
            build_revision=getattr(dataset, "Build-Revision", None),
        )


def _scalar_attribute(dataset: Any, variable: str, name: str) -> float | None:
    """Return the numeric attribute ``name`` of a NetCDF variable, or ``None``."""
    if variable not in dataset.variables:
        return None
    holder = dataset[variable]
    if name not in holder.ncattrs():
        return None
    try:
        return float(holder.getncattr(name))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class DepthStatistics:
    """The extremes and the flooded areas of a run.

    Attributes
    ----------
    max_depth_m : float
        Largest water depth anywhere [m]; 0 when no cell reached ``huthresh``.
    max_depth_x_m, max_depth_y_m : float or None
        Centre of the cell with that depth.
    max_velocity_ms : float
        Largest flow velocity [m/s].
    flooded_area_m2 : dict of float to float
        Area where the maximum depth reached each threshold [m2], by threshold [m].
    active_area_m2 : float
        Area of the domain [m2].
    """

    max_depth_m: float
    max_depth_x_m: float | None
    max_depth_y_m: float | None
    max_velocity_ms: float
    flooded_area_m2: dict[float, float]
    active_area_m2: float


def depth_statistics(
    run: MapRun, thresholds_m: Sequence[float] = (0.1, 0.3)
) -> DepthStatistics:
    """Return the maximum depth and velocity and the area flooded deeper than limits.

    Parameters
    ----------
    run : MapRun
        The map.
    thresholds_m : sequence of float, optional
        Depths [m] for which the flooded area is reported (maximum depth at least
        the threshold).

    Returns
    -------
    DepthStatistics
        The numbers; cells where the depth stayed under ``huthresh`` count as dry.

    Raises
    ------
    InvalidInputError
        If a threshold is not positive or is below ``huthresh`` (the file does not
        hold depths under it).
    """
    huthresh = run.huthresh_m or 0.0
    for limit in thresholds_m:
        if limit <= 0 or limit < huthresh - 1e-9:
            raise InvalidInputError(
                f"depth threshold {limit:g} m is below the wet/dry threshold "
                f"{huthresh:g} m of the run",
                details={"option": "thresholds_m", "value": limit},
                hint="Depths under huthresh are masked in the SFINCS map.",
                reason="below_huthresh",
            )
    depth = np.where(np.isfinite(run.max_depth_m), run.max_depth_m, 0.0)
    peak = float(depth.max()) if depth.size else 0.0
    x_m: float | None = None
    y_m: float | None = None
    if peak > 0.0:
        row, column = np.unravel_index(int(np.argmax(depth)), depth.shape)
        x_m, y_m = run.grid.centre_of(int(row), int(column))
    velocity = run.max_velocity_ms[np.isfinite(run.max_velocity_ms)]
    return DepthStatistics(
        max_depth_m=peak,
        max_depth_x_m=x_m,
        max_depth_y_m=y_m,
        max_velocity_ms=float(velocity.max()) if velocity.size else 0.0,
        flooded_area_m2={
            float(limit): float((depth >= limit).sum()) * run.cell_area_m2
            for limit in thresholds_m
        },
        active_area_m2=float(run.active.sum()) * run.cell_area_m2,
    )


@dataclass(frozen=True)
class SurfaceBalance:
    """Water volumes of the surface model and what is left over [m3].

    Attributes
    ----------
    rain_m3, infiltration_m3, stored_m3 : float
        Rain that fell, water that infiltrated and water left on the surface.
    residual_m3 : float
        ``rain - infiltration - stored``: the outflow over an open boundary, or the
        error of a closed model.
    residual_percent : float
        ``residual`` as a percentage of the rain.
    open_boundary : bool
        True when the model has outflow cells (``msk = 3``).
    expected_rain_m3 : float or None
        The rain of the precipitation file over the domain, when it is known.
    flags : tuple of str
        What is wrong: ``balance_residual`` (closed model, residual above the
        threshold), ``balance_gain`` (open model that gained water),
        ``rain_mismatch`` (rain differs from the file by more than the threshold),
        ``time_mismatch`` (the last depth map is not at the end of the run).
    """

    rain_m3: float
    infiltration_m3: float
    stored_m3: float
    residual_m3: float
    residual_percent: float
    open_boundary: bool
    expected_rain_m3: float | None
    flags: tuple[str, ...]

    @property
    def flagged(self) -> bool:
        """bool: True when a flag is set."""
        return bool(self.flags)


def surface_balance(
    run: MapRun, *, expected_rain_mm: float | None = None
) -> SurfaceBalance:
    """Book the water of a run: rain, infiltration, storage, residual.

    Parameters
    ----------
    run : MapRun
        The map.
    expected_rain_mm : float or None, optional
        The depth of the precipitation file [mm], to check the rain SFINCS applied.

    Returns
    -------
    SurfaceBalance
        The volumes, the residual and the flags (see :class:`SurfaceBalance`).
    """
    area = run.cell_area_m2
    inside = run.active

    def total(array: Float) -> float:
        return float(np.nansum(np.where(inside, array, 0.0))) * area

    rain = total(run.rain_m)
    infiltration = total(run.infiltration_m)
    stored = total(run.depth_m)
    residual = rain - infiltration - stored
    percent = 100.0 * residual / rain if rain > 0.0 else 0.0
    open_boundary = bool(run.outflow.any())
    expected = (
        None
        if expected_rain_mm is None
        else expected_rain_mm / 1000.0 * float(inside.sum()) * area
    )
    flags: list[str] = []
    if not np.isfinite(run.rain_m[inside]).any():
        flags.append("no_rain_output")  # storecumprcp was off: nothing to book
    else:
        if rain > 0.0:
            if not open_boundary and abs(percent) > BALANCE_WARNING_PERCENT:
                flags.append("balance_residual")
            if open_boundary and percent < -BALANCE_WARNING_PERCENT:
                flags.append("balance_gain")
        limit = BALANCE_WARNING_PERCENT / 100.0 * (expected or 0.0)
        if expected and abs(rain - expected) > limit:
            flags.append("rain_mismatch")
    if math.isfinite(run.end_time_s) and abs(run.depth_time_s - run.end_time_s) > 1.0:
        flags.append("time_mismatch")
    return SurfaceBalance(
        rain_m3=rain,
        infiltration_m3=infiltration,
        stored_m3=stored,
        residual_m3=residual,
        residual_percent=percent,
        open_boundary=open_boundary,
        expected_rain_m3=expected,
        flags=tuple(flags),
    )


@dataclass(frozen=True)
class Station:
    """The series of one observation point (``sfincs_his.nc``).

    Attributes
    ----------
    name : str
        Name from ``sfincs.obs``.
    x_m, y_m : float
        Position of the point [m].
    bed_m : float
        Bed level of its cell [m].
    times_s : ndarray
        Output times [s from the start].
    level_m, depth_m : ndarray
        Water level and depth at each time [m].
    """

    name: str
    x_m: float
    y_m: float
    bed_m: float
    times_s: Float
    level_m: Float
    depth_m: Float

    @property
    def max_depth_m(self) -> float:
        """float: largest depth of the series [m]."""
        return float(np.nanmax(self.depth_m)) if self.depth_m.size else 0.0

    @property
    def time_of_max_s(self) -> float:
        """float: first time the largest depth occurs [s from the start]."""
        return (
            float(self.times_s[int(np.nanargmax(self.depth_m))])
            if self.depth_m.size
            else 0.0
        )


def read_stations(path: str | Path) -> tuple[Station, ...]:
    """Read ``sfincs_his.nc``.

    Parameters
    ----------
    path : str or Path
        The file.

    Returns
    -------
    tuple of Station
        One per observation point, in file order.

    Raises
    ------
    NotFoundError, InputDataError, MissingDependencyError
        As :func:`read_map`.
    """
    dataset = _open(Path(path))
    with dataset:
        needed = ("station_name", "point_x", "point_y", "point_zb", "time", "point_zs")
        missing = [n for n in needed if n not in dataset.variables]
        if missing:
            raise InputDataError(
                f"{Path(path).name} lacks the variables {', '.join(missing)}",
                details={"path": str(path), "missing": missing},
                reason="invalid_his",
            )
        names = np.ma.filled(np.ma.asarray(dataset["station_name"][:]), b"")
        times = _filled(dataset["time"])
        level = _filled(dataset["point_zs"]).reshape(times.size, -1)
        bed = _filled(dataset["point_zb"]).reshape(-1)
        x = _filled(dataset["point_x"]).reshape(-1)
        y = _filled(dataset["point_y"]).reshape(-1)
        stations: list[Station] = []
        for index in range(bed.size):
            raw = b"".join(
                item if isinstance(item, bytes) else bytes(item)
                for item in names[index]
            )
            name = (
                raw.decode("utf-8", errors="replace").strip("\x00 ") or f"{index + 1}"
            )
            series = level[:, index]
            stations.append(
                Station(
                    name=name,
                    x_m=float(x[index]),
                    y_m=float(y[index]),
                    bed_m=float(bed[index]),
                    times_s=times,
                    level_m=series,
                    depth_m=np.maximum(series - bed[index], 0.0),
                )
            )
        return tuple(stations)


def write_stations_csv(stations: Sequence[Station], path: Path) -> None:
    """Write the series of the stations as ``time_s,station,level_m,depth_m``.

    Parameters
    ----------
    stations : sequence of Station
        The series.
    path : Path
        The file to create.
    """
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write("time_s,station,level_m,depth_m\n")
        for station in stations:
            for time_s, level, depth in zip(
                station.times_s, station.level_m, station.depth_m, strict=True
            ):
                stream.write(f"{time_s:g},{station.name},{level:.4f},{depth:.4f}\n")


def export_geotiff(run: MapRun, variable: str, path: Path) -> None:
    """Write one map of the run as a GeoTIFF in the CRS of the model.

    Parameters
    ----------
    run : MapRun
        The map.
    variable : {"max_depth", "max_velocity", "final_depth", "infiltration"}
        Which map (see :data:`EXPORT_VARIABLES`).
    path : Path
        The file to create; it is overwritten.

    Raises
    ------
    InvalidInputError
        If ``variable`` is not one of :data:`EXPORT_VARIABLES`.
    MissingDependencyError
        If rasterio is not installed (extra ``model``).
    """
    arrays = {
        "max_depth": run.max_depth_m,
        "max_velocity": run.max_velocity_ms,
        "final_depth": run.depth_m,
        "infiltration": run.infiltration_m,
    }
    if variable not in arrays:
        raise InvalidInputError(
            f"unknown map {variable!r}",
            details={"option": "variable", "allowed": sorted(arrays)},
            reason="not_allowed",
        )
    write_grid_raster(
        path,
        run.grid,
        arrays[variable],
        tags={
            "variable": variable,
            "description": EXPORT_VARIABLES[variable],
            "source": run.path.name,
        },
    )
