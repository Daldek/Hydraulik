"""Reading ``sfincs.inp`` of a model directory (ADR-0004).

The file is ``key = value`` text. Only what Hydraulik needs is interpreted: which
files the run will produce and the grid and the times that a result is checked
against. The writer is :func:`hydraulik.engines.sfincs.model.render_inp`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Final

from hydraulik.exceptions import InputDataError, NotFoundError

__all__ = [
    "INP_NAME",
    "LOG_NAME",
    "MAP_NAME",
    "STATIONS_NAME",
    "planned_outputs",
    "read_inp",
    "tstop_s",
]

INP_NAME: Final = "sfincs.inp"
MAP_NAME: Final = "sfincs_map.nc"
STATIONS_NAME: Final = "sfincs_his.nc"
LOG_NAME: Final = "sfincs.log"

_TIME_FORMAT: Final = "%Y%m%d %H%M%S"


def read_inp(path: str | Path) -> dict[str, str]:
    r"""Return the ``key = value`` pairs of a ``sfincs.inp``.

    Parameters
    ----------
    path : str or Path
        The file, or the model directory that holds ``sfincs.inp``.

    Returns
    -------
    dict
        Lower-case key to the value text, both stripped. Lines without ``=`` are
        skipped.

    Raises
    ------
    NotFoundError
        If there is no ``sfincs.inp``.

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     _ = (pathlib.Path(tmp) / "sfincs.inp").write_text("MMAX = 10\ndx=5.0\n")
    ...     read_inp(tmp)
    {'mmax': '10', 'dx': '5.0'}
    """
    source = Path(path)
    if source.is_dir():
        source = source / INP_NAME
    if not source.is_file():
        raise NotFoundError(
            f"{INP_NAME} not found: {source}",
            details={"path": str(source)},
            hint="Name a model directory written by `hydraulik model build`.",
            reason="model_missing",
        )
    values: dict[str, str] = {}
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip():
            values[key.strip().lower()] = value.strip()
    return values


def tstop_s(inp: dict[str, str]) -> float:
    """Return the length of the run [s] from ``tstart`` and ``tstop``.

    Parameters
    ----------
    inp : dict
        The result of :func:`read_inp`.

    Returns
    -------
    float
        ``tstop - tstart`` in seconds.

    Raises
    ------
    InputDataError
        If a time is missing or is not ``YYYYMMDD HHMMSS``.

    Examples
    --------
    >>> tstop_s({"tstart": "20000101 000000", "tstop": "20000101 020000"})
    7200.0
    """
    try:
        start = datetime.strptime(inp["tstart"], _TIME_FORMAT)
        stop = datetime.strptime(inp["tstop"], _TIME_FORMAT)
    except (KeyError, ValueError) as exc:
        raise InputDataError(
            "sfincs.inp has no valid tstart and tstop",
            details={"keys": ["tstart", "tstop"]},
            hint="Times are written as YYYYMMDD HHMMSS.",
            reason="invalid_inp",
        ) from exc
    return (stop - start).total_seconds()


def planned_outputs(inp: dict[str, str]) -> tuple[str, ...]:
    """Return the files a run of this model writes, known before it starts.

    Parameters
    ----------
    inp : dict
        The result of :func:`read_inp`.

    Returns
    -------
    tuple of str
        ``sfincs_map.nc`` and ``sfincs.log`` always, ``sfincs_his.nc`` when the model
        has observation points or cross-sections.

    Examples
    --------
    >>> planned_outputs({"obsfile": "sfincs.obs"})
    ('sfincs_map.nc', 'sfincs_his.nc', 'sfincs.log')
    """
    names = [MAP_NAME]
    if "obsfile" in inp or "crsfile" in inp:
        names.append(STATIONS_NAME)
    names.append(LOG_NAME)
    return tuple(names)
