"""Where a model of a SFINCS directory has its cells (ADR-0004, ADR-0005).

The BMI of SFINCS numbers the active cells of a model in the order of the index file
(``sfincs.ind``: the column ``m`` outer, the row ``n`` inner, both counted from the
south-west corner), and ``qext``, ``zs`` and ``zb`` hold one value per active cell in
that order. This module reads the grid and the index file of a regular, unrotated model
in binary input mode (what :mod:`hydraulik.engines.sfincs.model` writes), so that the
coupler can tell, without the library, which point lies on which cell, and so that a
call into the library is only made for a point that does lie on an active cell.

Subgrid, quadtree, rotated and ASCII-input models are not read: their cells are numbered
differently (ADR-0004).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from hydraulik.engines.sfincs.inp import read_inp
from hydraulik.engines.sfincs.model import RegularGrid
from hydraulik.exceptions import InputDataError, UnsupportedError

__all__ = ["ModelLayout"]

_UNSUPPORTED_KEYS = {
    "qtrfile": "a quadtree grid",
    "sbgfile": "a subgrid table",
    "rotation": "a rotated grid",
}


@dataclass(frozen=True)
class ModelLayout:
    """The grid of a model and the numbering of its active cells.

    Attributes
    ----------
    grid : RegularGrid
        Origin, cell size, shape and CRS.
    index : ndarray of int32
        ``(m - 1) * nmax + n`` (1-based) of every active cell, increasing; the position
        of a cell in this array is its position in the arrays of the BMI.
    """

    grid: RegularGrid
    index: NDArray[np.int32]

    @classmethod
    def read(cls, directory: str | Path) -> ModelLayout:
        """Read the layout of a model directory.

        Parameters
        ----------
        directory : str or Path
            The directory with ``sfincs.inp`` and the index file.

        Returns
        -------
        ModelLayout
            The layout.

        Raises
        ------
        NotFoundError
            If there is no ``sfincs.inp``.
        UnsupportedError
            If the model is not a regular, unrotated grid in binary input mode (reason
            ``model_layout``).
        InputDataError
            If a key of the grid is missing or not a number, or the index file does not
            match the grid (reason ``invalid_index``).
        """
        folder = Path(directory)
        inp = read_inp(folder)
        for key, what in _UNSUPPORTED_KEYS.items():
            if key in inp and (key != "rotation" or float(inp[key] or 0) != 0.0):
                raise UnsupportedError(
                    f"the model has {what} ({key}); only regular grids are supported",
                    details={"key": key},
                    hint="Build the model with `hydraulik model build` (ADR-0004).",
                    reason="model_layout",
                )
        if inp.get("inputformat", "bin") != "bin":
            raise UnsupportedError(
                f"the model reads {inp['inputformat']!r} input; only binary input is "
                "supported",
                details={"key": "inputformat", "value": inp["inputformat"]},
                reason="model_layout",
            )
        try:
            grid = RegularGrid(
                float(inp["x0"]),
                float(inp["y0"]),
                float(inp["dx"]),
                int(inp["mmax"]),
                int(inp["nmax"]),
                int(inp.get("epsg", "0")),
            )
            dy = float(inp.get("dy", inp["dx"]))
        except (KeyError, ValueError) as exc:
            raise InputDataError(
                f"sfincs.inp lacks a number for x0, y0, dx, mmax or nmax: {exc}",
                details={"keys": ["x0", "y0", "dx", "mmax", "nmax"]},
                reason="invalid_inp",
            ) from exc
        if dy != grid.dx_m:
            raise UnsupportedError(
                f"the cells are {grid.dx_m:g} m by {dy:g} m; only square cells are "
                "supported",
                details={"key": "dy", "value": dy},
                reason="model_layout",
            )
        path = folder / inp.get("indexfile", "sfincs.ind")
        if not path.is_file():
            raise InputDataError(
                f"the index file {path.name} of the model does not exist",
                details={"path": str(path)},
                reason="invalid_index",
            )
        raw = path.read_bytes()
        index = np.frombuffer(raw[4:], dtype=np.int32)
        count = int(np.frombuffer(raw[:4], dtype=np.int32)[0]) if len(raw) >= 4 else -1
        cells = grid.rows * grid.columns
        if (
            count != index.size
            or index.size == 0
            or index[0] < 1
            or index[-1] > cells
            or np.any(np.diff(index) <= 0)
        ):
            raise InputDataError(
                f"{path.name} does not match the grid of {grid.columns} x {grid.rows}",
                details={"path": str(path)},
                reason="invalid_index",
            )
        return cls(grid, index)

    @property
    def active_cells(self) -> int:
        """int: the number of active cells."""
        return int(self.index.size)

    def cell_of(self, x_m: float, y_m: float) -> int | None:
        """Return the position of the active cell that holds a point, or ``None``.

        Parameters
        ----------
        x_m, y_m : float
            Position in the CRS of the model [m].

        Returns
        -------
        int or None
            0-based position in the arrays of the BMI; ``None`` when the point lies
            outside the grid or on an inactive cell.

        Examples
        --------
        >>> layout = ModelLayout(
        ...     RegularGrid(0.0, 0.0, 10.0, 2, 2), np.array([1, 2, 4], dtype=np.int32)
        ... )
        >>> layout.cell_of(5.0, 15.0), layout.cell_of(15.0, 5.0)
        (1, None)
        """
        found = self.grid.cell_of(x_m, y_m)
        if found is None:
            return None
        row, column = found
        flat = column * self.grid.rows + row + 1
        position = int(np.searchsorted(self.index, flat))
        if position < self.index.size and int(self.index[position]) == flat:
            return position
        return None
