"""The SFINCS BMI through ``ctypes``, and the surface model the coupler drives.

``libsfincs`` is the shared library that the user builds from the SFINCS sources with
``--enable-shared`` (ADR-0003); it is loaded with :class:`ctypes.CDLL` and never
bundled. Its BMI is the interface of the Basic Model Interface: ``initialize``,
``update_until`` (an **absolute** time; the last step is not clipped, so SFINCS may
overshoot the target by one adaptive step, and a target in the past still runs one
step), ``finalize``, pointers to the arrays ``zs`` (double), ``zb`` and ``qext``
(float; one value per **active** cell, in the order of the index file), and the
position of a point (``get_sfincs_cell_index``, 1-based) and the area of a cell.

Three facts shape this module (ADR-0005):

* **SFINCS keeps its state in global variables**: one model per process, and
  ``initialize`` reads ``sfincs.inp`` from the working directory.
  :class:`SfincsSurface` changes into the model directory while it is open, and the
  coupling command runs it in a process of its own
  (:mod:`hydraulik.coupling.worker`).
* **``qext`` has two units.** Up to v2.4.1 ``zs += qext * dt``, so ``qext`` is a rate
  of depth [m/s]; on ``main`` since PR 355 it is a flow [m3/s] per cell. ``qext_unit``
  (the setting ``sfincs.qext_unit``, ``ms`` or ``m3s``) says which; a wrong one is a
  wrong discharge by the cell area, and the water balance of the run flags it.
* **A sink larger than the water in the cell creates water**: SFINCS clips the level
  at the bed. The coupler limits the sink
  (:func:`hydraulik.coupling.laws.limit_to_available_water`).
"""

from __future__ import annotations

import contextlib
import ctypes
import os
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Literal

import numpy as np
from numpy.typing import NDArray

from hydraulik.engines.sfincs.inp import read_inp
from hydraulik.engines.sfincs.layout import ModelLayout
from hydraulik.exceptions import EngineError

__all__ = ["SfincsBmi", "SfincsSurface"]

QextUnit = Literal["m3s", "ms"]

_ERROR_LENGTH: Final = 1024
"""``BMI_LENERRMESSAGE``: the size of the buffer of ``get_last_bmi_error``."""

_FUNCTIONS: Final = (
    "initialize",
    "update_until",
    "finalize",
    "get_current_time",
    "get_end_time",
    "get_var_shape",
    "get_value_ptr",
    "set_logical",
    "get_sfincs_cell_index",
    "get_sfincs_cell_area",
)
"""What the coupler needs of the library."""

_used = False
"""True once a model was initialised in this process (SFINCS cannot start a second)."""


class SfincsBmi:
    """A thin ``ctypes`` wrapper of the BMI functions of ``libsfincs``.

    Parameters
    ----------
    library : str or Path
        The shared library (``libsfincs.so``, ``libsfincs.dylib``, ``sfincs.dll``).

    Raises
    ------
    EngineError
        If the library cannot be loaded or lacks a BMI function (reason
        ``engine_unavailable``).
    """

    def __init__(self, library: str | Path) -> None:
        path = Path(library)
        try:
            self._lib = ctypes.CDLL(str(path))
        except OSError as exc:
            raise EngineError(
                f"the SFINCS library {path} cannot be loaded: {exc}",
                details={"path": str(path)},
                hint="Build SFINCS with --enable-shared on this machine and set "
                "HYDRAULIK_SFINCS_LIBRARY to the libsfincs it made.",
                reason="engine_unavailable",
            ) from exc
        missing = [name for name in _FUNCTIONS if not hasattr(self._lib, name)]
        if missing:
            raise EngineError(
                f"{path.name} is not the SFINCS library: it lacks {', '.join(missing)}",
                details={"path": str(path), "missing": missing},
                hint="Point HYDRAULIK_SFINCS_LIBRARY at libsfincs of SFINCS v2.4 or "
                "newer.",
                reason="engine_unavailable",
            )
        self._lib.update_until.argtypes = [ctypes.c_double]
        self._path = path

    def _last_error(self) -> str | None:
        """Return the message of ``get_last_bmi_error`` when the library has one."""
        function = getattr(self._lib, "get_last_bmi_error", None)
        if function is None:
            return None
        buffer = ctypes.create_string_buffer(_ERROR_LENGTH)
        if function(buffer) != 0:
            return None
        text = buffer.value.decode("utf-8", errors="replace").strip()
        return text or None

    def _check(self, status: int, call: str) -> None:
        """Raise ``EngineError`` when a BMI call did not return 0."""
        if status == 0:
            return
        message = self._last_error()
        raise EngineError(
            f"the SFINCS BMI call {call} failed with code {status}"
            + (f": {message}" if message else ""),
            details={"call": call, "code": int(status), "library": str(self._path)},
            hint="Read sfincs.log in the output directory of the run.",
            reason="bmi_failed",
        )

    def initialize(self) -> None:
        """Initialise the model whose ``sfincs.inp`` is in the working directory.

        Raises
        ------
        EngineError
            If a model was already initialised in this process (reason
            ``one_model_per_process``) or SFINCS refuses the model (``bmi_failed``).
        """
        global _used  # noqa: PLW0603 - SFINCS itself has one global state per process
        if _used:
            raise EngineError(
                "SFINCS can run one model per process: it keeps its state in global "
                "variables",
                hint="Start a new process for the next model; `hydraulik model "
                "couple` does so itself.",
                reason="one_model_per_process",
            )
        _used = True
        self._check(self._lib.initialize(), "initialize")

    def update_until(self, time_s: float) -> None:
        """Advance the model to ``time_s`` [s from its start]; it may overshoot."""
        self._check(self._lib.update_until(ctypes.c_double(time_s)), "update_until")

    def finalize(self) -> None:
        """Finalise the model: SFINCS writes its last output and its log."""
        self._check(self._lib.finalize(), "finalize")

    def current_time(self) -> float:
        """Return the model time [s from its start]."""
        value = ctypes.c_double()
        self._check(self._lib.get_current_time(ctypes.byref(value)), "get_current_time")
        return float(value.value)

    def end_time(self) -> float:
        """Return the end of the simulation [s from its start]."""
        value = ctypes.c_double()
        self._check(self._lib.get_end_time(ctypes.byref(value)), "get_end_time")
        return float(value.value)

    def set_logical(self, name: str, value: bool) -> None:
        """Set a logical flag of the model (``qext`` switches the external source)."""
        flag = (ctypes.c_int * 1)(1 if value else 0)
        self._check(self._lib.set_logical(name.encode(), flag), "set_logical")

    def array(self, name: str, ctype: Any) -> NDArray[Any]:
        """Return a numpy view on an array of the model; writes go to SFINCS.

        Parameters
        ----------
        name : str
            ``zs``, ``zb`` or ``qext``.
        ctype : ctypes type
            ``ctypes.c_double`` or ``ctypes.c_float``, the type SFINCS stores it in.

        Returns
        -------
        ndarray
            One value per active cell, no copy; valid until :meth:`finalize`.
        """
        shape = (ctypes.c_int * 6)()
        self._check(
            self._lib.get_var_shape(name.encode(), shape), f"get_var_shape({name})"
        )
        pointer = ctypes.c_void_p()
        self._check(
            self._lib.get_value_ptr(name.encode(), ctypes.byref(pointer)),
            f"get_value_ptr({name})",
        )
        if not pointer.value:
            raise EngineError(
                f"the SFINCS library gave no memory for {name}",
                details={"variable": name},
                reason="bmi_failed",
            )
        typed = ctypes.cast(pointer, ctypes.POINTER(ctype))
        view: NDArray[Any] = np.ctypeslib.as_array(typed, shape=(int(shape[0]),))
        return view

    def cell_index(self, x_m: float, y_m: float) -> int:
        """Return the 0-based position of the cell that holds a point.

        The point must lie on an active cell: the library does not say otherwise.
        """
        index = ctypes.c_int()
        self._check(
            self._lib.get_sfincs_cell_index(
                ctypes.byref(ctypes.c_double(x_m)),
                ctypes.byref(ctypes.c_double(y_m)),
                ctypes.byref(index),
            ),
            "get_sfincs_cell_index",
        )
        return int(index.value) - 1

    def cell_area_m2(self, position: int) -> float:
        """Return the area of the cell at a 0-based position [m2]."""
        area = ctypes.c_double()
        self._check(
            self._lib.get_sfincs_cell_area(
                ctypes.byref(ctypes.c_int(position + 1)), ctypes.byref(area)
            ),
            "get_sfincs_cell_area",
        )
        return float(area.value)


class SfincsSurface:
    """The SFINCS model of a directory, as the surface the coupler drives.

    Use as a context manager: entering changes into the model directory and initialises
    the model, leaving finalises it and changes back. ``qext`` is switched on, zeroed.

    Parameters
    ----------
    library : str or Path
        ``libsfincs``.
    directory : str or Path
        The model directory (a regular grid in binary input mode).
    qext_unit : {"m3s", "ms"}
        The unit of ``qext`` in that library (module text).

    Raises
    ------
    UnsupportedError
        If the model is not a regular unrotated grid in binary input mode.
    EngineError
        If the library cannot be loaded or SFINCS fails (see :class:`SfincsBmi`).
    """

    def __init__(
        self, library: str | Path, directory: str | Path, *, qext_unit: QextUnit
    ) -> None:
        self._directory = Path(directory).resolve()
        self._layout = ModelLayout.read(self._directory)
        self._max_step_s = float(read_inp(self._directory).get("dtmax", "60"))
        self._unit = qext_unit
        self._bmi = SfincsBmi(library)
        self._previous: Path | None = None
        self._finalized = False
        self._area_m2 = self._layout.grid.dx_m**2
        self._area_checked = False

    def __enter__(self) -> SfincsSurface:
        """Change into the model directory and start SFINCS."""
        self._previous = Path.cwd()
        os.chdir(self._directory)
        try:
            self._bmi.initialize()
            self._zs = self._bmi.array("zs", ctypes.c_double)
            self._zb = self._bmi.array("zb", ctypes.c_float)
            self._qext = self._bmi.array("qext", ctypes.c_float)
            self._bmi.set_logical("qext", True)
            self._qext[:] = 0.0
            if self._zs.size != self._layout.active_cells:
                raise EngineError(
                    f"SFINCS has {self._zs.size} cells, the index file "
                    f"{self._layout.active_cells}",
                    details={"cells": int(self._zs.size)},
                    reason="cell_numbering",
                )
        except BaseException:
            os.chdir(self._previous)
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Finalise SFINCS if that has not happened and change back."""
        try:
            if exc is None:
                self.finalize()
            else:
                with contextlib.suppress(EngineError):
                    self.finalize()
        finally:
            if self._previous is not None:
                os.chdir(self._previous)

    def finalize(self) -> None:
        """Finalise SFINCS (its last output is written); safe to call twice."""
        if not self._finalized:
            self._finalized = True
            self._bmi.finalize()

    @property
    def time_s(self) -> float:
        """float: the time of the model [s from its start]."""
        return self._bmi.current_time()

    @property
    def end_s(self) -> float:
        """float: the end of the simulation [s from its start]."""
        return self._bmi.end_time()

    @property
    def max_step_s(self) -> float:
        """float: ``dtmax`` of the model, the longest step SFINCS may take [s]."""
        return self._max_step_s

    def locate(self, x_m: float, y_m: float) -> int | None:
        """Return the cell that holds a point, or ``None`` off the active domain.

        The position comes from the index file; the library is asked only for a point
        that lies on an active cell, and must agree.

        Raises
        ------
        EngineError
            If the library numbers the cell differently (reason ``cell_numbering``), or
            gives it another area than the grid does.
        """
        position = self._layout.cell_of(x_m, y_m)
        if position is None:
            return None
        found = self._bmi.cell_index(x_m, y_m)
        if found != position:
            raise EngineError(
                f"SFINCS puts ({x_m:g}, {y_m:g}) on cell {found}, the index file on "
                f"{position}",
                details={"x_m": x_m, "y_m": y_m, "library": found, "model": position},
                hint="Only regular grids in binary input mode are supported.",
                reason="cell_numbering",
            )
        if not self._area_checked:
            area = self._bmi.cell_area_m2(position)
            if abs(area - self._area_m2) > 1e-6 * self._area_m2:
                raise EngineError(
                    f"SFINCS gives a cell {area:g} m2, the grid {self._area_m2:g} m2",
                    details={"area_m2": area},
                    reason="cell_numbering",
                )
            self._area_checked = True
        return position

    def bed_m(self, cell: int) -> float:
        """Return the bed level of a cell [m]."""
        return float(self._zb[cell])

    def level_m(self, cell: int) -> float:
        """Return the water level of a cell [m]."""
        return float(self._zs[cell])

    def area_m2(self, cell: int) -> float:
        """Return the area of a cell [m2]."""
        del cell  # every cell of a regular grid has the same area
        return self._area_m2

    def set_source_m3s(self, cell: int, discharge_m3s: float) -> None:
        """Set the water that enters a cell from outside [m3/s]; negative takes it out.

        It stays in force until it is set again, in the unit the library expects.
        """
        if self._unit == "m3s":
            self._qext[cell] = discharge_m3s
        else:
            self._qext[cell] = discharge_m3s / self._area_m2

    def advance_to(self, time_s: float) -> float:
        """Advance SFINCS to ``time_s`` and return the time it reached (at least that).

        Raises
        ------
        EngineError
            If SFINCS fails.
        """
        self._bmi.update_until(time_s)
        return self._bmi.current_time()

    def stored_volume_m3(self) -> float:
        """Return the water on the surface now [m3], from the unmasked levels."""
        depth = np.maximum(self._zs - self._zb.astype(np.float64), 0.0)
        return float(depth.sum()) * self._area_m2
