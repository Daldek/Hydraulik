"""``model build``: write a SFINCS model directory from rasters the user supplies."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from hydraulik.documents import ModelDocument, PlanDocument
from hydraulik.exceptions import InvalidInputError
from hydraulik.model.options import DEFAULT_RECESSION_MIN, BuildOptions
from hydraulik.operations._support import (
    extra_blocker,
    file_dicts,
    missing_extras,
    refuse_option,
    require_extras,
)
from hydraulik.output import Writer, plan_directory

__all__ = ["build_model"]

_PACKAGES = ("numpy", "rasterio", "geopandas", "shapely", "pyproj")
"""What the build imports: the ``model`` extra."""


def _path(value: str | os.PathLike[str] | None) -> Path | None:
    return None if value is None else Path(value)


def _prepare(
    *,
    dem: Sequence[str | os.PathLike[str]],
    dx_m: float,
    rain: str | os.PathLike[str],
    bbox: Sequence[float] | None,
    crs: str | None,
    geometry: str | os.PathLike[str] | None,
    layer: str | None,
    manning: float | None,
    manning_raster: str | os.PathLike[str] | None,
    curve_number_raster: str | os.PathLike[str] | None,
    retention_mm_raster: str | os.PathLike[str] | None,
    recession_min: float | None,
    outlet: str | os.PathLike[str] | None,
    outlet_layer: str | None,
    observation_points: str | os.PathLike[str] | None,
) -> BuildOptions:
    """Check the combination of options and return them as ``BuildOptions``."""
    if not dem:
        raise refuse_option(
            "dem",
            "at least one elevation raster is required",
            "missing_option",
            "Give the terrain as a GeoTIFF, for Poland EPSG:2180.",
        )
    if dx_m <= 0:
        raise refuse_option("dx_m", "the cell size must be positive", "out_of_range")
    if bbox is not None and geometry is not None:
        raise refuse_option(
            "geometry",
            "a domain is --bbox or --geometry, not both",
            "exclusive_options",
            "Give the rectangle or the polygon of the domain.",
        )
    if bbox is not None and len(bbox) != 4:
        raise refuse_option(
            "bbox",
            f"four numbers are required (min_x,min_y,max_x,max_y), got {len(bbox)}",
            "invalid_bbox",
        )
    if bbox is not None and crs is None:
        raise refuse_option(
            "crs",
            "--bbox needs the CRS its numbers are in",
            "missing_option",
            "Give --crs, for example EPSG:2180 or EPSG:4326 (x is east or longitude).",
        )
    if crs is not None and bbox is None:
        raise refuse_option(
            "crs",
            "--crs describes --bbox, which was not given",
            "option_not_applicable",
        )
    if layer is not None and geometry is None:
        raise refuse_option(
            "layer",
            "--layer names a layer of --geometry, which was not given",
            "option_not_applicable",
        )
    if outlet_layer is not None and outlet is None:
        raise refuse_option(
            "outlet_layer",
            "--outlet-layer names a layer of --outlet, which was not given",
            "option_not_applicable",
        )
    if manning is not None and manning_raster is not None:
        raise refuse_option(
            "manning_raster",
            "the roughness is --manning or --manning-raster, not both",
            "exclusive_options",
        )
    if curve_number_raster is not None and retention_mm_raster is not None:
        raise refuse_option(
            "retention_mm_raster",
            "the infiltration is --curve-number-raster or --retention-mm-raster, "
            "not both",
            "exclusive_options",
            "SCS retention S in mm and the curve number say the same thing.",
        )
    if recession_min is not None and recession_min < 0:
        raise InvalidInputError(
            "--recession-min must not be negative",
            details={"option": "recession_min", "value": recession_min},
            reason="out_of_range",
        )
    return BuildOptions(
        dem=tuple(Path(item) for item in dem),
        dx_m=float(dx_m),
        rain=Path(rain),
        bbox=None if bbox is None else (bbox[0], bbox[1], bbox[2], bbox[3]),
        crs=crs,
        geometry=_path(geometry),
        layer=layer,
        manning=manning,
        manning_raster=_path(manning_raster),
        curve_number_raster=_path(curve_number_raster),
        retention_mm_raster=_path(retention_mm_raster),
        recession_min=(
            DEFAULT_RECESSION_MIN if recession_min is None else float(recession_min)
        ),
        outlet=_path(outlet),
        outlet_layer=outlet_layer,
        observation_points=_path(observation_points),
    )


def build_model(
    *,
    dem: Sequence[str | os.PathLike[str]],
    dx_m: float,
    rain: str | os.PathLike[str],
    bbox: Sequence[float] | None = None,
    crs: str | None = None,
    geometry: str | os.PathLike[str] | None = None,
    layer: str | None = None,
    manning: float | None = None,
    manning_raster: str | os.PathLike[str] | None = None,
    curve_number_raster: str | os.PathLike[str] | None = None,
    retention_mm_raster: str | os.PathLike[str] | None = None,
    recession_min: float | None = None,
    outlet: str | os.PathLike[str] | None = None,
    outlet_layer: str | None = None,
    observation_points: str | os.PathLike[str] | None = None,
    output_dir: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> ModelDocument | PlanDocument:
    """Write a SFINCS regular-grid model from rasters and a rain table you supply.

    The terrain is averaged (or interpolated) onto a grid of ``dx_m`` cells that is
    aligned to ``dx_m``; the domain is a polygon, a rectangle or the cells with
    elevation; Manning ``n`` and the SCS curve number are uniform or rasters on the same
    grid; the rain is the table of ``rainfall build``. Nothing reaches ``output_dir``
    before every file is written and checked.

    Parameters
    ----------
    dem : sequence of path-like
        Elevation rasters (GeoTIFF) in a metric CRS with an EPSG code; the first sets
        the CRS of the model and wins where they overlap.
    dx_m : float
        Cell size [m].
    rain : path-like
        Rain table (``time_min``, ``depth_mm``) from ``rainfall build``.
    bbox : sequence of float or None, optional
        ``min_x, min_y, max_x, max_y`` of the domain in ``crs``. At most one of
        ``bbox`` and ``geometry``; with neither the domain is every cell with elevation.
    crs : str or None, optional
        CRS of ``bbox``, for example ``"EPSG:2180"``. Required with ``bbox``.
    geometry : path-like or None, optional
        Polygon file (GeoPackage, GeoJSON, Shapefile) of the domain.
    layer : str or None, optional
        Layer of ``geometry``; the first layer when not given.
    manning : float or None, optional
        Uniform Manning ``n`` [s/m^(1/3)]; 0.04 when no Manning option is given.
    manning_raster : path-like or None, optional
        Manning ``n`` per cell; at most one of ``manning`` and ``manning_raster``.
    curve_number_raster, retention_mm_raster : path-like or None, optional
        SCS curve number per cell, or SCS retention ``S`` [mm] per cell
        (``CN = 25400 / (S + 254)``); at most one of them; none switches infiltration
        off.
    recession_min : float or None, optional
        Minutes the simulation lasts after the rain; 60 when not given.
    outlet, outlet_layer : path-like or None, optional
        Geometries (lines, points or polygons) where the water leaves the domain, and
        their layer; only the cells on the edge of the domain become outflow cells.
        Without an outlet the boundary is closed.
    observation_points : path-like or None, optional
        Station table (``name``, ``x_m``, ``y_m`` in the CRS of the model).
    output_dir : path-like
        Directory for the model files; created when missing.
    force : bool, optional
        Replace files that exist.
    check : bool, optional
        Plan without effects: the files, the grid and what is missing.

    Returns
    -------
    ModelDocument or PlanDocument
        ``hydraulik-model/1`` with the grid, the inputs that were used and the files,
        or the ``hydraulik-plan/1`` of ``check``. The notices name the defaults that
        were applied and the gaps that were found.

    Raises
    ------
    InvalidInputError
        If the options do not go together (reasons ``missing_option``,
        ``exclusive_options``, ``option_not_applicable``, ``invalid_bbox``,
        ``invalid_crs``), the domain is empty (``empty_domain``) or too large
        (``grid_too_large``), the outlet is outside the domain or not on its edge, or
        a station is outside it.
    NotFoundError
        If an input file does not exist.
    InputDataError
        If a raster, a vector file or a table cannot be read, the terrain does not
        cover the domain (``dem_gaps``) or the Manning raster does not
        (``manning_gaps``).
    UnsupportedError
        If the CRS of the first elevation raster is not a metric EPSG CRS.
    MissingDependencyError
        If the ``model`` extra is not installed.
    ConflictError
        If an output exists without ``force``, or the directory is inside a store.

    Examples
    --------
    >>> build_model(dem=[], dx_m=5.0, rain="rain.csv", output_dir="model")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.InvalidInputError: --dem: at least one elevation raster is \
required
    """
    options = _prepare(
        dem=dem,
        dx_m=dx_m,
        rain=rain,
        bbox=bbox,
        crs=crs,
        geometry=geometry,
        layer=layer,
        manning=manning,
        manning_raster=manning_raster,
        curve_number_raster=curve_number_raster,
        retention_mm_raster=retention_mm_raster,
        recession_min=recession_min,
        outlet=outlet,
        outlet_layer=outlet_layer,
        observation_points=observation_points,
    )
    plan = plan_directory(output_dir, options.planned_names(), force=force)
    missing = missing_extras(_PACKAGES)
    if check:
        steps = [
            f"put {len(options.dem)} elevation raster(s) on a grid of "
            f"{options.dx_m:g} m cells",
            "fill the domain, Manning n, the curve number, the outlet and the stations",
            f"read {options.rain} and write its rain, then the files of the model",
            f"move {', '.join(options.planned_names())} into {plan.directory}",
        ]
        if not missing:
            from hydraulik.model.build import plan_grid

            grid, _, domain = plan_grid(options)
            steps.insert(
                0,
                f"the domain is {domain['source']}: a grid of {grid.columns} x "
                f"{grid.rows} cells of {grid.dx_m:g} m in EPSG:{grid.epsg}",
            )
        return PlanDocument.from_write_plan(
            plan, steps=steps, blockers=[extra_blocker(name) for name in missing]
        )
    require_extras(*_PACKAGES)
    from hydraulik.engines.sfincs.model import write_model
    from hydraulik.model.build import build_inputs

    built = build_inputs(options)
    with Writer(plan) as writer:
        write_model(writer.staging, built.inputs)
        records = writer.commit()
    document = ModelDocument(**built.report, files=file_dicts(records))
    document.notices.extend(built.notices)
    return document
