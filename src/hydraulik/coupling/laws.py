"""Exchange law between a surface cell and a sewer node (extraction note 3).

The law is continuous in the surface level ``zs`` and in the node head ``H``, so no
regime change makes the exchange jump (feasibility test, README 3.6). Discharges are
positive from the surface into the network and negative when the node spills.

* ``H >= zs``: the node spills, ``Q = -Q_o(H - zs)``.
* otherwise the surface water falls over the rim into the node: a free weir
  ``Q_w = 2/3 * C_w * P * (zs - z_t)**1.5 * sqrt(2 g)`` that the Villemonte (1947)
  factor reduces once the head rises above the rim ``z_t``, capped by the orifice law
  for the level difference.
* the orifice law ``Q_o(dh) = C_o * A * sqrt(2 g dh)`` is linear below 1 cm so its
  slope stays bounded at ``dh = 0``.

The default coefficients are those calibrated for a manhole by Rubinato et al. (2017,
J. Hydrol. 552, doi:10.1016/j.jhydrol.2017.06.024), referenced as in Itzi to the node
area ``A`` and the perimeter ``P = 2 sqrt(pi A)``. They are not valid for street
inlets with a grate: the inlet description is the main uncertainty of the coupling
(laboratory test, README 3.13).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

__all__ = [
    "DEFAULT_NODE_AREA_M2",
    "GRAVITY_M_S2",
    "ORIFICE_LINEAR_BELOW_M",
    "RUBINATO_ORIFICE_COEFFICIENT",
    "RUBINATO_WEIR_COEFFICIENT",
    "Inlet",
    "exchange_discharge_m3s",
    "limit_to_available_water",
    "orifice_discharge_m3s",
    "relax",
]

GRAVITY_M_S2: Final = 9.81
RUBINATO_WEIR_COEFFICIENT: Final = 0.54
RUBINATO_ORIFICE_COEFFICIENT: Final = 0.167
DEFAULT_NODE_AREA_M2: Final = 1.167
"""SWMM's default ``MIN_SURFAREA`` (12.566 ft2), set explicitly in the SWMM files."""

ORIFICE_LINEAR_BELOW_M: Final = 0.01
"""Level difference [m] below which the orifice law is linear."""


@dataclass(frozen=True)
class Inlet:
    """Geometry and coefficients of the exchange between one cell and one node.

    Attributes
    ----------
    area_m2 : float
        Reference area ``A`` [m2] of the node (the footprint of the manhole).
    weir_coefficient : float
        ``C_w`` of the free weir [-].
    orifice_coefficient : float
        ``C_o`` of the orifice [-].
    """

    area_m2: float = DEFAULT_NODE_AREA_M2
    weir_coefficient: float = RUBINATO_WEIR_COEFFICIENT
    orifice_coefficient: float = RUBINATO_ORIFICE_COEFFICIENT

    @property
    def perimeter_m(self) -> float:
        """float: perimeter ``P = 2 sqrt(pi A)`` [m] of a circle of area ``A``."""
        return 2.0 * math.sqrt(math.pi * self.area_m2)

    def scaled(self, factor: float) -> Inlet:
        """Return the inlet with both coefficients multiplied by ``factor``.

        Parameters
        ----------
        factor : float
            Multiplier of ``C_w`` and ``C_o``.

        Returns
        -------
        Inlet
            A new inlet; the area is unchanged.
        """
        return Inlet(
            self.area_m2,
            self.weir_coefficient * factor,
            self.orifice_coefficient * factor,
        )


def orifice_discharge_m3s(inlet: Inlet, head_difference_m: float) -> float:
    """Return the orifice discharge ``C_o A sqrt(2 g dh)``, linear for small ``dh``.

    Parameters
    ----------
    inlet : Inlet
        Geometry and coefficients.
    head_difference_m : float
        Level difference [m]; the sign is ignored.

    Returns
    -------
    float
        Discharge [m3/s], never negative.

    Examples
    --------
    >>> round(orifice_discharge_m3s(Inlet(), 0.1), 4)
    0.273
    """
    dh = abs(head_difference_m)
    coefficient = (
        inlet.orifice_coefficient * inlet.area_m2 * math.sqrt(2.0 * GRAVITY_M_S2)
    )
    if dh < ORIFICE_LINEAR_BELOW_M:
        return (
            coefficient
            * math.sqrt(ORIFICE_LINEAR_BELOW_M)
            * dh
            / ORIFICE_LINEAR_BELOW_M
        )
    return coefficient * math.sqrt(dh)


def exchange_discharge_m3s(
    inlet: Inlet, zs_m: float, ground_m: float, head_m: float
) -> float:
    """Return the exchange discharge between a surface cell and a node.

    Parameters
    ----------
    inlet : Inlet
        Geometry and coefficients of the link.
    zs_m : float
        Water level of the surface cell [m].
    ground_m : float
        Rim of the node, the bed of the cell [m].
    head_m : float
        Hydraulic head in the node [m].

    Returns
    -------
    float
        Discharge [m3/s]; positive from the surface into the network, negative when
        the node spills onto the surface. Continuous in ``zs_m`` and ``head_m``.

    Examples
    --------
    >>> exchange_discharge_m3s(Inlet(), zs_m=10.1, ground_m=10.0, head_m=5.0) > 0
    True
    >>> exchange_discharge_m3s(Inlet(), zs_m=10.0, ground_m=10.0, head_m=10.3) < 0
    True
    """
    if head_m >= zs_m:
        return -orifice_discharge_m3s(inlet, head_m - zs_m)
    upstream_depth_m = zs_m - ground_m
    if upstream_depth_m <= 0.0:
        return 0.0
    weir = (
        2.0
        / 3.0
        * inlet.weir_coefficient
        * inlet.perimeter_m
        * math.pow(upstream_depth_m, 1.5)
        * math.sqrt(2.0 * GRAVITY_M_S2)
    )
    downstream_depth_m = head_m - ground_m
    if downstream_depth_m > 0.0:
        ratio = downstream_depth_m / upstream_depth_m
        weir *= math.pow(1.0 - math.pow(ratio, 1.5), 0.385)
    # Below the rim the water falls freely into the node: the orifice head is the
    # surface depth, not the difference with the (lower) node head.
    return min(weir, orifice_discharge_m3s(inlet, zs_m - max(head_m, ground_m)))


def limit_to_available_water(
    discharge_m3s: float, depth_m: float, cell_area_m2: float, window_s: float
) -> tuple[float, bool]:
    """Limit an inflow to the water that stands in the cell over ``window_s``.

    SFINCS clips the level at the bed and silently creates the water it could not
    remove (extraction note 7), so the coupler never asks for more than the cell
    holds over the longest interval SFINCS may take: ``Q <= h A / window``.

    Parameters
    ----------
    discharge_m3s : float
        Requested discharge from the surface into the network [m3/s].
    depth_m : float
        Water depth in the cell [m].
    cell_area_m2 : float
        Area of the cell [m2].
    window_s : float
        Exchange interval plus the largest SFINCS step ``dtmax`` [s].

    Returns
    -------
    tuple of (float, bool)
        The limited discharge and whether the limit applied. Only an inflow into the
        network (positive) is limited.

    Examples
    --------
    >>> limit_to_available_water(1.0, 0.01, 4.0, 2.0)
    (0.02, True)
    """
    if discharge_m3s <= 0.0:
        return discharge_m3s, False
    limit = max(depth_m, 0.0) * cell_area_m2 / window_s
    if discharge_m3s > limit:
        return limit, True
    return discharge_m3s, False


def relax(new_m3s: float, previous_m3s: float, weight: float) -> float:
    """Return ``w * new + (1 - w) * previous`` (under-relaxation, README 2.5).

    The volume handed to the other model is always computed from the discharge that
    was actually used, so relaxation does not break the mass balance.

    Parameters
    ----------
    new_m3s : float
        Discharge of the current interval [m3/s].
    previous_m3s : float
        Discharge used in the previous interval [m3/s].
    weight : float
        ``w`` in (0, 1]; 1 means no relaxation.

    Returns
    -------
    float
        The relaxed discharge [m3/s].

    Examples
    --------
    >>> relax(1.0, 0.0, 0.1)
    0.1
    """
    return weight * new_m3s + (1.0 - weight) * previous_m3s
