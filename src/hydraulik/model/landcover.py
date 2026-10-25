"""BDOT10k land cover to Manning ``n`` and the curve number on the grid (ADR-0007).

The features of a BDOT10k GeoPackage are painted as classes (``mapping.csv``) on a grid
finer than the model, in the order of the mapping: polygons of the land-cover layers,
then the roads (``OT_SKJZ_L``, lines buffered by half their width) and last the
buildings (``OT_BUBD_A``, a mask over the classes). The share of each class in a cell of
the model then gives

* Manning ``n``: the area-weighted mean of the ``n`` of the classes;
* the curve number: the area-weighted mean of the ``CN`` of the classes for the soil
  group of the cell (the composite curve number of TR-55, figure 2-3).

The fine grid has cells of about 1 m (at most ten to a cell of the model) and is painted
tile by tile, so the memory stays at a few tens of megabytes whatever the size of the
model. A tile is a block of cells of the model; every array of this module is shaped
``(rows, columns)`` with row 0 at the **south**, like the rest of the build.

Roads are lines in BDOT10k. Those that lie on the ground are painted with the width of
their surface (``SZEROKOSCNAWIERZCHNI``), 5 m where it is missing; bridges, tunnels and
the conventional lines that join roads across a crossing are not painted.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from hydraulik._optional import require
from hydraulik.documents import notice
from hydraulik.engines.sfincs.model import RegularGrid
from hydraulik.exceptions import InputDataError, NotFoundError
from hydraulik.model.classes import (
    BUILDING,
    OTHER_VALUES,
    UNCLASSIFIED,
    ClassTable,
    MappingRow,
    load_mapping,
    normalise,
)

__all__ = [
    "BUILDING_SHARE",
    "DEFAULT_ROAD_WIDTH_M",
    "LandCoverResult",
    "build_landcover",
    "subdivision",
]

Float = NDArray[np.float64]
Bool = NDArray[np.bool_]

DEFAULT_ROAD_WIDTH_M: Final = 5.0
"""Width of the surface of a road that BDOT10k gives none for [m]."""

BUILDING_SHARE: Final = 0.5
"""Share of the area of a cell under roofs from which the cell counts as a building."""

_SUB_CELL_M: Final = 1.0
_MAX_SUB: Final = 10
_TILE_SUBCELLS: Final = 1 << 22
_TILE_CELLS: Final = 1 << 18
_MARGIN_M: Final = 30.0
_WIDTH_FIELD: Final = "SZEROKOSCNAWIERZCHNI"
_POSITION_FIELD: Final = "POLOZENIE"
_ON_GROUND: Final = "na powierzchni gruntu"
_GEOMETRY_FIELD: Final = "CECHAGEOMETRII"
_CONVENTIONAL: Final = "linia umowna"


@dataclass(frozen=True)
class LandCoverResult:
    """What the land cover gives the model.

    Attributes
    ----------
    manning : ndarray
        Manning ``n`` of each cell of the domain [s/m^(1/3)]; NaN elsewhere.
    curve_number : ndarray or None
        Curve number of each cell of the domain; NaN where the soil group is unknown.
        ``None`` when no soil group was given.
    building_fraction : ndarray
        Share of each cell under roofs, 0 to 1.
    report : dict
        The ``landcover`` entry of the ``hydraulik-model/1`` document.
    notices : list of dict
        Warnings and remarks for the result.
    """

    manning: Float
    curve_number: Float | None
    building_fraction: Float
    report: dict[str, Any]
    notices: list[dict[str, str]]


def subdivision(dx_m: float) -> int:
    """Return how many cells of the painting grid make one side of a cell of the model.

    Parameters
    ----------
    dx_m : float
        Cell size of the model [m].

    Returns
    -------
    int
        The number of painted cells per side, 1 to 10: the painting cell is about 1 m,
        the accuracy of BDOT10k, and never more than a tenth of a cell of the model.

    Examples
    --------
    >>> subdivision(5.0), subdivision(0.5), subdivision(50.0)
    (5, 1, 10)
    """
    return max(1, min(_MAX_SUB, round(dx_m / _SUB_CELL_M)))


def _tiles(rows: int, columns: int, sub: int) -> Iterator[tuple[slice, slice]]:
    """Yield blocks of cells of the model whose painted raster has a bounded size."""
    side = max(1, min(math.isqrt(_TILE_SUBCELLS) // sub, math.isqrt(_TILE_CELLS)))
    for row in range(0, rows, side):
        for column in range(0, columns, side):
            yield (
                slice(row, min(row + side, rows)),
                slice(column, min(column + side, columns)),
            )


@dataclass
class _Layer:
    """The geometries of one row of the mapping, ready to be painted."""

    code: int
    building: bool
    geometry: Any
    tree: Any


def _read(
    path: Path, grid: RegularGrid, layers: Sequence[str]
) -> tuple[dict[str, Any], list[str]]:
    """Read the layers that the file has, within the extent of the grid and a margin."""
    geopandas = require("geopandas", "model")
    shapely = require("shapely.geometry", "model")
    if not path.is_file():
        raise NotFoundError(
            f"land-cover file not found: {path}",
            details={"path": str(path)},
            reason="path_missing",
        )
    try:
        present = set(geopandas.list_layers(path)["name"])
    except Exception as exc:  # noqa: BLE001 - the readers raise several error types
        raise InputDataError(
            f"{path.name} cannot be read as a vector file: {exc}",
            details={"path": str(path)},
            hint="Give the BDOT10k GeoPackage that `terrain download` writes.",
            reason="vector_unreadable",
        ) from exc
    wanted = [layer for layer in dict.fromkeys(layers) if layer in present]
    missing = [layer for layer in dict.fromkeys(layers) if layer not in present]
    if not any(layer.startswith("OT_PT") for layer in wanted):
        raise InputDataError(
            f"{path.name} has none of the land-cover layers of BDOT10k (OT_PT*_A)",
            details={"path": str(path), "layers": sorted(present)[:20]},
            hint="Give the BDOT10k GeoPackage that `terrain download` writes.",
            reason="landcover_layers_missing",
        )
    extent = shapely.box(
        grid.x0_m - _MARGIN_M,
        grid.y0_m - _MARGIN_M,
        grid.x0_m + grid.columns * grid.dx_m + _MARGIN_M,
        grid.y0_m + grid.rows * grid.dx_m + _MARGIN_M,
    )
    area = geopandas.GeoSeries([extent], crs=f"EPSG:{grid.epsg}")
    frames: dict[str, Any] = {}
    for layer in wanted:
        try:
            frame = geopandas.read_file(path, layer=layer, bbox=area)
        except Exception as exc:  # noqa: BLE001 - the readers raise several error types
            raise InputDataError(
                f"layer {layer} of {path.name} cannot be read: {exc}",
                details={"path": str(path), "layer": layer},
                reason="vector_unreadable",
            ) from exc
        if frame.crs is None:
            raise InputDataError(
                f"layer {layer} of {path.name} has no CRS",
                details={"path": str(path), "layer": layer},
                reason="crs_missing",
            )
        frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
        frame = frame.to_crs(epsg=grid.epsg)
        if len(frame) and not frame.geometry.is_valid.all():
            frame = frame.assign(geometry=frame.geometry.make_valid())
        frames[layer] = frame.reset_index(drop=True)
    return frames, missing


def _roads(frame: Any) -> tuple[Any, dict[str, int]]:
    """Return the roads on the ground as polygons of the width of their surface."""
    pandas = require("pandas", "model")
    stats = {
        "features": len(frame),
        "skipped_not_on_ground": 0,
        "skipped_conventional": 0,
        "default_width": 0,
    }
    keep = np.ones(len(frame), dtype=bool)
    if _POSITION_FIELD in frame:
        ground = frame[_POSITION_FIELD].map(
            lambda value: pandas.isna(value) or normalise(value) == _ON_GROUND
        )
        stats["skipped_not_on_ground"] = int((~ground).sum())
        keep &= ground.to_numpy(dtype=bool)
    if _GEOMETRY_FIELD in frame:
        conventional = frame[_GEOMETRY_FIELD].map(
            lambda value: not pandas.isna(value) and normalise(value) == _CONVENTIONAL
        )
        stats["skipped_conventional"] = int((conventional & keep).sum())
        keep &= ~conventional.to_numpy(dtype=bool)
    frame = frame[keep].reset_index(drop=True)
    if _WIDTH_FIELD in frame:
        width = pandas.to_numeric(frame[_WIDTH_FIELD], errors="coerce").to_numpy(float)
    else:
        width = np.full(len(frame), np.nan)
    missing = ~(np.isfinite(width) & (width > 0))
    stats["default_width"] = int(missing.sum())
    width = np.where(missing, DEFAULT_ROAD_WIDTH_M, width)
    buffered = frame.geometry.buffer(width / 2.0, cap_style="flat")
    return frame.assign(geometry=buffered), stats


def _paint_rows(
    frames: dict[str, Any], mapping: Sequence[MappingRow], table: ClassTable
) -> tuple[list[_Layer], dict[str, Any]]:
    """Select the features of every row of the mapping, in painting order."""
    pandas = require("pandas", "model")
    painted: list[_Layer] = []
    report: dict[str, Any] = {"roads": None, "unmapped": []}
    by_layer: dict[str, list[MappingRow]] = {}
    for row in mapping:
        by_layer.setdefault(row.layer, []).append(row)
    prepared: dict[str, Any] = {}
    for layer, frame in frames.items():
        if layer.endswith("_L"):
            frame, stats = _roads(frame)
            report["roads"] = stats
        prepared[layer] = frame
    explicit: dict[tuple[str, str], set[str]] = {}
    for row in mapping:
        if row.field is not None and row.value != OTHER_VALUES:
            explicit.setdefault((row.layer, row.field), set()).add(normalise(row.value))
    starred = {(row.layer, row.field) for row in mapping if row.value == OTHER_VALUES}
    normalised: dict[tuple[str, str], Any] = {}
    for (layer, field), known_values in explicit.items():
        frame = prepared.get(layer)
        if frame is None:
            continue
        if field not in frame:
            report["unmapped"].append(
                {"layer": layer, "field": field, "value": None, "features": len(frame)}
            )
            continue
        normalised[(layer, field)] = frame[field].map(
            lambda value: None if pandas.isna(value) else normalise(value)
        )
        if (layer, field) in starred:
            continue
        known = normalised[(layer, field)].isin(known_values)
        for raw, count in Counter(frame.loc[~known, field].astype(str)).items():
            report["unmapped"].append(
                {"layer": layer, "field": field, "value": raw, "features": count}
            )
    for row in mapping:
        frame = prepared.get(row.layer)
        if frame is None or not len(frame):
            continue
        if row.field is None:
            mask = np.ones(len(frame), dtype=bool)
        else:
            series = normalised.get((row.layer, row.field))
            if series is None:
                continue
            if row.value == OTHER_VALUES:
                mask = ~series.isin(explicit[(row.layer, row.field)]).to_numpy(bool)
            else:
                mask = (series == normalise(row.value)).to_numpy(bool)
        geometry = frame.geometry[mask].reset_index(drop=True)
        if not len(geometry):
            continue
        painted.append(
            _Layer(
                table.index(row.class_name),
                row.class_name == BUILDING,
                geometry,
                geometry.sindex,
            )
        )
    return painted, report


def _paint_tile(
    rows: Sequence[_Layer],
    extent: tuple[float, float, float, float],
    shape: tuple[int, int],
    sub_m: float,
    fill: int,
) -> tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """Paint one tile; return the classes and the roofs, row 0 at the north."""
    features = require("rasterio.features", "model")
    transform = require("rasterio.transform", "model").from_origin(
        extent[0], extent[3], sub_m, sub_m
    )
    shapely = require("shapely.geometry", "model")
    box = shapely.box(*extent)
    canvas = np.full(shape, fill, dtype=np.uint8)
    roofs = np.zeros(shape, dtype=np.uint8)
    for row in rows:
        hits = row.tree.query(box, predicate="intersects")
        if not len(hits):
            continue
        shapes = [
            (geometry, 1 if row.building else row.code)
            for geometry in row.geometry.iloc[hits]
        ]
        features.rasterize(
            shapes,
            out=roofs if row.building else canvas,
            transform=transform,
            all_touched=False,
        )
    return canvas, roofs


def _shares(
    canvas: NDArray[np.uint8],
    roofs: NDArray[np.uint8],
    codes: int,
    sub: int,
    cells: tuple[int, int],
) -> tuple[Float, Float, Float]:
    """Return the shares of the classes in the cells of a painted tile.

    The result is the share of each class in each cell under any roof or not, the share
    of each class free of roofs, and the share of the roofs; row 0 is at the south.
    """
    rows, columns = cells
    under_all = np.zeros((codes, rows, columns))
    free = np.zeros((codes, rows, columns))
    covered = roofs.astype(bool)
    area = float(sub * sub)
    for code in np.unique(canvas):
        hit = canvas == code
        under_all[code] = hit.reshape(rows, sub, columns, sub).sum(axis=(1, 3)) / area
        free[code] = (hit & ~covered).reshape(rows, sub, columns, sub).sum(
            axis=(1, 3)
        ) / area
    roof = covered.reshape(rows, sub, columns, sub).sum(axis=(1, 3)) / area
    return under_all[:, ::-1], free[:, ::-1], roof[::-1]


def build_landcover(
    path: Path,
    grid: RegularGrid,
    active: Bool,
    table: ClassTable,
    *,
    soil_groups: NDArray[np.int8] | None,
    building_roughness: bool,
) -> LandCoverResult:
    """Turn a BDOT10k GeoPackage into Manning ``n`` and curve numbers on the grid.

    Parameters
    ----------
    path : Path
        The GeoPackage (``terrain download`` writes it into ``landcover/``).
    grid : RegularGrid
        The grid of the model.
    active : ndarray of bool
        The cells of the domain; the tiles without one are not painted.
    table : ClassTable
        The classes and their values.
    soil_groups : ndarray of int8 or None
        The hydrologic soil group of each cell, 0 for A to 3 for D and -1 where it is
        unknown; ``None`` computes no curve number.
    building_roughness : bool
        Whether the roughness of the ``building`` class applies under the roofs. It
        does where the buildings are raised, because the water then runs off the roof;
        otherwise water crosses the footprint of a building like any other ground, and
        the ``n`` of the class under the roof is kept.

    Returns
    -------
    LandCoverResult
        The arrays, the report and the notices.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If it cannot be read as a vector file, has no BDOT10k land-cover layer
        (reason ``landcover_layers_missing``) or a layer has no CRS.
    """
    mapping = load_mapping(table)
    frames, missing = _read(path, grid, [row.layer for row in mapping])
    painted, report = _paint_rows(frames, mapping, table)
    sub = subdivision(grid.dx_m)
    sub_m = grid.dx_m / sub
    codes = len(table.classes)
    fill = table.index(UNCLASSIFIED)
    roof = table.index(BUILDING)
    manning_of = np.array([item.manning_n for item in table.classes])
    curve_of = np.array([item.curve_numbers for item in table.classes])
    manning = np.full(grid.shape, np.nan)
    curve_number = None if soil_groups is None else np.full(grid.shape, np.nan)
    building = np.zeros(grid.shape)
    area = np.zeros(codes)
    for rows_slice, columns_slice in _tiles(grid.rows, grid.columns, sub):
        domain = active[rows_slice, columns_slice]
        if not domain.any():
            continue
        rows, columns = domain.shape
        extent = (
            grid.x0_m + columns_slice.start * grid.dx_m,
            grid.y0_m + rows_slice.start * grid.dx_m,
            grid.x0_m + columns_slice.stop * grid.dx_m,
            grid.y0_m + rows_slice.stop * grid.dx_m,
        )
        canvas, roofs = _paint_tile(
            painted, extent, (rows * sub, columns * sub), sub_m, fill
        )
        under_all, free, covered = _shares(canvas, roofs, codes, sub, (rows, columns))
        if building_roughness:
            free_n = np.tensordot(manning_of, free, axes=1)
            n_cell = free_n + covered * manning_of[roof]
        else:
            n_cell = np.tensordot(manning_of, under_all, axes=1)
        manning[rows_slice, columns_slice] = n_cell
        building[rows_slice, columns_slice] = covered
        shares = free.copy()
        shares[roof] = covered
        area += (shares * domain).sum(axis=(1, 2)) * grid.dx_m * grid.dx_m
        if soil_groups is not None and curve_number is not None:
            groups = soil_groups[rows_slice, columns_slice]
            known = groups >= 0
            column = np.where(known, groups, 0).astype(np.intp)
            total = np.zeros((rows, columns))
            for code in range(codes):
                if shares[code].any():
                    total += shares[code] * curve_of[code][column]
            curve_number[rows_slice, columns_slice] = np.where(known, total, np.nan)
    manning = np.where(active, manning, np.nan)
    if curve_number is not None:
        curve_number = np.where(active, curve_number, np.nan)
    total_area = float(active.sum()) * grid.dx_m * grid.dx_m
    classes = [
        {
            "class": name,
            "area_m2": float(value),
            "percent": 100.0 * float(value) / total_area,
        }
        for name, value in sorted(
            zip(table.names, area, strict=True), key=lambda pair: -pair[1]
        )
        if value > 0.0
    ]
    unclassified = 100.0 * float(area[fill]) / total_area
    notices: list[dict[str, str]] = []
    if unclassified >= 1.0:
        notices.append(
            notice(
                "warning",
                "landcover_unclassified",
                f"{unclassified:.1f} % of the domain has no BDOT10k polygon: it gets "
                f"the values of the class {UNCLASSIFIED} (grass)",
            )
        )
    unmapped = report["unmapped"]
    if unmapped:
        first = unmapped[0]
        notices.append(
            notice(
                "warning",
                "landcover_unmapped",
                f"{sum(item['features'] for item in unmapped)} features have an "
                f"attribute value that the mapping does not name (for example "
                f"{first['layer']} {first['field']} = {first['value']!r}): they are "
                f"not painted",
            )
        )
    if missing:
        notices.append(
            notice(
                "info",
                "landcover_layers_missing",
                f"the file has no layer {', '.join(missing)}: nothing of that kind is "
                f"painted",
            )
        )
    document = {
        "path": str(path),
        "table": {"source": table.source, "overridden": list(table.overridden)},
        "layers": {"missing": missing},
        "classes": classes,
        "unclassified_percent": unclassified,
        "roads": report["roads"],
        "unmapped": unmapped,
        "painting_cell_m": sub_m,
    }
    return LandCoverResult(manning, curve_number, building, document, notices)
