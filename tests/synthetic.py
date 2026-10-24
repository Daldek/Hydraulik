"""Synthetic SFINCS result files and a fake SFINCS program for tests without an engine.

The files follow the layout of the real ones (checked on SFINCS v2.4.1 and ``main``):
``sfincs_map.nc`` has ``n`` (rows from the south) and ``m`` (columns), ``h`` at the
output times unmasked, ``hmax`` masked under ``huthresh``, accumulated ``cumprcp`` and
``cuminf`` on ``timemax``, the grid in ``corner_x`` and ``corner_y``, the CRS in
``crs`` and the input keys in ``inp``; ``sfincs_his.nc`` has ``point_zs`` per station.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import netCDF4
import numpy as np
from numpy.typing import NDArray

from hydraulik.engines.detect import SfincsInstall
from hydraulik.engines.sfincs.model import (
    ModelInputs,
    RegularGrid,
    precip_breakpoints,
)

Float = NDArray[np.float64]

FILL = -99999.0


def write_map(
    path: Path,
    *,
    rows: int = 4,
    columns: int = 5,
    x0: float = 1000.0,
    y0: float = 2000.0,
    dx: float = 10.0,
    epsg: int = 2180,
    active: NDArray[np.bool_] | None = None,
    outflow: NDArray[np.bool_] | None = None,
    bed: Float | None = None,
    depth: Float | None = None,
    rain_m: Float | float = 0.03,
    infiltration_m: Float | float = 0.01,
    huthresh: float = 0.05,
    end_time_s: float = 7200.0,
    depth_time_s: float = 7200.0,
    status: float | None = 0.0,
    with_accumulated: bool = True,
    revision: str = "$Rev: v2.4.1 Galibier+",
) -> None:
    """Write a regular-grid ``sfincs_map.nc`` with two output frames.

    ``depth`` is the water depth of the last frame [m] (the first frame is dry);
    ``hmax`` equals it and is masked under ``huthresh``; ``rain_m`` and
    ``infiltration_m`` fill ``cumprcp`` and ``cuminf`` (a scalar or an array).
    """
    shape = (rows, columns)
    mask = np.ones(shape, dtype=np.int32) if active is None else active.astype(np.int32)
    if outflow is not None:
        mask[outflow] = 3
    bed_m = np.zeros(shape) if bed is None else bed
    depth_m = np.zeros(shape) if depth is None else depth
    with netCDF4.Dataset(path, "w") as ds:
        ds.setncattr("Build-Revision", revision)
        ds.createDimension("n", rows)
        ds.createDimension("m", columns)
        ds.createDimension("corner_n", rows + 1)
        ds.createDimension("corner_m", columns + 1)
        ds.createDimension("time", 2)
        ds.createDimension("timemax", 1)
        ds.createDimension("runtime", 1)
        cx, cy = np.meshgrid(
            x0 + dx * np.arange(columns + 1), y0 + dx * np.arange(rows + 1)
        )
        for name, values in (("corner_x", cx), ("corner_y", cy)):
            var = ds.createVariable(name, "f4", ("corner_n", "corner_m"))
            var[:] = values
        crs = ds.createVariable("crs", "i4", ())
        crs.setncattr("epsg", np.int32(epsg))
        inp = ds.createVariable("inp", "i4", ())
        inp.setncattr("huthresh", np.float32(huthresh))
        ds.createVariable("msk", "i4", ("n", "m"), fill_value=-999)[:] = mask
        zb = ds.createVariable("zb", "f4", ("n", "m"), fill_value=FILL)
        zb[:] = np.ma.masked_where(mask == 0, bed_m)
        ds.createVariable("time", "f4", ("time",))[:] = [0.0, depth_time_s]
        h = ds.createVariable("h", "f4", ("time", "n", "m"), fill_value=FILL)
        h[0] = np.ma.masked_where(mask == 0, np.zeros(shape))
        h[1] = np.ma.masked_where(mask == 0, depth_m)
        if with_accumulated:
            ds.createVariable("timemax", "f4", ("timemax",))[:] = [end_time_s]
            for name, values in (
                ("cumprcp", np.broadcast_to(rain_m, shape)),
                ("cuminf", np.broadcast_to(infiltration_m, shape)),
                ("vmax", np.where(depth_m > 0, 0.5, 0.0)),
            ):
                var = ds.createVariable(
                    name, "f4", ("timemax", "n", "m"), fill_value=FILL
                )
                var[0] = np.ma.masked_where(mask == 0, values)
            hmax = ds.createVariable(
                "hmax", "f4", ("timemax", "n", "m"), fill_value=FILL
            )
            hmax[0] = np.ma.masked_where((mask == 0) | (depth_m < huthresh), depth_m)
        if status is not None:
            ds.createVariable("status", "f4", ("runtime",))[:] = [status]
        ds.createVariable("total_runtime", "f4", ("runtime",))[:] = [1.5]
        ds.createVariable("average_dt", "f4", ("runtime",))[:] = [2.5]


def write_his(
    path: Path,
    *,
    names: tuple[str, ...] = ("outlet",),
    x: tuple[float, ...] = (1025.0,),
    y: tuple[float, ...] = (2015.0,),
    bed: tuple[float, ...] = (0.0,),
    times: tuple[float, ...] = (0.0, 600.0, 1200.0),
    level: Float | None = None,
) -> None:
    """Write ``sfincs_his.nc`` with ``point_zs`` of shape ``(time, stations)``."""
    count = len(names)
    series = (
        np.tile(np.array([0.0, 0.02, 0.1]), (count, 1)).T if level is None else level
    )
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("time", len(times))
        ds.createDimension("stations", count)
        ds.createDimension("pointnamelength", 256)
        name_var = ds.createVariable(
            "station_name", "S1", ("stations", "pointnamelength")
        )
        for index, name in enumerate(names):
            padded = name.encode().ljust(256, b"\x00")
            name_var[index, :] = np.frombuffer(padded, dtype="S1")
        ds.createVariable("point_x", "f4", ("stations",))[:] = x
        ds.createVariable("point_y", "f4", ("stations",))[:] = y
        ds.createVariable("point_zb", "f4", ("stations",), fill_value=FILL)[:] = bed
        ds.createVariable("time", "f4", ("time",))[:] = times
        zs = ds.createVariable("point_zs", "f4", ("time", "stations"), fill_value=FILL)
        zs[:] = series


FAKE_SFINCS = textwrap.dedent(
    '''
    """A stand-in for the SFINCS program, driven by files of the model directory."""
    import os
    import shutil
    import sys
    import time
    from pathlib import Path

    mode = Path("mode.txt").read_text().strip() if Path("mode.txt").exists() else "ok"
    if not Path("sfincs.inp").exists() and mode != "hang":
        print('Error   : SFINCS input file "sfincs.inp" not found! SFINCS has stopped!')
        sys.exit(2)
    Path("seen.txt").write_text(
        f"{os.environ.get('OMP_NUM_THREADS', '')}|{os.getcwd()}"
    )
    if mode == "hang":
        time.sleep(60)
    if mode == "fail":
        print(" 0% complete,       - s remaining ...", flush=True)
        print('Error   : Precipitation prcp file "sfincs.precip" not found!')
        sys.exit(2)
    for percent in (0, 50, 100):
        print(f"{percent:3d}% complete,       - s remaining ...", flush=True)
    if mode != "silent":
        shutil.copy(os.environ["FAKE_SFINCS_MAP"], "sfincs_map.nc")
        if os.environ.get("FAKE_SFINCS_HIS"):
            shutil.copy(os.environ["FAKE_SFINCS_HIS"], "sfincs_his.nc")
    Path("sfincs.log").write_text("log of the fake run\\n")
    '''
)

FAKE_DOCKER = textwrap.dedent(
    '''
    """A stand-in for the docker command: records its arguments, optionally hangs."""
    import os
    import sys
    import time
    from pathlib import Path

    log = Path(os.environ["FAKE_DOCKER_LOG"])
    with log.open("a") as stream:
        stream.write(" ".join(sys.argv[1:]) + "\\n")
    if sys.argv[1] == "run":
        if os.environ.get("FAKE_DOCKER_HANG"):
            time.sleep(60)
        print("100% complete,       - s remaining ...", flush=True)
    '''
)


def fake_sfincs(folder: Path) -> SfincsInstall:
    """Write the fake SFINCS program and return the install that runs it."""
    script = folder / "fake_sfincs.py"
    script.write_text(FAKE_SFINCS, encoding="utf-8")
    return SfincsInstall("exe", (sys.executable, str(script)), None, "fake")


def fake_docker(folder: Path) -> SfincsInstall:
    """Write the fake docker command and return the Docker install that runs it."""
    script = folder / "fake_docker.py"
    script.write_text(FAKE_DOCKER, encoding="utf-8")
    return SfincsInstall(
        "docker", (sys.executable, str(script)), "deltares/sfincs-cpu:sfincs-v2.4.1"
    )


def closed_basin() -> ModelInputs:
    """A flat 10 x 10 basin of 10 m cells, 30 mm of rain, CN 80, no outflow."""
    grid = RegularGrid(0.0, 0.0, 10.0, 10, 10)
    return ModelInputs(
        grid=grid,
        elevation_m=np.zeros(grid.shape),
        active=np.ones(grid.shape, dtype=bool),
        precip=precip_breakpoints([5.0] * 6, 600.0, 7200.0),
        tstop_s=7200.0,
        manning=np.full(grid.shape, 0.03),
        curve_number=np.full(grid.shape, 80.0),
        observation_points=((55.0, 55.0, "centre"),),
        dtmax_s=10.0,
        dtout_s=7200.0,
        dthisout_s=600.0,
    )


def slope_with_outflow() -> ModelInputs:
    """A 10 x 10 slope (0.4 %) towards two outflow cells at the south edge, 60 mm."""
    grid = RegularGrid(0.0, 0.0, 10.0, 10, 10)
    rows = np.arange(10)[:, None] * np.ones((1, 10))
    outflow = np.zeros(grid.shape, dtype=bool)
    outflow[0, 4:6] = True
    return ModelInputs(
        grid=grid,
        elevation_m=0.5 + 0.04 * rows,
        active=np.ones(grid.shape, dtype=bool),
        precip=precip_breakpoints([30.0, 30.0], 900.0, 7200.0),
        tstop_s=7200.0,
        outflow=outflow,
        manning=0.04,
        dtmax_s=10.0,
        dtout_s=7200.0,
        observation_points=((55.0, 5.0, "low"),),
    )
