"""The ``hydraulik-results/1`` document of a SFINCS run (shared by two commands)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from hydraulik.documents import ResultsDocument, notice
from hydraulik.engines.sfincs.inp import MAP_NAME, STATIONS_NAME
from hydraulik.exceptions import NotFoundError

__all__ = [
    "DEFAULT_THRESHOLDS_M",
    "describe_depth",
    "describe_grid",
    "describe_stations",
    "locate_results",
    "summarise",
]

DEFAULT_THRESHOLDS_M: Final = (0.1, 0.3)
"""Depths [m] for which the flooded area is reported when the caller gives none."""

_MESSAGES: Final = {
    "balance_residual": (
        "the water balance of the closed model does not close: the residual is "
        "{percent:.2f} % of the rain"
    ),
    "balance_gain": (
        "the model gained water: the residual is {percent:.2f} % of the rain although "
        "water can only leave"
    ),
    "rain_mismatch": "the rain SFINCS applied differs from the precipitation file",
    "time_mismatch": "the last depth map is not at the end of the run",
    "no_rain_output": (
        "the map has no accumulated rain (storecumprcp was off): no balance"
    ),
}


def locate_results(run: str | os.PathLike[str]) -> tuple[Path, Path | None]:
    """Return the map and the station file of a run.

    Parameters
    ----------
    run : str or Path
        The directory of a run, or its ``sfincs_map.nc``.

    Returns
    -------
    tuple of (Path, Path or None)
        The map, and ``sfincs_his.nc`` next to it when there is one.

    Raises
    ------
    NotFoundError
        If there is no map.
    """
    source = Path(run)
    folder = source if source.is_dir() else source.parent
    map_path = source / MAP_NAME if source.is_dir() else source
    if not map_path.is_file():
        raise NotFoundError(
            f"SFINCS map not found: {map_path}",
            details={"path": str(map_path)},
            hint="Name the directory that `hydraulik model run` wrote.",
            reason="results_missing",
        )
    his = folder / STATIONS_NAME
    return map_path, his if his.is_file() else None


def describe_grid(run: Any, stats: Any) -> dict[str, Any]:
    """Return the ``grid`` entry of a results document for a read map."""
    return {
        "epsg": run.grid.epsg,
        "dx_m": run.grid.dx_m,
        "x0_m": run.grid.x0_m,
        "y0_m": run.grid.y0_m,
        "rows": run.grid.rows,
        "columns": run.grid.columns,
        "active_cells": int(run.active.sum()),
        "area_m2": stats.active_area_m2,
        "huthresh_m": run.huthresh_m,
    }


def describe_depth(stats: Any) -> dict[str, Any]:
    """Return the ``depth`` entry of a results document for its statistics."""
    return {
        "max_depth_m": stats.max_depth_m,
        "max_depth_x_m": stats.max_depth_x_m,
        "max_depth_y_m": stats.max_depth_y_m,
        "max_velocity_ms": stats.max_velocity_ms,
        "flooded_area_m2": [
            {"threshold_m": limit, "area_m2": area}
            for limit, area in stats.flooded_area_m2.items()
        ],
    }


def describe_stations(stations: Sequence[Any]) -> list[dict[str, Any]]:
    """Return the ``stations`` entry of a results document."""
    return [
        {
            "name": station.name,
            "x_m": station.x_m,
            "y_m": station.y_m,
            "max_depth_m": station.max_depth_m,
            "time_of_max_s": station.time_of_max_s,
        }
        for station in stations
    ]


def summarise(
    map_path: Path,
    stations_path: Path | None,
    *,
    thresholds_m: Sequence[float] | None = None,
    expected_rain_mm: float | None = None,
    source: Path | None = None,
) -> ResultsDocument:
    """Read a run and build its ``hydraulik-results/1`` document.

    Parameters
    ----------
    map_path, stations_path : Path
        The result files (the station file may be absent).
    thresholds_m : sequence of float or None, optional
        Depths for the flooded areas; :data:`DEFAULT_THRESHOLDS_M` when ``None``.
    expected_rain_mm : float or None, optional
        The depth of the precipitation file, to check the rain SFINCS applied.
    source : Path or None, optional
        The path to name in the document when the files were read from a staging
        directory that is about to be moved.

    Returns
    -------
    ResultsDocument
        The grid, the depth statistics, the balance and the stations; the notices
        carry the flags of the balance.
    """
    from hydraulik.engines.sfincs.results import (  # numpy: only when results are read
        depth_statistics,
        read_map,
        read_stations,
        surface_balance,
    )

    run = read_map(map_path)
    limits = tuple(thresholds_m) if thresholds_m else DEFAULT_THRESHOLDS_M
    stats = depth_statistics(run, limits)
    balance = surface_balance(run, expected_rain_mm=expected_rain_mm)
    stations = read_stations(stations_path) if stations_path is not None else ()
    document = ResultsDocument(
        source=str(source or map_path),
        engine={
            "build_revision": run.build_revision,
            "status": run.status,
            "runtime_s": run.runtime_s,
            "average_dt_s": run.average_dt_s,
        },
        grid=describe_grid(run, stats),
        depth=describe_depth(stats),
        balance={
            "rain_m3": balance.rain_m3,
            "infiltration_m3": balance.infiltration_m3,
            "stored_m3": balance.stored_m3,
            "residual_m3": balance.residual_m3,
            "residual_percent": balance.residual_percent,
            "open_boundary": balance.open_boundary,
            "expected_rain_m3": balance.expected_rain_m3,
            "flags": list(balance.flags),
        },
        stations=describe_stations(stations),
    )
    for flag in balance.flags:
        document.notices.append(
            notice(
                "warning",
                flag,
                _MESSAGES[flag].format(percent=balance.residual_percent),
            )
        )
    if balance.open_boundary and not balance.flags:
        document.notices.append(
            notice(
                "info",
                "open_boundary",
                "the model has outflow cells: the residual is the water that left "
                "over them",
            )
        )
    if stats.max_depth_m == 0.0:
        document.notices.append(
            notice(
                "info",
                "no_flooding",
                "no cell reached the wet/dry threshold: there is nothing to map",
            )
        )
    return document
