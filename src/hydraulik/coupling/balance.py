"""Mass balance of a coupled run (extraction note 3, README 3.1).

The coupler exchanges volumes, so the interface adds no error: the surface side closes
to the error of SFINCS alone and the network side to SWMM's own continuity error.
:func:`coupled_balance` books every term so both can be told apart and a residual
above the threshold is reported (spec of 2026-08-20, section 6).

The terms, all in cubic metres: water enters the surface as ``rain`` and ``inflow``,
leaves it by ``infiltration``, by ``sink`` (a free edge the coupler drains) and by the
exchange with the network; it is left on the surface (``surface``) or in the network
(``network``), has left the network through the outfall (``outfall_net``), is spilled
by SWMM but not yet back on the surface (``pending``), or flooded out of a node that
has no surface cell (``lost_flooding``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["BALANCE_WARNING_PERCENT", "CoupledBalance", "coupled_balance"]

BALANCE_WARNING_PERCENT: Final = 1.0
"""Residual [percent of the water that entered] above which the balance is flagged."""


@dataclass(frozen=True)
class CoupledBalance:
    """Water volumes of a coupled run and their residuals [m3].

    Attributes
    ----------
    rain_m3, inflow_m3 : float
        Water that entered the surface as rain and as discharge.
    infiltration_m3 : float
        Water that infiltrated.
    surface_m3 : float
        Water left on the surface at the end.
    network_m3 : float
        Water stored in the network at the end.
    outfall_net_m3 : float
        Net volume through the outfall (positive = left the network).
    outfall_gross_inflow_m3 : float
        Volume that entered the network from the outfall (backwater).
    sink_m3 : float
        Water removed at a free surface edge by the coupler.
    exchanged_m3 : float
        Net volume given from the surface to the network.
    pending_m3 : float
        Spilled by SWMM but not yet returned to the surface (one interval).
    lost_flooding_m3 : float
        Flooded out of nodes that have no cell on the surface.
    total_error_m3 : float
        ``rain + inflow - infiltration - surface - network - outfall - sink - pending -
        lost_flooding``.
    surface_side_error_m3 : float
        ``rain + inflow - infiltration - surface - exchanged - sink``: the error of
        SFINCS, or the water that left over its outflow cells.
    network_side_error_m3 : float
        ``exchanged - pending - network - outfall - lost_flooding``: SWMM's continuity
        error.
    total_error_percent : float
        ``total_error`` as a percentage of the water that entered (rain, inflow and
        backwater).
    """

    rain_m3: float
    inflow_m3: float
    surface_m3: float
    network_m3: float
    outfall_net_m3: float
    outfall_gross_inflow_m3: float
    sink_m3: float
    exchanged_m3: float
    pending_m3: float
    total_error_m3: float
    surface_side_error_m3: float
    network_side_error_m3: float
    total_error_percent: float
    infiltration_m3: float = 0.0
    lost_flooding_m3: float = 0.0

    @property
    def flagged(self) -> bool:
        """bool: True when the total error exceeds :data:`BALANCE_WARNING_PERCENT`."""
        return abs(self.total_error_percent) > BALANCE_WARNING_PERCENT


def coupled_balance(
    *,
    rain_m3: float,
    inflow_m3: float,
    surface_m3: float,
    network_m3: float,
    outfall_net_m3: float,
    exchanged_m3: float,
    outfall_gross_inflow_m3: float = 0.0,
    sink_m3: float = 0.0,
    pending_m3: float = 0.0,
    infiltration_m3: float = 0.0,
    lost_flooding_m3: float = 0.0,
) -> CoupledBalance:
    """Book the volumes of a coupled run.

    Parameters
    ----------
    rain_m3, inflow_m3 : float
        Water that entered the surface [m3].
    surface_m3 : float
        Water on the surface at the end [m3].
    network_m3 : float
        Water in the network at the end [m3].
    outfall_net_m3 : float
        Net volume through the outfall, positive = left the network [m3].
    exchanged_m3 : float
        Net volume from the surface to the network [m3].
    outfall_gross_inflow_m3 : float, optional
        Volume that entered the network through the outfall [m3].
    sink_m3 : float, optional
        Water the coupler removed at a free edge [m3].
    pending_m3 : float, optional
        Spilled but not yet returned to the surface [m3].
    infiltration_m3 : float, optional
        Water that infiltrated into the ground [m3].
    lost_flooding_m3 : float, optional
        Water that flooded out of nodes without a surface cell [m3].

    Returns
    -------
    CoupledBalance
        The terms and the residuals.

    Examples
    --------
    >>> balance = coupled_balance(
    ...     rain_m3=100.0, inflow_m3=0.0, surface_m3=60.0, network_m3=10.0,
    ...     outfall_net_m3=30.0, exchanged_m3=40.0,
    ... )
    >>> balance.total_error_m3, balance.flagged
    (0.0, False)
    >>> coupled_balance(
    ...     rain_m3=100.0, inflow_m3=0.0, surface_m3=50.0, network_m3=10.0,
    ...     outfall_net_m3=30.0, exchanged_m3=40.0, infiltration_m3=10.0,
    ... ).total_error_m3
    0.0
    """
    total = rain_m3 + inflow_m3 - infiltration_m3 - surface_m3 - network_m3
    total -= outfall_net_m3 + sink_m3 + pending_m3 + lost_flooding_m3
    entered = rain_m3 + inflow_m3 + outfall_gross_inflow_m3
    return CoupledBalance(
        rain_m3=rain_m3,
        inflow_m3=inflow_m3,
        surface_m3=surface_m3,
        network_m3=network_m3,
        outfall_net_m3=outfall_net_m3,
        outfall_gross_inflow_m3=outfall_gross_inflow_m3,
        sink_m3=sink_m3,
        exchanged_m3=exchanged_m3,
        pending_m3=pending_m3,
        total_error_m3=total,
        surface_side_error_m3=(
            rain_m3 + inflow_m3 - infiltration_m3 - surface_m3 - exchanged_m3 - sink_m3
        ),
        network_side_error_m3=(
            exchanged_m3 - pending_m3 - network_m3 - outfall_net_m3 - lost_flooding_m3
        ),
        total_error_percent=100.0 * total / entered if entered > 0.0 else 0.0,
        infiltration_m3=infiltration_m3,
        lost_flooding_m3=lost_flooding_m3,
    )
