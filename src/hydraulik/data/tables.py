"""The two small tables that Hydraulik reads and writes: rain and hydrograph.

Both are CSV with a header and the units in the column names (DEV-8.2):

* a **rain table** has ``time_min`` (the end of each step, strictly regular, the first
  step starts at 0) and ``depth_mm`` (the depth that fell in the step). It is what
  ``hydraulik rainfall build`` writes and ``hydraulik model build`` reads, and it has
  the shape of a Hydrolog hyetograph (``HietogramResult``);
* a **hydrograph table** has ``time_min`` (elapsed) and ``discharge_m3s``, the form in
  which Hydrolog hands a hydrograph to Hydraulik. ``hydraulik swmm run`` reads it as the
  inflow of a node.

Only the standard library is needed to read them; a rain table gives the arrays that
the SFINCS writer takes.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hydraulik.exceptions import InputDataError, NotFoundError

__all__ = [
    "HYDROGRAPH_COLUMNS",
    "RAIN_COLUMNS",
    "Hydrograph",
    "RainTable",
    "read_hydrograph",
    "read_rain_table",
    "render_rain_table",
]

RAIN_COLUMNS: Final = ("time_min", "depth_mm")
HYDROGRAPH_COLUMNS: Final = ("time_min", "discharge_m3s")


def _read_columns(
    path: Path, columns: tuple[str, ...], reason: str
) -> list[list[float]]:
    """Return the numeric columns of a CSV file, one list per column."""
    if not path.is_file():
        raise NotFoundError(
            f"table not found: {path}",
            details={"path": str(path)},
            reason="path_missing",
        )

    def fail(why: str, row: int | None = None) -> InputDataError:
        return InputDataError(
            f"{path.name}: {why}",
            details={"path": str(path), **({} if row is None else {"row": row})},
            hint=f"Columns: {', '.join(columns)}.",
            reason=reason,
        )

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise fail("not UTF-8 text") from exc
    reader = csv.reader(text.splitlines())
    header = [cell.strip() for cell in next(reader, [])]
    missing = [name for name in columns if name not in header]
    if missing:
        raise fail(f"lacks the columns {', '.join(missing)}")
    position = [header.index(name) for name in columns]
    values: list[list[float]] = [[] for _ in columns]
    for number, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        try:
            numbers = [float(row[index]) for index in position]
        except (IndexError, ValueError):
            raise fail("a value is missing or not a number", number) from None
        if not all(math.isfinite(n) for n in numbers):
            raise fail("a value is not finite", number)
        for column, value in zip(values, numbers, strict=True):
            column.append(value)
    if not values[0]:
        raise fail("has no rows")
    return values


@dataclass(frozen=True)
class RainTable:
    """Uniform rain as the depth of each step of a regular hyetograph.

    Attributes
    ----------
    step_min : float
        Length of a step [min].
    depth_mm : tuple of float
        Depth that fell in each step [mm], not negative.
    """

    step_min: float
    depth_mm: tuple[float, ...]

    @property
    def duration_min(self) -> float:
        """float: length of the rain [min]."""
        return self.step_min * len(self.depth_mm)

    @property
    def total_mm(self) -> float:
        """float: total depth [mm]."""
        return float(sum(self.depth_mm))

    @property
    def peak_intensity_mm_h(self) -> float:
        """float: intensity of the heaviest step [mm/h]."""
        return max(self.depth_mm) * 60.0 / self.step_min


def read_rain_table(path: str | Path) -> RainTable:
    r"""Read a rain table (``time_min``, ``depth_mm``).

    Parameters
    ----------
    path : str or Path
        The CSV file.

    Returns
    -------
    RainTable
        The regular series.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If a column is missing, a value is not a number, a depth is negative, or the
        times are not strictly regular from the first step (``time_min`` is the end of
        each step, so the first value is the step).

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     p = pathlib.Path(tmp) / "rain.csv"
    ...     _ = p.write_text("time_min,depth_mm\n5,1.0\n10,3.0\n")
    ...     table = read_rain_table(p)
    >>> table.step_min, table.total_mm
    (5.0, 4.0)
    """
    source = Path(path)
    times, depths = _read_columns(source, RAIN_COLUMNS, "invalid_rain_table")
    step = times[0]

    def fail(why: str) -> InputDataError:
        return InputDataError(
            f"{source.name}: {why}",
            details={"path": str(source)},
            hint="time_min is the end of each step: 5, 10, 15, ... for a 5 min step.",
            reason="invalid_rain_table",
        )

    if step <= 0:
        raise fail(
            "the first time is the length of the first step and must be positive"
        )
    for index, time_min in enumerate(times):
        if not math.isclose(time_min, step * (index + 1), rel_tol=1e-9, abs_tol=1e-9):
            raise fail(
                f"the times are not regular from the first step (row {index + 2})"
            )
    if min(depths) < 0:
        raise fail("a depth is negative")
    return RainTable(step, tuple(depths))


def render_rain_table(step_min: float, depth_mm: Sequence[float]) -> str:
    """Return the text of a rain table.

    Parameters
    ----------
    step_min : float
        Length of a step [min].
    depth_mm : sequence of float
        Depth of each step [mm].

    Returns
    -------
    str
        The CSV text, ``time_min`` being the end of each step.

    Examples
    --------
    >>> render_rain_table(5.0, [1.0, 2.5]).splitlines()
    ['time_min,depth_mm', '5,1.0000', '10,2.5000']
    """
    lines = [",".join(RAIN_COLUMNS)]
    lines += [
        f"{step_min * (index + 1):g},{depth:.4f}"
        for index, depth in enumerate(depth_mm)
    ]
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Hydrograph:
    """A discharge series, linearly interpolated, zero outside its time range.

    Attributes
    ----------
    times_s : tuple of float
        Elapsed time [s], strictly increasing.
    discharge_m3s : tuple of float
        Discharge [m3/s], not negative.
    """

    times_s: tuple[float, ...]
    discharge_m3s: tuple[float, ...]

    def at(self, time_s: float) -> float:
        """Return the discharge at ``time_s`` [m3/s]; 0 outside the series.

        Examples
        --------
        >>> Hydrograph((0.0, 60.0), (0.0, 2.0)).at(30.0)
        1.0
        """
        times, values = self.times_s, self.discharge_m3s
        if time_s < times[0] or time_s > times[-1]:
            return 0.0
        high = next(i for i, t in enumerate(times) if t >= time_s)
        if high == 0 or times[high] == time_s:
            return values[high]
        low = high - 1
        weight = (time_s - times[low]) / (times[high] - times[low])
        return values[low] + weight * (values[high] - values[low])

    @property
    def volume_m3(self) -> float:
        """float: the volume under the series [m3] (trapezoids)."""
        return sum(
            0.5 * (a + b) * (t1 - t0)
            for (t0, a), (t1, b) in zip(
                zip(self.times_s, self.discharge_m3s, strict=True),
                zip(self.times_s[1:], self.discharge_m3s[1:], strict=True),
                strict=False,
            )
        )


def read_hydrograph(path: str | Path) -> Hydrograph:
    r"""Read a hydrograph table (``time_min``, ``discharge_m3s``).

    Parameters
    ----------
    path : str or Path
        The CSV file.

    Returns
    -------
    Hydrograph
        The series with the time in seconds.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If a column is missing, a value is not a number, a discharge is negative or
        the times do not increase.

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     p = pathlib.Path(tmp) / "q.csv"
    ...     _ = p.write_text("time_min,discharge_m3s\n0,0\n1,2\n")
    ...     series = read_hydrograph(p)
    >>> series.at(30.0), series.volume_m3
    (1.0, 60.0)
    """
    source = Path(path)
    times, flows = _read_columns(source, HYDROGRAPH_COLUMNS, "invalid_hydrograph")
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise InputDataError(
            f"{source.name}: time_min must increase",
            details={"path": str(source)},
            reason="invalid_hydrograph",
        )
    if min(flows) < 0:
        raise InputDataError(
            f"{source.name}: a discharge is negative",
            details={"path": str(source)},
            reason="invalid_hydrograph",
        )
    return Hydrograph(tuple(t * 60.0 for t in times), tuple(flows))
