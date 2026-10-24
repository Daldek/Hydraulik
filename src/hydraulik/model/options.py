"""The request of ``model build`` as data, without any scientific dependency.

``hydraulik model build --check`` plans the files before anything is read, and it must
do so on a machine without the ``model`` extra, so this module imports nothing heavy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hydraulik.engines.sfincs.inp import FILES

__all__ = ["DEFAULT_MANNING", "DEFAULT_RECESSION_MIN", "BuildOptions"]

DEFAULT_MANNING: Final = 0.04
"""Manning ``n`` [s/m^(1/3)] of a model without a Manning option (mixed urban cover)."""

DEFAULT_RECESSION_MIN: Final = 60.0
"""Minutes the simulation lasts after the rain ends, so the surface water can move."""


@dataclass(frozen=True)
class BuildOptions:
    """What ``model build`` was asked to do, checked for combinations.

    Attributes
    ----------
    dem : tuple of Path
        Elevation rasters; the first sets the CRS of the model and wins where they
        overlap, the next ones fill what the earlier ones leave without data.
    dx_m : float
        Cell size [m].
    rain : Path
        Rain table (``time_min``, ``depth_mm``).
    bbox : tuple of float or None
        ``(min_x, min_y, max_x, max_y)`` of the domain in ``crs``.
    crs : str or None
        CRS of ``bbox`` (``EPSG:2180``).
    geometry, layer : Path or None, str or None
        Polygon file and layer of the domain.
    manning : float or None
        Uniform Manning ``n``; :data:`DEFAULT_MANNING` when no Manning option is given.
    manning_raster : Path or None
        Manning ``n`` per cell.
    curve_number_raster, retention_mm_raster : Path or None
        SCS curve number per cell, or SCS retention ``S`` [mm] per cell (one of them).
    recession_min : float
        Minutes the run lasts after the rain.
    outlet, outlet_layer : Path or None, str or None
        Geometries where water leaves the domain, and their layer.
    observation_points : Path or None
        Station table (``name``, ``x_m``, ``y_m``).
    """

    dem: tuple[Path, ...]
    dx_m: float
    rain: Path
    bbox: tuple[float, float, float, float] | None = None
    crs: str | None = None
    geometry: Path | None = None
    layer: str | None = None
    manning: float | None = None
    manning_raster: Path | None = None
    curve_number_raster: Path | None = None
    retention_mm_raster: Path | None = None
    recession_min: float = DEFAULT_RECESSION_MIN
    outlet: Path | None = None
    outlet_layer: str | None = None
    observation_points: Path | None = None

    def planned_names(self) -> tuple[str, ...]:
        """Return the names of the files the build writes, known before it starts.

        Returns
        -------
        tuple of str
            ``sfincs.inp``, the index, mask, elevation and rain files always;
            ``sfincs.man`` for a Manning raster, ``sfincs.scs`` for a curve number or
            retention raster, ``sfincs.obs`` for observation points.

        Examples
        --------
        >>> from pathlib import Path
        >>> BuildOptions((Path("a.tif"), ), 5.0, Path("rain.csv")).planned_names()[-1]
        'sfincs.precip'
        """
        roles = ["inp", "index", "mask", "elevation", "precip"]
        if self.manning_raster is not None:
            roles.append("manning")
        if self.curve_number_raster is not None or self.retention_mm_raster is not None:
            roles.append("curve_number")
        if self.observation_points is not None:
            roles.append("observations")
        return tuple(FILES[role] for role in roles)
