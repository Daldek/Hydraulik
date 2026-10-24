"""Reading the text report of a SWMM run (README 3.10)."""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["routing_continuity_error_percent"]

_CONTINUITY = re.compile(r"Continuity Error \(%\) \.+\s+(-?[\d.]+)")


def routing_continuity_error_percent(report: str | Path) -> float | None:
    """Return the flow routing continuity error of a SWMM report [percent].

    The report has one continuity error per quantity that was computed (runoff, then
    flow routing); the last one is the flow routing. It is the error of SWMM itself:
    the coupler's interface adds none, so this is the network-side error of the
    balance (README 3.1).

    Parameters
    ----------
    report : str or Path
        The text of the report, or the :class:`~pathlib.Path` of the ``.rpt`` file.

    Returns
    -------
    float or None
        The error [percent], or ``None`` if the report has no continuity table (the
        run did not finish).

    Examples
    --------
    >>> routing_continuity_error_percent("Continuity Error (%) .....        -0.242")
    -0.242
    """
    if isinstance(report, Path):
        text = report.read_text(encoding="utf-8", errors="replace")
    else:
        text = report
    matches = _CONTINUITY.findall(text)
    return float(matches[-1]) if matches else None
