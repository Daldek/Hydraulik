"""Building the inputs of a SFINCS model from rasters the user supplies (ADR-0004).

The first step of ``model build``: the user brings a terrain (GeoTIFFs), optionally a
Manning raster and a curve-number raster (or the SCS retention ``S`` in mm), a design
rain and, where the water leaves, an outlet; this module puts them on one grid and
fills :class:`~hydraulik.engines.sfincs.model.ModelInputs`, which
:func:`~hydraulik.engines.sfincs.model.write_model` turns into files. Nothing is guessed
about land cover here: where a raster does not cover the domain the build says so
(an error for the terrain and the roughness, a warning for the curve number).

The domain is, in this order: the polygon of ``geometry``, the rectangle of ``bbox``,
or every cell where the terrain has data. A polygon or a rectangle must lie within the
terrain: a cell of the domain without elevation is an error, not a hole.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from hydraulik._optional import require
from hydraulik.data.tables import read_rain_table, read_station_table
from hydraulik.documents import notice
from hydraulik.engines.sfincs.model import ModelInputs, RegularGrid, precip_breakpoints
from hydraulik.exceptions import InputDataError, InvalidInputError
from hydraulik.model.options import DEFAULT_MANNING, BuildOptions
from hydraulik.terrain.grid import (
    Extent,
    edge_cells,
    grid_for_extent,
    model_epsg,
    polygon_mask,
    raster_extent,
    read_geometry,
    resample_raster,
)

__all__ = ["BuiltModel", "build_inputs", "plan_grid"]

Float = NDArray[np.float64]
Bool = NDArray[np.bool_]


@dataclass(frozen=True)
class BuiltModel:
    """The inputs of the model and what was done to make them.

    Attributes
    ----------
    inputs : ModelInputs
        Ready for :func:`~hydraulik.engines.sfincs.model.write_model`.
    report : dict
        The body of the ``hydraulik-model/1`` document: ``grid``, ``domain``,
        ``elevation``, ``roughness``, ``infiltration``, ``rain``, ``outlet`` and
        ``observation_points``.
    notices : list of dict
        Notices for the result: defaults that were applied and gaps that were found.
    """

    inputs: ModelInputs
    report: dict[str, Any]
    notices: list[dict[str, str]]


def _bbox_shape(bbox: tuple[float, float, float, float], crs: str, epsg: int) -> Any:
    """Return the rectangle ``bbox`` given in ``crs`` as a shape in the model CRS."""
    pyproj = require("pyproj", "model")
    geopandas = require("geopandas", "model")
    shapely = require("shapely.geometry", "model")
    min_x, min_y, max_x, max_y = bbox
    if not (min_x < max_x and min_y < max_y):
        raise InvalidInputError(
            "--bbox is min_x,min_y,max_x,max_y and each minimum must be below its "
            "maximum",
            details={"option": "bbox", "value": str(list(bbox))},
            reason="invalid_bbox",
        )
    try:
        source = pyproj.CRS.from_user_input(crs)
    except pyproj.exceptions.CRSError as exc:
        raise InvalidInputError(
            f"--crs {crs!r} is not a CRS: {exc}",
            details={"option": "crs", "value": crs},
            hint="Name it by its EPSG code, for example EPSG:2180 or EPSG:4326.",
            reason="invalid_crs",
        ) from exc
    series = geopandas.GeoSeries([shapely.box(min_x, min_y, max_x, max_y)], crs=source)
    return series.to_crs(epsg=epsg).iloc[0]


def plan_grid(options: BuildOptions) -> tuple[RegularGrid, Any, dict[str, Any]]:
    """Return the grid, the shape of the domain and its description.

    Parameters
    ----------
    options : BuildOptions
        The request.

    Returns
    -------
    tuple
        The grid, the shape of the domain in the model CRS (``None`` when the domain is
        the terrain itself) and the ``domain`` entry of the document.

    Raises
    ------
    NotFoundError, InputDataError, UnsupportedError, InvalidInputError
        If a raster or a vector file is missing or unusable, the CRS of the first
        elevation raster is not a metric EPSG CRS, ``--bbox`` is malformed, or the grid
        is empty or too large.
    """
    epsg = model_epsg(options.dem[0])
    shape: Any = None
    domain: dict[str, Any] = {"source": "dem"}
    if options.geometry is not None:
        shape = read_geometry(options.geometry, options.layer, epsg)
        domain = {
            "source": "geometry",
            "path": str(options.geometry),
            "layer": options.layer,
        }
    elif options.bbox is not None:
        assert options.crs is not None  # the operation refuses --bbox without --crs
        shape = _bbox_shape(options.bbox, options.crs, epsg)
        domain = {
            "source": "bbox",
            "bbox": list(options.bbox),
            "crs": options.crs,
        }
    if shape is not None:
        bounds = shape.bounds
        extent: Extent = (
            float(bounds[0]),
            float(bounds[1]),
            float(bounds[2]),
            float(bounds[3]),
        )
    else:
        extents = [raster_extent(path, epsg) for path in options.dem]
        extent = (
            min(e[0] for e in extents),
            min(e[1] for e in extents),
            max(e[2] for e in extents),
            max(e[3] for e in extents),
        )
    return grid_for_extent(extent, options.dx_m, epsg), shape, domain


def _statistics(values: Float, where: Bool) -> dict[str, float]:
    """Return the minimum, mean and maximum of ``values`` over the cells ``where``."""
    chosen = values[where & np.isfinite(values)]
    return {
        "min": float(chosen.min()),
        "mean": float(chosen.mean()),
        "max": float(chosen.max()),
    }


def _elevation(paths: tuple[Path, ...], grid: RegularGrid) -> tuple[Float, list[Any]]:
    """Put the elevation rasters on the grid; the first wins where they overlap."""
    merged: Float = np.full(grid.shape, np.nan)
    sources: list[dict[str, Any]] = []
    for path in paths:
        layer = resample_raster(path, grid)
        fill = np.isnan(merged) & np.isfinite(layer.values)
        merged[fill] = layer.values[fill]
        sources.append(
            {
                "path": str(path),
                "cell_size_m": layer.cell_size_m,
                "resampling": layer.resampling,
                "cells": int(fill.sum()),
            }
        )
    return merged, sources


def _first_gap(gaps: Bool, grid: RegularGrid) -> dict[str, float]:
    """Return the centre of the first (south-west) cell of ``gaps`` for a hint."""
    row, column = np.argwhere(gaps)[0]
    x_m, y_m = grid.centre_of(int(row), int(column))
    return {"x_m": x_m, "y_m": y_m}


def build_inputs(options: BuildOptions) -> BuiltModel:
    """Read the rasters and put them on one grid.

    Parameters
    ----------
    options : BuildOptions
        The request.

    Returns
    -------
    BuiltModel
        The inputs of the model, the report and the notices.

    Raises
    ------
    NotFoundError
        If a file does not exist.
    InputDataError
        If a raster or a table cannot be read, a domain cell has no elevation (reason
        ``dem_gaps``) or no Manning ``n`` (``manning_gaps``), or a retention is
        negative (``invalid_retention``).
    UnsupportedError
        If the CRS of the first elevation raster is not a metric EPSG CRS.
    InvalidInputError
        If the domain holds no cell, the outlet lies outside the domain or not on its
        edge, or a station is outside it.
    """
    grid, shape, domain = plan_grid(options)
    elevation, sources = _elevation(options.dem, grid)
    valid = np.isfinite(elevation)
    notices: list[dict[str, str]] = []
    if shape is None:
        active = valid
    else:
        active = polygon_mask(shape, grid, all_touched=False)
        gaps = active & ~valid
        if gaps.any():
            raise InputDataError(
                f"{int(gaps.sum())} of the {int(active.sum())} cells of the domain "
                "have no elevation",
                details={
                    "cells": int(gaps.sum()),
                    "domain_cells": int(active.sum()),
                    **_first_gap(gaps, grid),
                },
                hint="Give elevation rasters that cover the whole domain, or shrink "
                "--bbox or --geometry.",
                reason="dem_gaps",
            )
    if not active.any():
        raise InvalidInputError(
            "the domain holds no cell: no cell centre lies inside it and on the "
            "elevation",
            details={"option": "dx_m", "value": options.dx_m},
            hint="Check that the domain overlaps the elevation rasters, or use a "
            "smaller --dx-m.",
            reason="empty_domain",
        )
    elevation = np.where(active, elevation, np.nan)

    manning: float | Float
    if options.manning_raster is not None:
        layer = resample_raster(options.manning_raster, grid)
        gaps = active & ~np.isfinite(layer.values)
        if gaps.any():
            raise InputDataError(
                f"{int(gaps.sum())} cells of the domain have no Manning n",
                details={"cells": int(gaps.sum()), **_first_gap(gaps, grid)},
                hint="Give a Manning raster that covers the domain, or a uniform "
                "--manning.",
                reason="manning_gaps",
            )
        manning = layer.values
        roughness: dict[str, Any] = {
            "source": "raster",
            "path": str(options.manning_raster),
            "resampling": layer.resampling,
            **{f"{k}_s_m13": v for k, v in _statistics(manning, active).items()},
        }
    else:
        manning = DEFAULT_MANNING if options.manning is None else options.manning
        roughness = {"source": "uniform", "value_s_m13": manning}
        if options.manning is None:
            notices.append(
                notice(
                    "info",
                    "manning_default",
                    f"no Manning option: n = {DEFAULT_MANNING:g} s/m^(1/3) everywhere",
                )
            )

    curve_number: Float | None = None
    infiltration: dict[str, Any] | None = None
    if options.curve_number_raster is not None:
        layer = resample_raster(options.curve_number_raster, grid)
        curve_number = layer.values
        origin = {
            "source": "curve_number_raster",
            "path": str(options.curve_number_raster),
        }
    elif options.retention_mm_raster is not None:
        layer = resample_raster(options.retention_mm_raster, grid)
        retention = layer.values
        if np.nanmin(np.where(active, retention, np.inf)) < 0.0:
            raise InputDataError(
                "the retention raster has negative values",
                details={"path": str(options.retention_mm_raster)},
                hint="SCS retention S is in mm and not negative.",
                reason="invalid_retention",
            )
        curve_number = 25400.0 / (retention + 254.0)
        origin = {
            "source": "retention_mm_raster",
            "path": str(options.retention_mm_raster),
        }
    if curve_number is not None:
        missing = active & ~np.isfinite(curve_number)
        infiltration = {
            **origin,
            "resampling": layer.resampling,
            "gap_cells": int(missing.sum()),
            "initial_abstraction": 0.2,
        }
        if missing.all():
            raise InputDataError(
                "the infiltration raster covers no cell of the domain",
                details={"path": origin["path"]},
                hint="Check its CRS and extent.",
                reason="cn_gaps",
            )
        infiltration["curve_number"] = _statistics(curve_number, active)
        if missing.any():
            notices.append(
                notice(
                    "warning",
                    "cn_gaps",
                    f"{int(missing.sum())} cells of the domain have no curve number: "
                    "no infiltration there, all rain becomes runoff",
                )
            )
    else:
        notices.append(
            notice(
                "info",
                "no_infiltration",
                "no curve number or retention raster: infiltration is off and all rain "
                "becomes runoff",
            )
        )

    table = read_rain_table(options.rain)
    rain_end_s = table.duration_min * 60.0
    tstop_s = float(math.ceil(rain_end_s + options.recession_min * 60.0))
    precip = precip_breakpoints(list(table.depth_mm), table.step_min * 60.0, tstop_s)

    outflow: Bool | None = None
    outlet: dict[str, Any] | None = None
    if options.outlet is not None:
        line = read_geometry(options.outlet, options.outlet_layer, grid.epsg)
        touched = polygon_mask(line, grid, all_touched=True) & active
        if not touched.any():
            raise InvalidInputError(
                "the outlet does not touch the domain",
                details={"option": "outlet", "value": str(options.outlet)},
                hint="Draw the outlet across the edge of the domain where the water "
                "leaves, in any CRS the file declares.",
                reason="outlet_outside_domain",
            )
        outflow = touched & edge_cells(active)
        if not outflow.any():
            raise InvalidInputError(
                "the outlet lies inside the domain, not on its edge",
                details={"option": "outlet", "value": str(options.outlet)},
                hint="Only a cell at the edge of the domain can let the water out.",
                reason="outlet_not_on_edge",
            )
        outlet = {
            "path": str(options.outlet),
            "layer": options.outlet_layer,
            "cells": int(outflow.sum()),
        }
    else:
        notices.append(
            notice(
                "info",
                "closed_boundary",
                "no outlet: the boundary is closed and the water stays in the model",
            )
        )

    stations = (
        read_station_table(options.observation_points)
        if options.observation_points is not None
        else ()
    )
    for x_m, y_m, name in stations:
        cell = grid.cell_of(x_m, y_m)
        if cell is not None and not active[cell]:
            raise InvalidInputError(
                f"station {name} lies outside the domain",
                details={"option": "observation_points", "value": name},
                hint="Put the stations on cells of the domain.",
                reason="station_outside_domain",
            )

    inputs = ModelInputs(
        grid=grid,
        elevation_m=elevation,
        active=active,
        precip=precip,
        tstop_s=tstop_s,
        outflow=outflow,
        manning=manning,
        curve_number=curve_number,
        observation_points=stations,
        dtout_s=tstop_s,
        dthisout_s=min(60.0, tstop_s),
    )
    inputs.validate()
    report: dict[str, Any] = {
        "grid": {
            "epsg": grid.epsg,
            "dx_m": grid.dx_m,
            "x0_m": grid.x0_m,
            "y0_m": grid.y0_m,
            "rows": grid.rows,
            "columns": grid.columns,
            "cells": grid.rows * grid.columns,
            "active_cells": int(active.sum()),
            "area_m2": float(active.sum()) * grid.dx_m * grid.dx_m,
            "outflow_cells": 0 if outflow is None else int(outflow.sum()),
        },
        "domain": domain,
        "elevation": {
            **{f"{k}_m": v for k, v in _statistics(elevation, active).items()},
            "sources": sources,
        },
        "roughness": roughness,
        "infiltration": infiltration,
        "rain": {
            "path": str(options.rain),
            "total_mm": table.total_mm,
            "duration_min": table.duration_min,
            "timestep_min": table.step_min,
            "peak_intensity_mm_h": table.peak_intensity_mm_h,
            "recession_min": options.recession_min,
            "tstop_s": tstop_s,
        },
        "outlet": outlet,
        "observation_points": [
            {"name": name, "x_m": x_m, "y_m": y_m} for x_m, y_m, name in stations
        ],
    }
    return BuiltModel(inputs, report, notices)
