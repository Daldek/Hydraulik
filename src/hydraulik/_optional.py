"""Lazy import of the optional dependencies (DEV-6.5, AGI-7.3).

A feature that needs an extra imports it through :func:`require`, so importing
Hydraulik stays light and a missing extra is ``missing_dependency`` with the install
command in the hint.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from hydraulik.exceptions import MissingDependencyError

__all__ = ["require"]


def require(module: str, extra: str) -> ModuleType:
    """Import ``module`` or raise ``missing_dependency`` naming the extra.

    Parameters
    ----------
    module : str
        Import name, for example ``"rasterio"``.
    extra : str
        Extra of Hydraulik that installs it, for example ``"model"``.

    Returns
    -------
    module
        The imported module.

    Raises
    ------
    MissingDependencyError
        If the module cannot be imported; ``details.extra`` names the extra and the
        hint gives the ``uv add`` command.

    Examples
    --------
    >>> require("json", "model").__name__
    'json'
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingDependencyError(
            f"{module} is not installed (extra [{extra}] of Hydraulik)",
            details={"module": module, "extra": extra},
            hint=f"Install it: uv add 'hydraulik[{extra}]'",
            reason="extra_missing",
        ) from exc
