"""``results read`` and ``results export``: what a SFINCS run computed."""

from __future__ import annotations

import os
from pathlib import Path

from hydraulik.documents import ExportDocument, PlanDocument, ResultsDocument
from hydraulik.exceptions import InvalidInputError, NotFoundError
from hydraulik.operations._results import locate_results, summarise
from hydraulik.operations._support import (
    extra_blocker,
    file_dicts,
    missing_extras,
    require_extras,
)
from hydraulik.output import Writer, plan_file

__all__ = ["export_results", "read_results"]

_MAPS = ("max_depth", "max_velocity", "final_depth", "infiltration")
_VARIABLES = (*_MAPS, "stations")


def read_results(
    *,
    run: str | os.PathLike[str],
    thresholds_m: list[float] | None = None,
    expected_rain_mm: float | None = None,
) -> ResultsDocument:
    """Read the results of a SFINCS run: maxima, flooded areas, water balance.

    Parameters
    ----------
    run : path-like
        The directory of a run (``hydraulik model run``) or its ``sfincs_map.nc``; the
        station file next to it is read too.
    thresholds_m : list of float or None, optional
        Depths [m] for which the flooded area is reported; 0.1 and 0.3 by default. A
        threshold under the wet/dry threshold of the run is refused: the map does not
        hold depths under it.
    expected_rain_mm : float or None, optional
        The depth of the precipitation file [mm], to check the rain SFINCS applied.

    Returns
    -------
    ResultsDocument
        ``hydraulik-results/1``; the notices carry the flags of the balance.

    Raises
    ------
    NotFoundError
        If the directory has no ``sfincs_map.nc``.
    InputDataError
        If the file is not a SFINCS map, or UnsupportedError for a map that is not a
        regular grid.
    InvalidInputError
        If a threshold is not positive or is under ``huthresh``.
    MissingDependencyError
        If netCDF4 is not installed (extra ``sfincs``).

    Examples
    --------
    >>> read_results(run="no-such-run")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.NotFoundError: SFINCS map not found: no-such-run
    """
    require_extras("numpy", "netCDF4")
    map_path, stations_path = locate_results(run)
    return summarise(
        map_path,
        stations_path,
        thresholds_m=thresholds_m,
        expected_rain_mm=expected_rain_mm,
    )


def export_results(
    *,
    run: str | os.PathLike[str],
    variable: str,
    output: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> ExportDocument | PlanDocument:
    """Write one map (GeoTIFF) or the station series (CSV) of a run to ``output``.

    Parameters
    ----------
    run : path-like
        The directory of a run or its ``sfincs_map.nc``.
    variable : {"max_depth", "max_velocity", "final_depth", "infiltration", "stations"}
        What to export. The maps are GeoTIFF in the CRS of the model, no data outside
        the domain (and, for ``max_depth``, where the water stayed under ``huthresh``);
        ``stations`` is a CSV table with the level and depth at every output time.
    output : path-like
        The file to write; its directory is created when missing.
    force : bool, optional
        Replace the file when it exists.
    check : bool, optional
        Plan without effects.

    Returns
    -------
    ExportDocument or PlanDocument
        ``hydraulik-export/1``, or the ``hydraulik-plan/1`` of ``check``.

    Raises
    ------
    InvalidInputError
        If ``variable`` is unknown.
    NotFoundError
        If the run has no map, or no station file for ``stations``.
    ConflictError
        If ``output`` exists without ``force`` or lies inside a store.
    MissingDependencyError
        If netCDF4 (or rasterio for a GeoTIFF) is not installed.

    Examples
    --------
    >>> export_results(run="r", variable="elevation", output="o.tif")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.InvalidInputError: unknown variable 'elevation'
    """
    if variable not in _VARIABLES:
        raise InvalidInputError(
            f"unknown variable {variable!r}",
            details={
                "option": "variable",
                "value": variable,
                "allowed": list(_VARIABLES),
            },
            reason="not_allowed",
        )
    packages = ("numpy", "netCDF4") + (() if variable == "stations" else ("rasterio",))
    map_path, stations_path = locate_results(run)
    if variable == "stations" and stations_path is None:
        raise NotFoundError(
            f"the run has no station file next to {map_path.name}",
            details={"path": str(map_path.parent)},
            hint="Give `hydraulik model build` observation points (--stations).",
            reason="results_missing",
        )
    plan = plan_file(output, force=force)
    name = Path(output).name
    if check:
        return PlanDocument.from_write_plan(
            plan,
            steps=[f"read {map_path.name} and write {variable} to {name}"],
            blockers=[extra_blocker(item) for item in missing_extras(packages)],
        )
    require_extras(*packages)
    from hydraulik.engines.sfincs.results import (  # numpy: only when exporting
        export_geotiff,
        read_map,
        read_stations,
        write_stations_csv,
    )

    with Writer(plan) as writer:
        staged = writer.staged_path(name)
        if variable == "stations":
            assert stations_path is not None
            write_stations_csv(read_stations(stations_path), staged)
        else:
            export_geotiff(read_map(map_path), variable, staged)
        records = writer.commit()
    return ExportDocument(
        variable=variable,
        format="csv" if variable == "stations" else "geotiff",
        source=str(map_path),
        files=file_dicts(records),
    )
