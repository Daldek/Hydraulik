"""Helpers shared by the operations: blockers, extras, file records (DEV-19.10)."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

from hydraulik.exceptions import InvalidInputError, MissingDependencyError
from hydraulik.output import STAGING_DIR, FileRecord

__all__ = [
    "EXTRAS",
    "blocker",
    "extra_blocker",
    "extra_found",
    "extra_version",
    "file_dicts",
    "missing_extras",
    "refuse_option",
    "require_extras",
    "stage_model",
    "unknown_inflow_node",
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


def refuse_option(
    option: str, why: str, reason: str, hint: str | None = None
) -> InvalidInputError:
    """Return the ``validation_error`` of a combination of options that cannot work.

    Parameters
    ----------
    option : str
        Name of the option the error is about, in snake_case.
    why : str
        One English clause after the flag.
    reason : str
        ``details.reason``: ``missing_option``, ``exclusive_options``,
        ``option_not_applicable`` or a finer one.
    hint : str or None, optional
        What to do about it.

    Returns
    -------
    InvalidInputError
        To be raised by the caller.

    Examples
    --------
    >>> str(refuse_option("crs", "goes with --bbox", "option_not_applicable"))
    '--crs: goes with --bbox'
    """
    return InvalidInputError(
        f"--{option.replace('_', '-')}: {why}",
        details={"option": option},
        hint=hint,
        reason=reason,
    )


def unknown_inflow_node(
    node: str, allowed: Sequence[str], *, junctions_only: bool
) -> InvalidInputError:
    """Return the ``validation_error`` of an inflow at a node the source does not have.

    Parameters
    ----------
    node : str
        The name that ``--inflow-node`` gave.
    allowed : sequence of str
        The names the source has (the first 50 go into ``details.allowed``).
    junctions_only : bool
        True for a network table, whose outfall takes no inflow; False for the user's
        SWMM input, where any node does.

    Returns
    -------
    InvalidInputError
        Reason ``unknown_node``, to be raised by the caller.

    Examples
    --------
    >>> str(unknown_inflow_node("X", ["J1"], junctions_only=False))
    "the SWMM input has no node 'X'"
    """
    return InvalidInputError(
        f"the network table has no junction {node!r}"
        if junctions_only
        else f"the SWMM input has no node {node!r}",
        details={
            "option": "inflow_node",
            "value": node,
            "allowed": list(allowed)[:50],
        },
        hint=(
            "Name a junction of the table; the outfall takes no inflow."
            if junctions_only
            else "Name a node of the SWMM input."
        ),
        reason="unknown_node",
    )


def stage_model(model: Path, staging: Path, outputs: Iterable[str]) -> None:
    """Copy the files of a model directory into the directory an engine will run in.

    The run happens in staging so that nothing reaches the output directory before it
    has succeeded. Files of a previous run (``outputs``) and hidden entries, among them
    the staging directory of the writer, are left out.

    Parameters
    ----------
    model : Path
        The model directory (it may be the output directory itself).
    staging : Path
        An existing directory.
    outputs : iterable of str
        Names of the files the run will write.
    """
    skip = set(outputs)
    for entry in model.iterdir():
        if (
            entry.name.startswith(".")
            or entry.name in skip
            or entry.name == STAGING_DIR
        ):
            continue
        target = staging / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)
