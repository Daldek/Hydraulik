"""``model build``: write a SFINCS model directory from rasters the user supplies."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from hydraulik.documents import ModelDocument, PlanDocument
from hydraulik.exceptions import InvalidInputError, NotFoundError
from hydraulik.model.classes import HSG_LETTERS, load_classes
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

SoilGroup = Literal["A", "B", "C", "D"]


def _path(value: str | os.PathLike[str] | None) -> Path | None:
    return None if value is None else Path(value)


def _landcover_step(options: BuildOptions) -> str:
    """Return the line of the ``--check`` plan about the land cover.

    The inputs of the land cover are looked for and the class table is read here, so
    that a plan fails on what a run would fail on.
    """
    for path, what in (
        (options.landcover, "land-cover file"),
        (options.hsg, "soil raster"),
    ):
        if path is not None and not path.is_file():
            raise NotFoundError(
                f"{what} not found: {path}",
                details={"path": str(path)},
                reason="path_missing",
            )
    table = load_classes(options.classes)
    values = (
        "the shipped class values"
        if options.classes is None
        else f"the class values of {options.classes} ({len(table.overridden)} replaced)"
    )
    step = f"paint the land cover of {options.landcover} with {values} into Manning n"
    if options.hsg is not None and options.default_hsg is not None:
        step += (
            f" and, with the soil groups of {options.hsg} (group {options.default_hsg} "
            "where it has none), into the curve number"
        )
    elif options.hsg is not None:
        step += f" and, with the soil groups of {options.hsg}, into the curve number"
    elif options.default_hsg is not None:
        step += (
            f" and, with soil group {options.default_hsg} everywhere, into the curve "
            "number"
        )
    if options.building_raise_m > 0.0:
        step += f"; raise the cells under roofs by {options.building_raise_m:g} m"
    return step


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
    landcover: str | os.PathLike[str] | None,
    hsg: str | os.PathLike[str] | None,
    default_hsg: str | None,
    classes: str | os.PathLike[str] | None,
    building_raise_m: float | None,
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
    if landcover is None:
        for option, value in (
            ("hsg", hsg),
            ("default_hsg", default_hsg),
            ("classes", classes),
            ("building_raise_m", building_raise_m),
        ):
            if value is not None:
                raise refuse_option(
                    option,
                    f"--{option.replace('_', '-')} belongs to --landcover, which was "
                    "not given",
                    "option_not_applicable",
                    "Give the BDOT10k GeoPackage of the area with --landcover.",
                )
    else:
        if manning is not None or manning_raster is not None:
            raise refuse_option(
                "landcover",
                "the roughness comes from the land cover, not from --manning or "
                "--manning-raster",
                "exclusive_options",
                "Drop --landcover, or the Manning option; --classes changes the "
                "values of the land cover.",
            )
        if (hsg is not None or default_hsg is not None) and (
            curve_number_raster is not None or retention_mm_raster is not None
        ):
            raise refuse_option(
                "hsg" if hsg is not None else "default_hsg",
                "the curve number comes from the land cover and the soil group, not "
                "from --curve-number-raster or --retention-mm-raster",
                "exclusive_options",
                "Give the soil group, or the curve-number raster.",
            )
    if default_hsg is not None and default_hsg not in HSG_LETTERS:
        raise refuse_option(
            "default_hsg",
            f"the soil group is one of {', '.join(HSG_LETTERS)}, got {default_hsg!r}",
            "not_allowed",
        )
    if building_raise_m is not None and building_raise_m < 0:
        raise refuse_option(
            "building_raise_m", "the height must not be negative", "out_of_range"
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
        landcover=_path(landcover),
        hsg=_path(hsg),
        default_hsg=default_hsg,
        classes=_path(classes),
        building_raise_m=0.0 if building_raise_m is None else float(building_raise_m),
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
    landcover: str | os.PathLike[str] | None = None,
    hsg: str | os.PathLike[str] | None = None,
    default_hsg: SoilGroup | None = None,
    classes: str | os.PathLike[str] | None = None,
    building_raise_m: float | None = None,
    output_dir: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> ModelDocument | PlanDocument:
    """Write a SFINCS regular-grid model from rasters and a rain table you supply.

    The terrain is averaged (or interpolated) onto a grid of ``dx_m`` cells that is
    aligned to ``dx_m``; the domain is a polygon, a rectangle or the cells with
    elevation; Manning ``n`` and the SCS curve number are uniform or rasters on the same
    grid, or are made from the BDOT10k land cover (``landcover``) and the hydrologic
    soil groups (``hsg``, ``default_hsg``); the rain is the table of ``rainfall build``.
    Nothing reaches ``output_dir`` before every file is written and checked.

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
    landcover : path-like or None, optional
        BDOT10k GeoPackage (``terrain download`` writes it to ``landcover/``): Manning
        ``n`` and, with a soil group, the curve number are made from its classes
        (``docs/LAND_COVER.md``) and written as ``manning.tif`` and
        ``curve_number.tif``. Excludes ``manning`` and ``manning_raster``.
    hsg : path-like or None, optional
        Raster of hydrologic soil groups (uint8: 1 A to 4 D, 0 no data; the nearest
        cell is taken). Needs ``landcover``; excludes ``curve_number_raster`` and
        ``retention_mm_raster``.
    default_hsg : {"A", "B", "C", "D"} or None, optional
        The soil group of the cells that ``hsg`` does not cover, or of every cell when
        there is no ``hsg``. Needs ``landcover``.
    classes : path-like or None, optional
        CSV that replaces values of the shipped class table: a ``class`` column and any
        of ``manning_n`` and ``cn_a`` to ``cn_d``. Needs ``landcover``.
    building_raise_m : float or None, optional
        Height [m] by which the cells that are half or more under roofs are raised, so
        the water runs round the buildings (the roughness of a roof then applies); 0
        when not given: the buildings are ground that the water crosses. Needs
        ``landcover``.
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
        ``exclusive_options``, ``option_not_applicable``, ``not_allowed``,
        ``out_of_range``, ``invalid_bbox``, ``invalid_crs``), the domain is empty
        (``empty_domain``) or too large (``grid_too_large``), the outlet is outside the
        domain or not on its edge, or a station is outside it.
    NotFoundError
        If an input file does not exist.
    InputDataError
        If a raster, a vector file or a table cannot be read, the terrain does not
        cover the domain (``dem_gaps``) or the Manning raster does not
        (``manning_gaps``), the soil raster is not one of soil groups
        (``invalid_hsg``), or the land cover or the class table cannot be used
        (``landcover_layers_missing``, ``invalid_classes_table``).
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
        landcover=landcover,
        hsg=hsg,
        default_hsg=default_hsg,
        classes=classes,
        building_raise_m=building_raise_m,
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
        if options.landcover is not None:
            steps.insert(1, _landcover_step(options))
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
    from hydraulik.terrain.grid import write_grid_raster

    built = build_inputs(options)
    with Writer(plan) as writer:
        write_model(writer.staging, built.inputs)
        for name, (values, tags) in built.rasters.items():
            write_grid_raster(
                writer.staging / name, built.inputs.grid, values, tags=tags
            )
        records = writer.commit()
    document = ModelDocument(**built.report, files=file_dicts(records))
    document.notices.extend(built.notices)
    return document
