"""The grid of a model and the rasters that fill it (ADR-0004).

A model is built on a regular grid of square cells that is aligned to its cell size: the
corner of the grid is a multiple of ``dx_m``, so models built from the same terrain with
the same cell size share their cell edges. The CRS of the grid is the CRS of the first
elevation raster; it must be projected, in metres and have an EPSG code (SFINCS reads
``epsg`` and ``dx`` in metres).

Every array that this module returns is shaped ``(rows, columns)`` with row 0 at the
**south** edge, the order of SFINCS (:mod:`hydraulik.engines.sfincs.model`); a raster is
north-up on disk and is flipped here, so nothing else has to think about it.

A raster is brought onto the grid with ``rasterio.warp.reproject``: the mean of the
source cells when they are finer than the grid (a 1 m terrain averaged to 5 m keeps
the volume of the terrain), bilinear interpolation otherwise. A cell that no source
cell covers is NaN. Needs the ``model`` extra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

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

__all__ = [
    "MAX_CELLS",
    "Extent",
    "Resampled",
    "edge_cells",
    "grid_for_extent",
    "model_epsg",
    "polygon_mask",
    "raster_extent",
    "read_geometry",
    "resample_raster",
]

MAX_CELLS: Final = 25_000_000
"""The most cells a model may have: about 200 MB for each array of the build."""

Float = NDArray[np.float64]
Bool = NDArray[np.bool_]
Extent = tuple[float, float, float, float]
"""``(min_x, min_y, max_x, max_y)`` in the CRS of the grid [m]."""

_METRE: Final = ("metre", "meter")


@dataclass(frozen=True)
class Resampled:
    """A raster on the grid and how it got there.

    Attributes
    ----------
    values : ndarray
        The raster on the grid, shape ``(rows, columns)``, row 0 south; NaN where no
        source cell covers the cell or the source has no data.
    cell_size_m : float
        Cell size of the source in the CRS of the grid [m].
    resampling : {"average", "bilinear"}
        How the source was brought onto the grid.
    """

    values: Float
    cell_size_m: float
    resampling: str


def _open(path: Path) -> Any:
    """Open a raster, or raise ``not_found`` or ``data_error`` with its name."""
    rasterio = require("rasterio", "model")
    if not path.is_file():
        raise NotFoundError(
            f"raster not found: {path}",
            details={"path": str(path)},
            reason="path_missing",
        )
    try:
        return rasterio.open(path)
    except Exception as exc:  # noqa: BLE001 - rasterio raises several error types
        raise InputDataError(
            f"{path.name} is not a raster that GDAL can read: {exc}",
            details={"path": str(path)},
            hint="Give a GeoTIFF or another raster with a CRS.",
            reason="raster_unreadable",
        ) from exc


def model_epsg(path: Path) -> int:
    """Return the EPSG code of the CRS of a raster, which becomes the CRS of the model.

    Parameters
    ----------
    path : Path
        The first elevation raster.

    Returns
    -------
    int
        The EPSG code of its projected CRS.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If the raster has no CRS (reason ``crs_missing``) or cannot be read.
    UnsupportedError
        If the CRS has no EPSG code, is not projected or is not in metres (reason
        ``crs_not_supported``).
    """
    with _open(path) as source:
        crs = source.crs
    if crs is None:
        raise InputDataError(
            f"{path.name} has no CRS",
            details={"path": str(path)},
            hint="Assign the CRS of the data to the raster, for Poland EPSG:2180.",
            reason="crs_missing",
        )
    epsg = crs.to_epsg()
    if epsg is None or not crs.is_projected or crs.linear_units.lower() not in _METRE:
        raise UnsupportedError(
            f"the CRS of {path.name} is not projected, in metres, with an EPSG code",
            details={"path": str(path), "crs": crs.to_string()[:80]},
            hint="Reproject the raster to a metric CRS, for Poland EPSG:2180.",
            reason="crs_not_supported",
        )
    return int(epsg)


def raster_extent(path: Path, epsg: int) -> Extent:
    """Return the bounds of a raster in the CRS of the model.

    Parameters
    ----------
    path : Path
        The raster.
    epsg : int
        EPSG code of the CRS of the model.

    Returns
    -------
    tuple of float
        ``(min_x, min_y, max_x, max_y)`` [m]; for another CRS the box that holds the
        reprojected raster.
    """
    warp = require("rasterio.warp", "model")
    with _open(path) as source:
        if source.crs is None:
            raise InputDataError(
                f"{path.name} has no CRS",
                details={"path": str(path)},
                reason="crs_missing",
            )
        bounds = warp.transform_bounds(
            source.crs, f"EPSG:{epsg}", *source.bounds, densify_pts=21
        )
    return (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))


def grid_for_extent(extent: Extent, dx_m: float, epsg: int) -> RegularGrid:
    """Return the grid of cells of ``dx_m`` that covers an extent, aligned to ``dx_m``.

    The lower-left corner is rounded down to a multiple of ``dx_m``, so grids of the
    same cell size built from different areas share their cell edges.

    Parameters
    ----------
    extent : tuple of float
        ``(min_x, min_y, max_x, max_y)`` [m].
    dx_m : float
        Cell size [m].
    epsg : int
        EPSG code of the CRS of the extent.

    Returns
    -------
    RegularGrid
        The grid.

    Raises
    ------
    InvalidInputError
        If the extent is empty or the grid would have more than :data:`MAX_CELLS` cells
        (reason ``grid_too_large``).

    Examples
    --------
    >>> grid = grid_for_extent((101.0, 202.0, 119.5, 209.0), 5.0, 2180)
    >>> (grid.x0_m, grid.y0_m, grid.columns, grid.rows)
    (100.0, 200.0, 4, 2)
    """
    min_x, min_y, max_x, max_y = extent
    if not (max_x > min_x and max_y > min_y) or dx_m <= 0:
        raise InvalidInputError(
            "the extent of the domain is empty",
            details={"option": "dx_m", "value": dx_m},
            reason="empty_domain",
        )
    x0 = math.floor(min_x / dx_m + 1e-9) * dx_m
    y0 = math.floor(min_y / dx_m + 1e-9) * dx_m
    columns = math.ceil(round((max_x - x0) / dx_m, 6))
    rows = math.ceil(round((max_y - y0) / dx_m, 6))
    if columns * rows > MAX_CELLS:
        raise InvalidInputError(
            f"the grid would have {columns} x {rows} = {columns * rows} cells, "
            f"more than {MAX_CELLS}",
            details={"option": "dx_m", "value": dx_m, "columns": columns, "rows": rows},
            hint="Use a larger --dx-m or a smaller domain (--bbox or --geometry).",
            reason="grid_too_large",
        )
    return RegularGrid(float(x0), float(y0), float(dx_m), columns, rows, epsg)


def _transform(grid: RegularGrid) -> Any:
    """Return the affine transform of the north-up version of the grid."""
    transform = require("rasterio.transform", "model")
    return transform.from_origin(
        grid.x0_m, grid.y0_m + grid.rows * grid.dx_m, grid.dx_m, grid.dx_m
    )


def resample_raster(path: Path, grid: RegularGrid) -> Resampled:
    """Bring band 1 of a raster onto the grid.

    Parameters
    ----------
    path : Path
        The raster; its nodata value marks cells without data.
    grid : RegularGrid
        The grid to fill.

    Returns
    -------
    Resampled
        The values on the grid (row 0 south, NaN where there is no data), the cell size
        of the source and the resampling that was used: ``average`` when the source
        cells are finer than the grid, ``bilinear`` otherwise.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If the raster cannot be read or has no CRS.
    """
    rasterio = require("rasterio", "model")
    enums = require("rasterio.enums", "model")
    warp = require("rasterio.warp", "model")
    target = f"EPSG:{grid.epsg}"
    destination = np.full(grid.shape, np.nan, dtype=np.float64)
    with _open(path) as source:
        if source.crs is None:
            raise InputDataError(
                f"{path.name} has no CRS",
                details={"path": str(path)},
                hint="Assign the CRS of the data to the raster.",
                reason="crs_missing",
            )
        if source.crs == rasterio.crs.CRS.from_string(target):
            cell_size = abs(float(source.res[0]))
        else:
            transform, _, _ = warp.calculate_default_transform(
                source.crs, target, source.width, source.height, *source.bounds
            )
            cell_size = abs(float(transform.a))
        method = (
            enums.Resampling.average
            if cell_size < grid.dx_m - 1e-9
            else enums.Resampling.bilinear
        )
        warp.reproject(
            source=rasterio.band(source, 1),
            destination=destination,
            dst_transform=_transform(grid),
            dst_crs=target,
            src_nodata=source.nodata,
            dst_nodata=np.nan,
            resampling=method,
        )
    destination[~np.isfinite(destination)] = np.nan
    return Resampled(np.flipud(destination), cell_size, method.name)


def read_geometry(path: Path, layer: str | None, epsg: int) -> Any:
    """Read a vector file and return its geometries as one shape in the model CRS.

    Parameters
    ----------
    path : Path
        A vector file that geopandas reads (GeoPackage, GeoJSON, Shapefile, ...).
    layer : str or None
        The layer of a multi-layer file; the first layer when ``None``.
    epsg : int
        EPSG code of the CRS of the model; the geometries are reprojected to it.

    Returns
    -------
    shapely.geometry.base.BaseGeometry
        The union of every geometry of the layer.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If it cannot be read, has no CRS (reason ``crs_missing``) or holds no geometry
        (reason ``empty_geometry``).
    """
    geopandas = require("geopandas", "model")
    if not path.is_file():
        raise NotFoundError(
            f"vector file not found: {path}",
            details={"path": str(path)},
            reason="path_missing",
        )
    try:
        frame = geopandas.read_file(path, layer=layer)
    except Exception as exc:  # noqa: BLE001 - the readers raise several error types
        raise InputDataError(
            f"{path.name} cannot be read as a vector layer: {exc}",
            details={"path": str(path), "layer": layer},
            hint="Name an existing layer with --layer or --outlet-layer.",
            reason="vector_unreadable",
        ) from exc
    if frame.crs is None:
        raise InputDataError(
            f"{path.name} has no CRS",
            details={"path": str(path)},
            hint="Assign the CRS of the data to the layer.",
            reason="crs_missing",
        )
    shapes = frame.to_crs(epsg=epsg).geometry.dropna()
    shapes = shapes[~shapes.is_empty]
    if shapes.empty:
        raise InputDataError(
            f"{path.name} holds no geometry",
            details={"path": str(path), "layer": layer},
            reason="empty_geometry",
        )
    return shapes.union_all()


def polygon_mask(shape: Any, grid: RegularGrid, *, all_touched: bool) -> Bool:
    """Mark the cells of the grid that a shape covers.

    Parameters
    ----------
    shape : shapely geometry
        In the CRS of the grid.
    grid : RegularGrid
        The grid.
    all_touched : bool
        True marks every cell the shape touches (a line or a point of an outlet), False
        only the cells whose centre lies inside it (a domain).

    Returns
    -------
    ndarray of bool
        Shape ``(rows, columns)``, row 0 south.
    """
    features = require("rasterio.features", "model")
    mask = features.rasterize(
        [(shape, 1)],
        out_shape=grid.shape,
        transform=_transform(grid),
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    )
    marked: Bool = np.flipud(mask).astype(bool)
    return marked


def edge_cells(active: Bool) -> Bool:
    """Return the active cells that touch the edge of the domain.

    A cell is on the edge when one of its four neighbours is not active or lies outside
    the grid.

    Parameters
    ----------
    active : ndarray of bool
        The domain.

    Returns
    -------
    ndarray of bool
        The cells of ``active`` with a neighbour outside the domain.

    Examples
    --------
    >>> import numpy as np
    >>> edge_cells(np.ones((3, 3), dtype=bool)).sum()
    8
    """
    padded = np.pad(active, 1, constant_values=False)
    inside = padded[2:, 1:-1] & padded[:-2, 1:-1] & padded[1:-1, 2:] & padded[1:-1, :-2]
    result: Bool = active & ~inside
    return result
