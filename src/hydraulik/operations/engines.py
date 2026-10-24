"""``engines check``: what Hydraulik found on this machine (ADR-0003)."""

from __future__ import annotations

from typing import Final

from hydraulik.documents import EnginesDocument
from hydraulik.engines.detect import (
    EngineStatus,
    detect_kartograf,
    detect_sfincs,
    detect_sfincs_library,
    detect_swmm,
)
from hydraulik.exceptions import InvalidInputError, MissingDependencyError
from hydraulik.operations._support import EXTRAS, extra_found, extra_version
from hydraulik.settings import load_settings

__all__ = ["FEATURES", "check_engines"]

# command -> (engines it needs, Python packages it needs)
FEATURES: Final[dict[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "terrain download": (("kartograf",), ()),
    "rainfall build": ((), ("hydrolog",)),
    "model build": ((), ("numpy", "rasterio", "geopandas", "shapely", "pyproj")),
    "model run": (("sfincs",), ("numpy", "netCDF4")),
    "results read": ((), ("numpy", "netCDF4")),
    "results export": ((), ("numpy", "netCDF4", "rasterio")),
    "swmm run": (("swmm",), ("numpy", "pyswmm")),
    "model couple": (
        ("sfincs-library", "swmm"),
        ("numpy", "netCDF4", "pyswmm"),
    ),
}
"""What each command that needs more than the core package needs (ADR-0003)."""


def _engine_entry(status: EngineStatus) -> dict[str, object]:
    return {
        "name": status.name,
        "found": status.found,
        "via": status.via,
        "location": status.location,
        "version": status.version,
        "detail": status.detail,
        "hint": status.hint,
    }


def check_engines(*, require: list[str] | None = None) -> EnginesDocument:
    """Report the engines and the Python packages that Hydraulik can use.

    Nothing is installed, started for a run, pulled or written; SFINCS is only started
    in an empty directory to read its banner, and a Docker image is only inspected.

    Parameters
    ----------
    require : list of str or None, optional
        Commands (``model run``, ``model couple``, ...) that must be able to run; if
        one cannot, the call fails with ``missing_dependency`` that lists what is
        missing.

    Returns
    -------
    EnginesDocument
        The engines, the packages and, for each command that needs more than the core
        package, whether it can run here.

    Raises
    ------
    InvalidInputError
        If ``require`` names a command that needs nothing or does not exist.
    MissingDependencyError
        If a required command cannot run (reason ``engine_missing``).

    Examples
    --------
    >>> document = check_engines()
    >>> [engine["name"] for engine in document.engines]
    ['sfincs', 'sfincs-library', 'swmm', 'kartograf']
    """
    unknown = [name for name in require or [] if name not in FEATURES]
    if unknown:
        raise InvalidInputError(
            f"no check for the command {unknown[0]!r}",
            details={
                "option": "require",
                "value": unknown[0],
                "allowed": list(FEATURES),
            },
            reason="not_allowed",
        )
    settings = load_settings()
    sfincs, _ = detect_sfincs(settings)
    statuses = {
        status.name: status
        for status in (
            sfincs,
            detect_sfincs_library(settings),
            detect_swmm(),
            detect_kartograf(settings),
        )
    }
    extras = [
        {
            "name": module,
            "extra": extra,
            "found": extra_found(module),
            "version": extra_version(module),
        }
        for module, (_, extra) in EXTRAS.items()
    ]
    present = {entry["name"]: bool(entry["found"]) for entry in extras}
    missing_by_command: dict[str, list[str]] = {}
    for command, (engines, packages) in FEATURES.items():
        missing = [name for name in engines if not statuses[name].found]
        missing += [name for name in packages if not present.get(name, False)]
        missing_by_command[command] = missing
    document = EnginesDocument(
        engines=[_engine_entry(status) for status in statuses.values()],
        extras=extras,
        features=[
            {
                "command": command,
                "available": not missing_by_command[command],
                "needs": [*engines, *packages],
                "missing": missing_by_command[command],
            }
            for command, (engines, packages) in FEATURES.items()
        ],
    )
    blocked = {
        command: missing_by_command[command]
        for command in require or []
        if missing_by_command[command]
    }
    if blocked:
        names = {name for missing in blocked.values() for name in missing}
        hints = [statuses[name].hint or "" for name in sorted(names & set(statuses))]
        extras_missing = sorted({EXTRAS[name][1] for name in names & set(EXTRAS)})
        if extras_missing:
            hints.append(
                "Install the packages: uv add "
                + " ".join(f"'hydraulik[{extra}]'" for extra in extras_missing)
            )
        raise MissingDependencyError(
            "cannot run here: "
            + "; ".join(
                f"{command} (missing {', '.join(missing)})"
                for command, missing in blocked.items()
            ),
            details={"commands": list(blocked)},
            hint=" ".join(hint for hint in hints if hint) or None,
            reason="engine_missing",
        )
    return document
