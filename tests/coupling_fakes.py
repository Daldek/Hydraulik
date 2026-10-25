"""Fakes for the coupling loop: a row of dry cells, a tank network, a stand-in BMI.

They are small and exact so that a test can say what the loop must do: the cells are
independent squares along the x axis (cell ``i`` spans ``i * cell_m`` to
``(i + 1) * cell_m``), a step of the surface takes ``step_s`` whatever the target, so
it overshoots as SFINCS does,
and a clipped level is counted as water created, as SFINCS creates it.
"""

from __future__ import annotations

import ctypes
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


class FakeSurface:
    """A row of independent cells with rain, an external source and a fixed step."""

    def __init__(
        self,
        beds: Sequence[float],
        *,
        cell_m: float = 10.0,
        rain_mm_h: float = 0.0,
        depth_m: float = 0.0,
        end_s: float = 300.0,
        step_s: float = 3.0,
        max_step_s: float | None = None,
    ) -> None:
        self.beds = list(beds)
        self.levels = [bed + depth_m for bed in beds]
        self.cell_m = cell_m
        self.area = cell_m * cell_m
        self.time = 0.0
        self.end = end_s
        self.step_s = step_s
        self._max_step_s = step_s if max_step_s is None else max_step_s
        self.rain_rate = rain_mm_h / 1000.0 / 3600.0
        self.sources = [0.0] * len(beds)
        self.rain_m3 = 0.0
        self.created_m3 = 0.0
        self.calls: list[float] = []

    @property
    def time_s(self) -> float:
        return self.time

    @property
    def end_s(self) -> float:
        return self.end

    @property
    def max_step_s(self) -> float:
        return self._max_step_s

    def locate(self, x_m: float, y_m: float) -> int | None:
        index = int(x_m // self.cell_m)
        if x_m >= 0 and 0 <= y_m < self.cell_m and index < len(self.beds):
            return index
        return None

    def bed_m(self, cell: int) -> float:
        return self.beds[cell]

    def level_m(self, cell: int) -> float:
        return self.levels[cell]

    def area_m2(self, cell: int) -> float:
        return self.area

    def set_source_m3s(self, cell: int, discharge_m3s: float) -> None:
        self.sources[cell] = discharge_m3s

    def advance_to(self, time_s: float) -> float:
        self.calls.append(time_s)
        while True:  # a target in the past still runs one step, as in SFINCS
            dt = self.step_s
            for cell, bed in enumerate(self.beds):
                level = self.levels[cell] + self.rain_rate * dt
                level += self.sources[cell] * dt / self.area
                if level < bed:
                    self.created_m3 += (bed - level) * self.area
                    level = bed
                self.levels[cell] = level
            self.rain_m3 += self.rain_rate * dt * self.area * len(self.beds)
            self.time += dt
            if self.time >= time_s - 1e-9:
                return self.time

    def stored_volume_m3(self) -> float:
        return sum(
            max(level - bed, 0.0) * self.area
            for level, bed in zip(self.levels, self.beds, strict=True)
        )


class FakeNetwork:
    """Tanks that drain through the outfall at a fixed capacity and flood at the rim.

    ``flooding`` is SWMM's behaviour with no surcharge depth: what rises above the rim
    leaves the tank as flooding. The outfall flow is the capacity while water is left.
    """

    def __init__(
        self,
        rims: Mapping[str, float],
        *,
        invert_m: float = 8.0,
        tank_m2: float = 1.0,
        capacity_m3s: float = 0.002,
        initial_m3: float = 0.0,
        flooding: bool = True,
        end_s: float = 300.0,
        stride_s: int = 1,
    ) -> None:
        self.rims = dict(rims)
        self.invert = invert_m
        self.tank = tank_m2
        self.capacity = capacity_m3s
        self.volume = dict.fromkeys(rims, initial_m3)
        self.flooded = dict.fromkeys(rims, 0.0)
        self.inflow = dict.fromkeys(rims, 0.0)
        self.flooding = flooding
        self.end = end_s
        self._stride = stride_s
        self._time = 0.0
        self._outflow = 0.0  # SWMM starts a run with no flow, so does the fake

    @property
    def stride_s(self) -> int:
        return self._stride

    @property
    def time_s(self) -> float:
        return self._time

    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(self.rims)

    def head_m(self, name: str) -> float:
        return self.invert + self.volume[name] / self.tank

    def rim_m(self, name: str) -> float:
        return self.rims[name]

    def add_inflow(self, name: str, discharge_m3s: float) -> None:
        self.inflow[name] = discharge_m3s

    def flooding_volume_m3(self, name: str) -> float:
        return self.flooded[name]

    def outfall_flow_m3s(self) -> float:
        return self._outflow

    def stored_volume_m3(self) -> float:
        return sum(self.volume.values())

    def advance(self) -> bool:
        stride = self._stride
        self._time += stride
        flow_after = 0.0
        for name in self.rims:
            self.volume[name] += self.inflow[name] * stride
            out = 0.5 * (self._outflow + self.capacity) * stride / len(self.rims)
            if self.volume[name] > out:
                self.volume[name] -= out
                flow_after = self.capacity
            else:
                raise AssertionError("the fake network ran dry: pick a larger tank")
            full = (self.rims[name] - self.invert) * self.tank
            if self.flooding and self.volume[name] > full:
                self.flooded[name] += self.volume[name] - full
                self.volume[name] = full
        self._outflow = flow_after
        return self._time < self.end - 1e-9


class FakeBmi:
    """A stand-in for :class:`~hydraulik.engines.sfincs.bmi.SfincsBmi` on numpy arrays.

    ``order`` is what ``get_sfincs_cell_index`` answers for any point (1-based in the
    library, 0-based here, as the wrapper returns it), so a test can make the numbering
    differ from the index file.
    """

    last: FakeBmi | None = None

    def __init__(
        self, library: Any, *, positions: dict[tuple[float, float], int] | None = None
    ) -> None:
        self.library = library
        self.positions = positions or {}
        self.zs = np.array([1.0, 2.0, 3.0, 4.0])
        self.zb = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        self.qext = np.zeros(4, dtype=np.float32)
        self.cell_area = 25.0
        self.calls: list[str] = []
        self.time = 0.0
        self.flags: dict[str, bool] = {}
        FakeBmi.last = self

    def initialize(self) -> None:
        self.calls.append("initialize")

    def finalize(self) -> None:
        self.calls.append("finalize")

    def update_until(self, time_s: float) -> None:
        self.calls.append(f"update_until({time_s:g})")
        self.time = time_s + 0.25

    def current_time(self) -> float:
        return self.time

    def end_time(self) -> float:
        return 100.0

    def set_logical(self, name: str, value: bool) -> None:
        self.flags[name] = value

    def array(self, name: str, ctype: Any) -> Any:
        assert ctype in (ctypes.c_double, ctypes.c_float)
        return {"zs": self.zs, "zb": self.zb, "qext": self.qext}[name]

    def cell_index(self, x_m: float, y_m: float) -> int:
        return self.positions[(x_m, y_m)]

    def cell_area_m2(self, position: int) -> float:
        return self.cell_area
