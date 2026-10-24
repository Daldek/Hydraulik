"""Helpers shared by the operations: blockers, extras, file records (DEV-19.10)."""

from __future__ import annotations

import importlib.metadata
import importlib.util
from collections.abc import Iterable
from typing import Final

from hydraulik.exceptions import MissingDependencyError
from hydraulik.output import FileRecord

__all__ = [
    "EXTRAS",
    "blocker",
    "extra_blocker",
    "extra_found",
    "extra_version",
    "file_dicts",
    "missing_extras",
    "require_extras",
]

EXTRAS: Final[dict[str, tuple[str, str]]] = {
    "numpy": ("numpy", "model"),
    "netCDF4": ("netcdf4", "sfincs"),
    "rasterio": ("rasterio", "model"),
    "geopandas": ("geopandas", "model"),
    "shapely": ("shapely", "model"),
    "pyproj": ("pyproj", "model"),
    "pyswmm": ("pyswmm", "swmm"),
    "hydrolog": ("hydrolog", "rainfall"),
    "imgwtools": ("imgwtools", "rainfall"),
}
"""Import name to (distribution, extra of Hydraulik that installs it)."""


def blocker(reason: str, message: str, hint: str | None = None) -> dict[str, str]:
    """Return a blocker of a plan: why the real run would fail.

    Parameters
    ----------
    reason : str
        ``engine_missing`` or ``extra_missing``.
    message : str
        One English sentence.
    hint : str or None, optional
        What to do about it.

    Returns
    -------
    dict
        ``{"reason", "message"}`` and ``"hint"`` when there is one.

    Examples
    --------
    >>> blocker("engine_missing", "no SFINCS")
    {'reason': 'engine_missing', 'message': 'no SFINCS'}
    """
    entry = {"reason": reason, "message": message}
    if hint:
        entry["hint"] = hint
    return entry


def extra_found(module: str) -> bool:
    """Tell whether a Python package can be imported, without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def extra_version(module: str) -> str | None:
    """Return the installed version of a package of :data:`EXTRAS`, or ``None``."""
    distribution = EXTRAS[module][0] if module in EXTRAS else module
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def missing_extras(modules: Iterable[str]) -> list[str]:
    """Return those of ``modules`` that cannot be imported, in the order given."""
    return [name for name in modules if not extra_found(name)]


def extra_blocker(module: str) -> dict[str, str]:
    """Return the blocker for a package that an extra of Hydraulik would install."""
    extra = EXTRAS[module][1]
    return blocker(
        "extra_missing",
        f"{module} is not installed (extra [{extra}] of Hydraulik)",
        f"Install it: uv add 'hydraulik[{extra}]'",
    )


def require_extras(*modules: str) -> None:
    """Raise ``missing_dependency`` naming every missing package of ``modules``.

    Raises
    ------
    MissingDependencyError
        If any package cannot be imported; ``details.extras`` lists the extras and the
        hint gives one ``uv add`` command.
    """
    missing = missing_extras(modules)
    if not missing:
        return
    extras = sorted({EXTRAS[name][1] for name in missing})
    raise MissingDependencyError(
        f"not installed: {', '.join(missing)}",
        details={"modules": missing, "extras": extras},
        hint="Install them: uv add "
        + " ".join(f"'hydraulik[{extra}]'" for extra in extras),
        reason="extra_missing",
    )


def file_dicts(records: Iterable[FileRecord]) -> list[dict[str, object]]:
    """Return the ``files[]`` entries of the written files (DEV-19.19)."""
    return [record.to_dict() for record in records]
