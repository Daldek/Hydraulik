"""SFINCS-SWMM model of the A Coruna urban drainage facility (CITEEC).

Laboratory data: Sanudo, Cea, Puertas, Naves, Anta (2023), Experimental dataset
on a large-scale urban drainage physical facility, Zenodo,
doi:10.5281/zenodo.7941067 (CC BY 4.0); described in Sanudo et al. (2024),
Hydrol. Process. 38(1), doi:10.1002/hyp.15068.

The extracted dataset is read from the directory in the environment variable
CORUNA_DATA (subfolders 02_Geometries, 03_Rain_intensity_maps,
04_Digital_Elevation_Models, 06_Hydraulic_tests_database).

Model set-up (what is taken from the data and what is assumed):

- Surface: street + pavement DEM (SURFACE.asc, 5 cm). Roofs are left out:
  they drain through gutters straight to the manholes, so they do not take
  part in the surface-network exchange. Their records in the block tests are
  not usable as model input (in T01-T03 the roof discharge lasts ~115 s of a
  240 s rain and holds ~45% of the rain on the roofs; T06-T12 have none), so
  the measured outfall is compared only where no roof water reaches it: the
  steady runoff-generator flow before the rain in T07-T12.
- Inlets: the four 0.5 x 0.2 m grates and the 2.5 x 0.13 m transverse grate
  (outlines from surface_geometry_input_Iber.shp). Each grate exchanges water
  with the SFINCS cells inside its outline ("footprint").
- Sewer: nodes and conduits as in the authors' SWMM layers
  (ud_network_SWMM_*.shp), free outfall.
- Rain: hyetographs H1-H6 read from Fig. 2 of 05_Experimental_procedure.pdf.
  The database does not state when the rain starts; RAIN_START_S is estimated
  from the measured response (rise and fall of the inlet discharges).
- Runoff generators SD1/SD2 (tests T07-T12): 1 L/s each, spread across the
  upstream end of the main road and of the side road (positions from Fig. 2 of
  01_Physical_model_description.pdf, the exact devices are not described).

Measured discharges are stored in L/s although the column names say m3/s
(a volume check against the rain maps rules out m3/s).
"""

from __future__ import annotations

import math
import os
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Data location
# ---------------------------------------------------------------------------


def data_dir() -> Path:
    path = os.environ.get("CORUNA_DATA")
    if not path:
        raise RuntimeError(
            "Set CORUNA_DATA to the extracted Zenodo 7941067 dataset directory"
        )
    return Path(path)


# ---------------------------------------------------------------------------
# Geometry (local facility coordinates, metres)
# ---------------------------------------------------------------------------

# Street and pavements (surface_geometry_input_Iber.shp, layers STREET and
# PAVEMENT) as a union of boxes (x_min, x_max, y_min, y_max); roofs excluded.
SURFACE_BOXES = [
    (-7.495, 7.519, -1.250, 1.260),  # main road
    (-7.327, 7.519, -1.475, 1.475),  # main road with both pavements
    (-0.419, 2.919, -2.932, -1.250),  # side road with its pavements
    (0.043, 2.543, -3.100, -2.932),  # upstream end of the side road
]

# Grates (x_min, x_max, y_min, y_max) and the manhole each one drains into
# (Table 2 of 01_Physical_model_description.pdf).
INLETS = {
    "IN1": ((-6.014, -5.514, 1.035, 1.235), "MH_1"),
    "IN2": ((-2.132, -1.632, 1.035, 1.235), "MH_2"),
    "IN3": ((1.635, 2.135, 1.035, 1.235), "MH_3"),
    "IN4": ((5.491, 5.991, 1.035, 1.235), "MH_4"),
    "IN5": ((7.306, 7.436, -1.250, 1.260), "MH_4"),
}

# SWMM layers of the dataset: junction (invert, max depth), conduit
# (from, to, length, Manning n, inlet offset, outlet offset, diameter).
JUNCTIONS = {
    "MH_1": (1.596, 1.213),
    "MH_2": (1.566, 1.195),
    "MH_3": (1.545, 1.185),
    "MH_4": (1.536, 1.162),
    "PI_1": (1.612, 0.0),
    "PI_2": (1.638, 0.0),
}
OUTFALL_INVERT_M = 1.519
CONDUITS = {
    "1.1": ("PI_1", "MH_1", 2.22, 0.005, 0.0, 0.0, 0.240),
    "1.2": ("MH_1", "MH_2", 3.88, 0.005, 0.0, 0.0, 0.240),
    "1.3": ("MH_2", "MH_3", 3.77, 0.005, 0.0, 0.0, 0.240),
    "1.4": ("MH_3", "MH_4", 3.84, 0.005, 0.0, 0.0, 0.240),
    "1.5": ("MH_4", "OUT", 2.41, 0.005, 0.0, 0.0, 0.240),
    "2": ("PI_2", "MH_3", 3.92, 0.005, 0.0, 0.082, 0.194),
}
OUTFALL_CONDUIT = "1.5"
MANHOLE_SURFACE_AREA_M2 = 0.1  # SWMM MIN_SURFAREA (small laboratory manholes)

# Runoff generators: 1 L/s each, spread over points across the road width.
RUNOFF_GENERATOR_M3S = 0.001
SOURCE_POINTS = {
    "SD1": [(-7.47, y) for y in np.arange(-1.125, 1.2, 0.25)],
    "SD2": [(x, -3.075) for x in np.arange(0.168, 2.45, 0.25)],
}

# ---------------------------------------------------------------------------
# Rain and tests
# ---------------------------------------------------------------------------

# Hyetographs: (start offset s, duration s, intensity mm/h), Fig. 2 of the
# experimental procedure. H6 block widths read from the figure (+-5 s).
HYETOGRAPHS = {
    "H1": [(0.0, 240.0, 30.0)],
    "H2": [(0.0, 240.0, 50.0)],
    "H3": [(0.0, 240.0, 80.0)],
    "H4": [(0.0, 15.0, 30.0), (60.0, 15.0, 50.0), (120.0, 15.0, 80.0)],
    "H5": [(0.0, 15.0, 50.0), (60.0, 30.0, 50.0), (135.0, 45.0, 50.0)],
    "H6": [
        (0.0, 30.0, 30.0),
        (30.0, 30.0, 50.0),
        (60.0, 60.0, 80.0),
        (120.0, 30.0, 50.0),
        (150.0, 30.0, 30.0),
    ],
}
RAIN_START_S = 130.0  # estimated from the measured response, see module doc
RAIN_RAMP_S = 0.1  # SFINCS interpolates rain linearly between series points

TEST_DURATION_S = 600.0  # length of every measured record
SPINUP_S = 300.0  # model time before the record starts (steady SD1/SD2 flow)

TESTS = {
    f"T{i:02d}": (
        f"T{i:02d}_exp_post_block_{'wet' if i <= 6 else 'runoff'}_H{(i - 1) % 6 + 1}",
        f"H{(i - 1) % 6 + 1}",
        i > 6,
    )
    for i in range(1, 13)
}

# ---------------------------------------------------------------------------
# Exchange law
# ---------------------------------------------------------------------------

GRAVITY = 9.81
# Same continuous law as the feasibility test (Rubinato et al. 2017
# coefficients), referenced to the grate outline: weir length = grate
# perimeter, orifice area = grate area.
WEIR_COEFFICIENT = 0.54  # Q = 2/3 * Cw * P * h^1.5 * sqrt(2g)
ORIFICE_COEFFICIENT = 0.167  # Q = Co * A * sqrt(2g * h)


@dataclass(frozen=True)
class Config:
    """One model run: a laboratory test and the model options."""

    name: str
    test: str
    cell_size_m: float = 0.05
    manning_n: float = 0.016
    wet_threshold_m: float = 0.0001  # SFINCS huthresh
    inlet_coefficient_scale: float = 1.0
    inlet_depth: str = "mean"  # depth over the grate: footprint "mean" or "max"
    rain: str = "uniform"  # "uniform" (SFINCS precip) or "map" (measured map)
    exchange_interval_s: float = 0.2
    sfincs_dtmax_s: float = 0.2
    swmm_routing_step_s: float = 0.5

    @property
    def hyetograph(self) -> str:
        return TESTS[self.test][1]

    @property
    def runoff(self) -> bool:
        return TESTS[self.test][2]


# Uncalibrated runs: the exchange law with the coefficients of the
# feasibility test (scale 1).
BASE_RUNS = {test: Config(name=test, test=test) for test in TESTS}

# Calibration of the single inlet parameter (scale of both coefficients) on
# the steady runoff-generator flow before the rain (T07; T07-T12 repeat the
# same steady state and give its measurement spread). Target: the mean flows
# of IN1-IN4 and IN5 = outfall - (IN1 + ... + IN4), minimum RMSE.
CALIBRATION_SCALES = (0.5, 0.3, 0.2, 0.15, 0.1, 0.07, 0.05)
CALIBRATION_RUNS = {
    f"cal_{scale:g}": Config(
        name=f"cal_{scale:g}", test="T07", inlet_coefficient_scale=scale
    )
    for scale in CALIBRATION_SCALES
}
CALIBRATED_SCALE = 0.07  # result of the scan (results/calibration.md)

CALIBRATED_RUNS = {
    f"C_{test}": Config(
        name=f"C_{test}", test=test, inlet_coefficient_scale=CALIBRATED_SCALE
    )
    for test in TESTS
}


def _sensitivity(test: str) -> dict[str, Config]:
    base = CALIBRATED_RUNS[f"C_{test}"]
    variants = {
        "dx10": {"cell_size_m": 0.10},
        "n012": {"manning_n": 0.012},
        "n020": {"manning_n": 0.020},
        "hmax": {"inlet_depth": "max"},
        "hu1mm": {"wet_threshold_m": 0.001},
        "rainmap": {"rain": "map"},
        "dtx1": {"exchange_interval_s": 1.0, "sfincs_dtmax_s": 1.0},
    }
    return {
        f"C_{test}_{key}": replace(base, name=f"C_{test}_{key}", **changes)
        for key, changes in variants.items()
    }


SENSITIVITY_RUNS = {**_sensitivity("T03"), **_sensitivity("T09")}
RUNS = {**BASE_RUNS, **CALIBRATION_RUNS, **CALIBRATED_RUNS, **SENSITIVITY_RUNS}


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


@dataclass
class Grid:
    """Regular SFINCS grid; row 0 is the southern row (as SFINCS reads it)."""

    x0: float
    y0: float
    cell_size: float
    bed: np.ndarray  # (rows, cols), NaN outside the surface
    active: np.ndarray  # bool (rows, cols)

    @property
    def shape(self) -> tuple[int, int]:
        return self.bed.shape

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        rows, cols = self.shape
        xc = self.x0 + self.cell_size * (np.arange(cols) + 0.5)
        yc = self.y0 + self.cell_size * (np.arange(rows) + 0.5)
        return np.meshgrid(xc, yc)

    def cells_in_box(self, box) -> list[tuple[float, float]]:
        """Centres of the active cells whose centre lies inside the box."""
        x_min, x_max, y_min, y_max = box
        x, y = self.centres()
        inside = (x >= x_min) & (x <= x_max) & (y >= y_min) & (y <= y_max)
        inside &= self.active
        return list(zip(x[inside], y[inside]))


def read_ascii_grid(path: Path) -> tuple[dict, np.ndarray]:
    """ESRI ASCII grid as (header, array with NaN for no-data, row 0 = south)."""
    header = {}
    with path.open() as handle:
        for _ in range(6):
            key, value = handle.readline().split()
            header[key.lower()] = float(value)
    values = np.loadtxt(path, skiprows=6)
    values = np.where(values == header["nodata_value"], np.nan, values)
    return header, values[::-1]


def build_grid(cell_size_m: float) -> Grid:
    """Surface DEM on the model grid (block mean of the 5 cm DEM if coarser)."""
    header, dem = read_ascii_grid(
        data_dir() / "04_Digital_Elevation_Models" / "SURFACE.asc"
    )
    factor = round(cell_size_m / header["cellsize"])
    if factor < 1 or abs(factor * header["cellsize"] - cell_size_m) > 1e-9:
        raise ValueError("cell size must be a multiple of the 5 cm DEM")
    rows, cols = (s // factor * factor for s in dem.shape)
    blocks = dem[:rows, :cols].reshape(rows // factor, factor, cols // factor, factor)
    bed = blocks.mean(axis=(1, 3))  # NaN if any 5 cm cell is missing
    grid = Grid(
        x0=header["xllcorner"],
        y0=header["yllcorner"],
        cell_size=cell_size_m,
        bed=bed,
        active=np.zeros(bed.shape, dtype=bool),
    )
    x, y = grid.centres()
    inside = np.zeros(bed.shape, dtype=bool)
    for x_min, x_max, y_min, y_max in SURFACE_BOXES:
        inside |= (x >= x_min) & (x <= x_max) & (y >= y_min) & (y <= y_max)
    grid.active = inside & np.isfinite(bed)
    grid.bed = np.where(grid.active, bed, np.nan)
    return grid


# ---------------------------------------------------------------------------
# Forcing
# ---------------------------------------------------------------------------


def rain_blocks(config: Config) -> list[tuple[float, float, float]]:
    """Rain blocks (start, end, mm/h) in model time."""
    start = SPINUP_S + RAIN_START_S
    return [
        (start + offset, start + offset + duration, intensity)
        for offset, duration, intensity in HYETOGRAPHS[config.hyetograph]
    ]


def rain_intensity_mm_h(config: Config, t_s: float) -> float:
    """Nominal rain intensity at model time t (step function)."""
    for t0, t1, intensity in rain_blocks(config):
        if t0 <= t_s < t1:
            return intensity
    return 0.0


def rain_series(config: Config) -> list[tuple[float, float]]:
    """Piecewise-linear rain series for SFINCS: steps with short ramps."""
    end = SPINUP_S + TEST_DURATION_S
    changes = sorted({t for block in rain_blocks(config) for t in block[:2]})
    points = [(0.0, 0.0)]
    for t in changes:
        before = rain_intensity_mm_h(config, t - 1e-6)
        after = rain_intensity_mm_h(config, t + 1e-6)
        points += [(t, before), (t + RAIN_RAMP_S, after)]
    points.append((end, rain_intensity_mm_h(config, end)))
    return points


def series_integral(points: list[tuple[float, float]], t_s: float) -> float:
    """Integral of a piecewise-linear series from 0 to t."""
    total = 0.0
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t_s <= t0:
            break
        t_upper = min(t_s, t1)
        v_upper = v0 + (v1 - v0) * (t_upper - t0) / (t1 - t0)
        total += 0.5 * (v0 + v_upper) * (t_upper - t0)
    return total


def rain_map_mm_h(grid: Grid, intensity: float) -> np.ndarray:
    """Measured rain map of one nominal intensity on the model grid (>= 0)."""
    header, values = read_ascii_grid(
        data_dir() / "03_Rain_intensity_maps" / f"rain_intensity_{intensity:g}mmh.asc"
    )
    x, y = grid.centres()
    col = np.floor((x - header["xllcorner"]) / header["cellsize"]).astype(int)
    row = np.floor((y - header["yllcorner"]) / header["cellsize"]).astype(int)
    rows, cols = values.shape
    inside = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
    sampled = np.full(grid.shape, np.nan)
    sampled[inside] = values[row[inside], col[inside]]
    # Cells outside the map (edges of the side road) get the nominal intensity.
    sampled = np.where(np.isfinite(sampled), sampled, intensity)
    return np.maximum(sampled, 0.0)


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def load_measurements(test: str) -> dict[str, np.ndarray]:
    """Measured series of one test; discharges converted from L/s to m3/s."""
    table = TESTS[test][0]
    path = data_dir() / "06_Hydraulic_tests_database" / "experimental_database.db"
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        columns = [r[1] for r in connection.execute(f'pragma table_info("{table}")')]
        rows = connection.execute(f'select * from "{table}"').fetchall()
    values = np.array(rows, dtype=float)
    data = {}
    for index, column in enumerate(columns):
        series = values[:, index]
        if column.endswith("[m3/s]"):
            series = series / 1000.0  # stored in L/s
        data[column] = series
    return data


def depth_gauges() -> dict[str, tuple[float, float]]:
    """Surface depth gauges: database column -> (x, y)."""
    path = data_dir() / "06_Hydraulic_tests_database" / "measuring_points_info.csv"
    gauges = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        fields = line.split(";")
        if fields[1] == "Depth" and fields[2] == "Surface":
            number = int(fields[0][3:])
            gauges[f"d_gauge_{number:02d}[m]"] = (float(fields[3]), float(fields[4]))
    return gauges


# ---------------------------------------------------------------------------
# Input files
# ---------------------------------------------------------------------------


def write_sfincs_case(run_dir: Path, config: Config, grid: Grid) -> None:
    """sfincs.inp, bed and mask grids, rain series and runoff sources."""
    rows, cols = grid.shape
    bed = np.where(grid.active, grid.bed, 10.0)
    (run_dir / "sfincs.dep").write_text(
        "\n".join(" ".join(f"{v:.4f}" for v in row) for row in bed) + "\n"
    )
    (run_dir / "sfincs.msk").write_text(
        "\n".join(" ".join("1" if a else "0" for a in row) for row in grid.active)
        + "\n"
    )
    end = SPINUP_S + TEST_DURATION_S
    lines = {
        "mmax": cols,
        "nmax": rows,
        "dx": grid.cell_size,
        "dy": grid.cell_size,
        "x0": grid.x0,
        "y0": grid.y0,
        "rotation": 0.0,
        "tref": "20260101 000000",
        "tstart": "20260101 000000",
        "tstop": f"20260101 00{int(end // 60):02d}{int(end % 60):02d}",
        "inputformat": "asc",
        "depfile": "sfincs.dep",
        "mskfile": "sfincs.msk",
        "manning": config.manning_n,
        "huthresh": config.wet_threshold_m,
        "alpha": 0.5,
        "dtmax": config.sfincs_dtmax_s,
        "outputformat": "net",
        "dtout": end,
        "dtmaxout": end,
        "dthisout": end,
    }
    if config.rain == "uniform":
        lines["precipfile"] = "sfincs.prcp"
        (run_dir / "sfincs.prcp").write_text(
            "".join(f"{t:.2f} {p:.3f}\n" for t, p in rain_series(config))
        )
    if config.runoff:
        points = [p for name in SOURCE_POINTS for p in SOURCE_POINTS[name]]
        lines["srcfile"] = "sfincs.src"
        lines["disfile"] = "sfincs.dis"
        (run_dir / "sfincs.src").write_text(
            "".join(f"{x:.3f} {y:.3f} sd_{i:02d}\n" for i, (x, y) in enumerate(points))
        )
        q = RUNOFF_GENERATOR_M3S / len(SOURCE_POINTS["SD1"])
        row = " ".join(f"{q:.7f}" for _ in points)
        (run_dir / "sfincs.dis").write_text(f"0.0 {row}\n{end:.1f} {row}\n")
    (run_dir / "sfincs.inp").write_text(
        "".join(f"{key:<16}= {value}\n" for key, value in lines.items())
    )


def runoff_volume_m3(config: Config, t_s: float) -> float:
    """Volume injected by the runoff generators up to model time t."""
    if not config.runoff:
        return 0.0
    return 2 * RUNOFF_GENERATOR_M3S * t_s


def write_swmm_case(run_dir: Path, config: Config) -> Path:
    """SWMM input: dataset network, free outfall, EXTRAN with SurDepth = 0."""
    end = SPINUP_S + TEST_DURATION_S
    junctions = "".join(
        f"{name:<6} {invert:.3f} {depth:.3f} 0 0 0\n"
        for name, (invert, depth) in JUNCTIONS.items()
    )
    conduits = "".join(
        f"{name:<4} {a:<5} {b:<5} {length:.2f} {n:.3f} {off_in:.3f} {off_out:.3f} 0 0\n"
        for name, (a, b, length, n, off_in, off_out, _) in CONDUITS.items()
    )
    xsections = "".join(
        f"{name:<4} CIRCULAR {d:.3f} 0 0 0 1\n"
        for name, (*_, d) in CONDUITS.items()
    )
    text = f"""[TITLE]
A Coruna urban drainage facility, run {config.name}

[OPTIONS]
FLOW_UNITS           CMS
INFILTRATION         HORTON
FLOW_ROUTING         DYNWAVE
START_DATE           01/01/2026
START_TIME           00:00:00
REPORT_START_DATE    01/01/2026
REPORT_START_TIME    00:00:00
END_DATE             01/01/2026
END_TIME             00:{int(end // 60):02d}:{int(end % 60):02d}
REPORT_STEP          00:00:10
WET_STEP             00:00:01
DRY_STEP             00:00:01
ROUTING_STEP         {config.swmm_routing_step_s:g}
VARIABLE_STEP        0
ALLOW_PONDING        NO
INERTIAL_DAMPING     PARTIAL
NORMAL_FLOW_LIMITED  BOTH
SURCHARGE_METHOD     EXTRAN
MIN_SURFAREA         {MANHOLE_SURFACE_AREA_M2}

[JUNCTIONS]
;;Name  Invert MaxDepth InitDepth SurDepth Aponded
{junctions}
[OUTFALLS]
;;Name  Invert Type Gated
OUT    {OUTFALL_INVERT_M:.3f} FREE NO

[CONDUITS]
;;Name From To Length Roughness InOffset OutOffset InitFlow MaxFlow
{conduits}
[XSECTIONS]
;;Link Shape Geom1 Geom2 Geom3 Geom4 Barrels
{xsections}
[REPORT]
NODES ALL
LINKS ALL
"""
    path = run_dir / "network.inp"
    path.write_text(text)
    return path


def inlet_discharge(
    depth_m: float, head_m: float, ground_m: float, box, scale: float
) -> float:
    """Free inflow through a grate [m3/s]: min(weir, orifice), no spill.

    The weir runs along the grate perimeter, the orifice is the grate area.
    The head of the manhole matters only once it reaches the grate (it never
    does in these tests: the pipes run far below capacity); then the inflow
    is reduced with the Villemonte factor as in the feasibility test.
    """
    if depth_m <= 0.0:
        return 0.0
    x_min, x_max, y_min, y_max = box
    perimeter = 2.0 * ((x_max - x_min) + (y_max - y_min))
    area = (x_max - x_min) * (y_max - y_min)
    weir = (
        2.0
        / 3.0
        * WEIR_COEFFICIENT
        * scale
        * perimeter
        * depth_m**1.5
        * math.sqrt(2.0 * GRAVITY)
    )
    submergence = head_m - ground_m
    if submergence > 0.0:
        weir *= max(1.0 - min(submergence / depth_m, 1.0) ** 1.5, 0.0) ** 0.385
    orifice = ORIFICE_COEFFICIENT * scale * area * math.sqrt(2.0 * GRAVITY * depth_m)
    return min(weir, orifice)
