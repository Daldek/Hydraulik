"""Diagnostics of coupled runs: oscillation, held maxima, sustained spills.

The feasibility test showed that the settings that damp the exchange are not
universal (README 3.9) and that SWMM's ``EXTRAN`` solver makes head spikes of 1.3 to
1.4 m within 1 s when a node becomes pressurised (README 7.1, extraction note 7).
These functions measure both, so a result can say how far to trust it:

* :func:`sign_flips` and :func:`window_statistics` detect a limit cycle of the
  exchange in a node;
* :func:`held_maximum` is the maximum that was held without interruption for at least
  ``T`` seconds, the direction chosen in README 7.1 instead of a percentile (a
  percentile depends on the length of the record); :func:`is_numerical_spike` compares
  it with the raw maximum;
* :func:`sustained_spill` tells a real spill from the false spills of the spikes.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "DEFAULT_HOLD_S",
    "DEFAULT_SPIKE_TOLERANCE_M",
    "SpillSummary",
    "WindowStatistics",
    "held_maximum",
    "is_numerical_spike",
    "sign_flips",
    "sustained_spill",
    "window_statistics",
]

DEFAULT_HOLD_S: Final = 10.0
"""Start value of ``T`` [s]: 5 s is too short (a spike lasts 5 to 10 s), 30 s cuts
real short peaks by about 20 percent, 10 s by 2 to 4 percent (README 7.1)."""

DEFAULT_SPIKE_TOLERANCE_M: Final = 0.05
"""Difference [m] between the raw and the held maximum above which a result is marked
as a possible numerical spike (README 7.1)."""


def sign_flips(values: ArrayLike, threshold: float = 1e-6) -> int:
    """Count the changes of sign of a series, ignoring values near zero.

    Parameters
    ----------
    values : array-like
        Exchange discharge of one node [m3/s], one value per interval.
    threshold : float, optional
        Values with a smaller absolute value are ignored [m3/s].

    Returns
    -------
    int
        The number of times the sign changes between consecutive significant values.

    Examples
    --------
    >>> sign_flips([0.1, -0.1, 0.0, 0.2, 0.3, -0.2])
    3
    """
    series = np.asarray(values, dtype=float)
    significant = series[np.abs(series) > threshold]
    if significant.size < 2:
        return 0
    return int(np.sum(np.diff(np.sign(significant)) != 0))


@dataclass(frozen=True)
class WindowStatistics:
    """Statistics of a series over a time window.

    Attributes
    ----------
    mean : float
        Mean of the window.
    std : float
        Standard deviation of the window.
    minimum : float
        Smallest value.
    maximum : float
        Largest value.
    sign_flips : int
        Changes of sign inside the window (see :func:`sign_flips`).
    drift : float
        Mean of the second half minus the mean of the window: a steady state has
        none.
    """

    mean: float
    std: float
    minimum: float
    maximum: float
    sign_flips: int
    drift: float


def window_statistics(
    times_s: ArrayLike, values: ArrayLike, end_s: float, length_s: float
) -> WindowStatistics:
    """Return mean, spread, sign flips and drift of ``values`` in ``(end-length, end]``.

    Used for steady states, where the true exchange is constant, so any spread is
    numerical (README 2.7).

    Parameters
    ----------
    times_s : array-like
        Time of each value [s].
    values : array-like
        The series, for example the exchange of one node [m3/s].
    end_s : float
        End of the window [s].
    length_s : float
        Length of the window [s].

    Returns
    -------
    WindowStatistics
        The statistics.

    Raises
    ------
    ValueError
        If the window holds no value.

    Examples
    --------
    >>> stats = window_statistics([1, 2, 3, 4], [1.0, 1.0, 1.0, 1.0], 4, 4)
    >>> stats.mean, stats.std, stats.sign_flips
    (1.0, 0.0, 0)
    """
    t = np.asarray(times_s, dtype=float)
    q = np.asarray(values, dtype=float)
    window = (t > end_s - length_s) & (t <= end_s)
    half = (t > end_s - length_s / 2) & (t <= end_s)
    if not window.any():
        raise ValueError("the window holds no value")
    inside = q[window]
    return WindowStatistics(
        mean=float(inside.mean()),
        std=float(inside.std()),
        minimum=float(inside.min()),
        maximum=float(inside.max()),
        sign_flips=sign_flips(inside),
        drift=float(q[half].mean() - inside.mean()),
    )


def held_maximum(
    times_s: Sequence[float] | NDArray[np.float64],
    values: Sequence[float] | NDArray[np.float64],
    hold_s: float = DEFAULT_HOLD_S,
) -> float:
    """Return the highest value held without interruption for at least ``hold_s``.

    This is the maximum, over every moment ``t``, of the minimum of the series in the
    window ``[t - hold_s, t]``; a spike shorter than ``hold_s`` does not raise it, a
    plateau of that length does. Unlike a percentile it does not depend on the length
    of the record (README 7.1).

    Parameters
    ----------
    times_s : sequence of float
        Time of each value [s], increasing.
    values : sequence of float
        The series, for example the head in a node [m].
    hold_s : float, optional
        ``T`` [s].

    Returns
    -------
    float
        The held maximum. A record shorter than ``hold_s`` gives its minimum, the
        value that was held for the whole record.

    Raises
    ------
    ValueError
        If the series is empty or its lengths differ.

    Examples
    --------
    >>> t = list(range(30))
    >>> q = [0.0] * 30
    >>> q[10] = 5.0                       # a one-second spike
    >>> held_maximum(t, q, 10.0)
    0.0
    >>> held_maximum(t, [1.0] * 15 + [3.0] * 15, 10.0)
    3.0
    """
    t = np.asarray(times_s, dtype=float)
    v = np.asarray(values, dtype=float)
    if t.size == 0 or t.size != v.size:
        raise ValueError("times and values must be non-empty and of equal length")
    if t[-1] - t[0] < hold_s:
        return float(v.min())
    best = -np.inf
    window: deque[int] = (
        deque()
    )  # indices with increasing values: the window minimum first
    for i in range(t.size):
        while window and v[window[-1]] >= v[i]:
            window.pop()
        window.append(i)
        while t[window[0]] < t[i] - hold_s:
            window.popleft()
        if t[i] - t[0] >= hold_s:
            best = max(best, float(v[window[0]]))
    return float(best)


def is_numerical_spike(
    raw_maximum: float,
    held: float,
    tolerance: float = DEFAULT_SPIKE_TOLERANCE_M,
) -> bool:
    """Tell whether the raw maximum exceeds the held one by more than a tolerance.

    Parameters
    ----------
    raw_maximum : float
        The raw maximum of the series.
    held : float
        :func:`held_maximum` of the same series.
    tolerance : float, optional
        Difference above which the result is a possible numerical spike [m].

    Returns
    -------
    bool
        True when ``raw_maximum - held > tolerance``.

    Examples
    --------
    >>> is_numerical_spike(31.5, 31.2)
    True
    """
    return raw_maximum - held > tolerance


@dataclass(frozen=True)
class SpillSummary:
    """Spills out of a node, split into sustained and short ones.

    Attributes
    ----------
    total_m3 : float
        All spilled volume [m3].
    sustained_m3 : float
        Volume in spells that lasted at least the minimum duration [m3].
    sustained : bool
        True when a spell lasted that long and its volume reached the threshold: the
        manhole really spills.
    longest_s : float
        Duration of the longest spell [s].
    """

    total_m3: float
    sustained_m3: float
    sustained: bool
    longest_s: float


def sustained_spill(
    times_s: ArrayLike,
    spill_m3s: ArrayLike,
    min_duration_s: float = DEFAULT_HOLD_S,
    min_volume_m3: float = 1.0,
) -> SpillSummary:
    """Tell a real spill from the short false spills of head spikes (README 7.1).

    A spell is a run of consecutive intervals with a spill. False spills are 0.01 to
    0.10 m3 in 1 to 2 s, the real one of the feasibility test 532 m3 in 17 min. The
    volume threshold is provisional: README 7.1 says it still has to be fixed.

    Parameters
    ----------
    times_s : array-like
        End time of each interval [s].
    spill_m3s : array-like
        Spill discharge of the node in each interval [m3/s].
    min_duration_s : float, optional
        Shortest spell that counts [s].
    min_volume_m3 : float, optional
        Smallest volume of such a spell that counts [m3]; provisional.

    Returns
    -------
    SpillSummary
        Totals and the verdict.

    Examples
    --------
    >>> t = list(range(1, 21))
    >>> sustained_spill(t, [0.0] * 5 + [2.0] * 12 + [0.0] * 3).sustained
    True
    >>> sustained_spill(t, [0.0] * 5 + [0.05] * 2 + [0.0] * 13).sustained
    False
    """
    t = np.asarray(times_s, dtype=float)
    q = np.asarray(spill_m3s, dtype=float)
    if t.size == 0:
        return SpillSummary(0.0, 0.0, False, 0.0)
    dt = np.diff(t, prepend=t[0] - (t[1] - t[0] if t.size > 1 else 1.0))
    volume = q * dt
    active = q > 1e-9
    total = float(volume.sum())
    sustained_volume = 0.0
    longest = 0.0
    sustained = False
    i = 0
    while i < t.size:
        if not active[i]:
            i += 1
            continue
        j = i
        while j + 1 < t.size and active[j + 1]:
            j += 1
        duration = float(dt[i : j + 1].sum())
        spell_volume = float(volume[i : j + 1].sum())
        longest = max(longest, duration)
        if duration >= min_duration_s:
            sustained_volume += spell_volume
            if spell_volume >= min_volume_m3:
                sustained = True
        i = j + 1
    return SpillSummary(total, sustained_volume, sustained, longest)
