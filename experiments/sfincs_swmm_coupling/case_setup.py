"""Idealised test case for the SFINCS-SWMM coupling feasibility test.

Builds the SFINCS input (regular grid, closed boundaries, uniform block rain)
and the SWMM input (three exchange nodes, conduits, one outfall) for each
scenario. All geometry is defined here, so every number in the results can be
traced back to this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

# --- Domain (SFINCS) --------------------------------------------------------

CELL_SIZE_M = 2.0
N_CELLS_X = 100  # 200 m along the main slope
N_CELLS_Y = 21  # 42 m across; the centre row (y = 21 m) is the drainage line
Z_UPSTREAM_M = 10.0  # surface elevation at x = 0 on the drainage line
SLOPE_LONGITUDINAL = 0.005  # [-] surface falls towards x = 200 m
SLOPE_TRANSVERSE = 0.02  # [-] surface rises away from the drainage line
DRAINAGE_LINE_Y_M = 21.0
MANNING_N = 0.015  # [s/m^(1/3)]
WET_DRY_THRESHOLD_M = 0.001  # SFINCS 'huthresh'; small value for rain-on-grid
SFINCS_ALPHA = 0.5  # CFL factor (SFINCS default)
SFINCS_DTMAX_S = 1.0  # upper bound on the adaptive SFINCS time step

# --- Forcing -----------------------------------------------------------------

SIMULATION_DURATION_S = 3600.0
# Surface inflow alternative to rain: stepped hydrograph, spread evenly over the
# upstream edge (x = 1 m, all rows); 60 s linear ramps between the steps.
INFLOW_HYDROGRAPH_M3S = [
    (0.0, 0.0),
    (60.0, 0.05),
    (1200.0, 0.05),
    (1260.0, 0.10),
    (2400.0, 0.10),
    (2460.0, 0.15),
    (3600.0, 0.15),
]
STEADY_WINDOW_S = 300.0  # last part of each step used for steady-state statistics
RAIN_INTENSITY_MM_H = 60.0
RAIN_DURATION_S = 1200.0

# --- Network (SWMM) ----------------------------------------------------------

NODE_DEPTH_BELOW_SURFACE_M = 2.0
NODE_SURCHARGE_DEPTH_M = 100.0  # large, so SWMM never spills internally
PIPE_MANNING_N = 0.013
SWMM_ROUTING_STEP_S = 1
NODE_SURFACE_AREA_M2 = (
    1.167  # SWMM MIN_SURFAREA (its default, 12.566 ft2), set explicitly
)
OUTFALL_X_M = 200.0

# Exchange nodes lie on cell centres of the drainage line.
EXCHANGE_NODES_XY = {
    "J1": (51.0, DRAINAGE_LINE_Y_M),
    "J2": (101.0, DRAINAGE_LINE_Y_M),
    "J3": (151.0, DRAINAGE_LINE_Y_M),
}


def surface_elevation_m(x_m: float, y_m: float) -> float:
    """Return the surface elevation of the idealised domain at a point."""
    return (
        Z_UPSTREAM_M
        - SLOPE_LONGITUDINAL * x_m
        + SLOPE_TRANSVERSE * abs(y_m - DRAINAGE_LINE_Y_M)
    )


@dataclass
class Scenario:
    """One run of the test matrix.

    Parameters
    ----------
    name : str
        Short identifier, also used as the run directory name.
    description : str
        One-line description used in the report.
    coupled : bool
        True when SWMM is coupled to SFINCS through BMI.
    pipe_diameters_m : dict
        Diameter of every conduit (C1: J1-J2, C2: J2-J3, C3: J3-outfall).
    outfall_stage : list of (time_s, stage_m) or None
        Water level imposed at the outfall; None means a free outfall.
    exchange_interval_s : float
        Interval between data exchanges of the two models.
    conceptual_drainage_mm_h : float or None
        Design rate of SFINCS' built-in urban drainage module (whole grid,
        no outfall); None disables the module.
    surcharge_method : str
        SWMM pressurised-flow method: "EXTRAN" (default) or "SLOT".
    relaxation : float
        Under-relaxation factor w of the exchange discharge,
        Q_k = w * Q_new + (1 - w) * Q_{k-1}; 1.0 means no relaxation.
    equalisation_limiter : bool
        Limit the volume exchanged in one interval to a fraction of the volume
        that would equalise surface level and node head.
    forcing : str
        "rain" (uniform block rain, closed domain) or "inflow" (stepped surface
        inflow at the upstream edge, free outflow measured at the downstream edge).
    swmm_routing_step_s : float
        SWMM routing step; must divide the 1 s stride used by the coupler.
    exchange_law : str
        "continuous" (v2: Rubinato et al. 2017 coefficients, Villemonte
        submergence, linearised orifice) or "legacy" (v1: discontinuous).
    """

    name: str
    description: str
    coupled: bool = False
    pipe_diameters_m: dict = field(
        default_factory=lambda: {"C1": 0.6, "C2": 0.6, "C3": 0.6}
    )
    outfall_stage: list | None = None
    exchange_interval_s: float = 1.0
    conceptual_drainage_mm_h: float | None = None
    surcharge_method: str = "EXTRAN"
    relaxation: float = 1.0
    equalisation_limiter: bool = False
    forcing: str = "rain"
    swmm_routing_step_s: float = float(SWMM_ROUTING_STEP_S)
    exchange_law: str = "continuous"


BOTTLENECK = {"C1": 0.3, "C2": 0.3, "C3": 0.15}
BACKWATER_STAGE = [(0.0, 7.0), (1800.0, 7.0), (2700.0, 9.6), (3600.0, 9.6)]


RECOMMENDED_RELAXATION = 0.1

CASES = {
    "S2": {"pipe_diameters_m": BOTTLENECK},
    "S3": {"outfall_stage": BACKWATER_STAGE},
}


def _recommended(**kwargs) -> dict:
    """Settings of the recommended scheme (slot + under-relaxation, 1 s)."""
    return dict(
        coupled=True,
        surcharge_method="SLOT",
        relaxation=RECOMMENDED_RELAXATION,
        **kwargs,
    )


SCENARIOS = {
    s.name: s
    for s in [
        # A. Reference runs without a network.
        Scenario("S0", "SFINCS only, no drainage"),
        Scenario(
            "S0K",
            "SFINCS built-in conceptual drainage (30 mm/h, whole grid)",
            conceptual_drainage_mm_h=30.0,
        ),
        # B. Naive explicit coupling (SWMM defaults: EXTRAN surcharge).
        Scenario("S1", "Coupled, free-flowing network", coupled=True),
        Scenario("S2", "Coupled, surcharged network", coupled=True, **CASES["S2"]),
        Scenario(
            "S3", "Coupled, backwater from the outfall", coupled=True, **CASES["S3"]
        ),
        # C. Stabilisation, one ingredient at a time.
        *[
            Scenario(
                f"{case}_slot",
                f"{case} + SWMM slot method",
                coupled=True,
                surcharge_method="SLOT",
                **extra,
            )
            for case, extra in CASES.items()
        ],
        *[
            Scenario(
                f"{case}_slot_lim",
                f"{case} + slot + equalisation limiter",
                coupled=True,
                surcharge_method="SLOT",
                equalisation_limiter=True,
                **extra,
            )
            for case, extra in CASES.items()
        ],
        # D. Recommended scheme (slot + under-relaxation) and interval sensitivity.
        *[
            Scenario(
                f"{case}_rec_dt{dt}",
                f"{case} + slot + under-relaxation w = {RECOMMENDED_RELAXATION}, "
                f"exchange every {dt} s",
                coupled=True,
                surcharge_method="SLOT",
                relaxation=RECOMMENDED_RELAXATION,
                exchange_interval_s=float(dt),
                **extra,
            )
            for case, extra in CASES.items()
            for dt in (1, 5, 30)
        ],
        # E. Surface inflow instead of rain (stepped steady states).
        Scenario("Q0", "Inflow, no network", forcing="inflow"),
        Scenario(
            "Q1_rec",
            "Inflow, free-flowing network, recommended scheme",
            forcing="inflow",
            **_recommended(),
        ),
        Scenario(
            "Q2_naive",
            "Inflow, surcharged network, naive (EXTRAN)",
            forcing="inflow",
            coupled=True,
            **CASES["S2"],
        ),
        Scenario(
            "Q2_slot",
            "Inflow, surcharged network, slot only",
            forcing="inflow",
            coupled=True,
            surcharge_method="SLOT",
            **CASES["S2"],
        ),
        Scenario(
            "Q2_rec",
            "Inflow, surcharged network, recommended scheme",
            forcing="inflow",
            **_recommended(**CASES["S2"]),
        ),
        Scenario(
            "Q2_rec_dt5",
            "Q2_rec with exchange every 5 s",
            forcing="inflow",
            **_recommended(exchange_interval_s=5.0, **CASES["S2"]),
        ),
        Scenario(
            "Q3_slot",
            "Inflow, backwater, slot only",
            forcing="inflow",
            coupled=True,
            surcharge_method="SLOT",
            **CASES["S3"],
        ),
        Scenario(
            "Q3_rec",
            "Inflow, backwater, recommended scheme",
            forcing="inflow",
            **_recommended(**CASES["S3"]),
        ),
        *[
            Scenario(
                f"Q2_rec_rs{tag}",
                f"Q2_rec with SWMM routing step {step} s",
                forcing="inflow",
                swmm_routing_step_s=step,
                **_recommended(**CASES["S2"]),
            )
            for tag, step in (("05", 0.5), ("025", 0.25))
        ],
        Scenario(
            "S3_slot_w03",
            "S3 + slot + under-relaxation w = 0.3",
            coupled=True,
            surcharge_method="SLOT",
            relaxation=0.3,
            **CASES["S3"],
        ),
    ]
}


# Legacy (v1) exchange law for a subset, to quantify the effect of the
# continuous formulation (v2) that all other scenarios use.
LEGACY_COMPARISON = [
    "S1",
    "S2_slot",
    "S3_slot",
    "S2_rec_dt1",
    "S3_rec_dt1",
    "Q1_rec",
    "Q2_slot",
    "Q2_rec",
    "Q2_rec_rs025",
    "Q3_slot",
    "Q3_rec",
]
for _name in LEGACY_COMPARISON:
    SCENARIOS[f"{_name}_v1"] = replace(
        SCENARIOS[_name],
        name=f"{_name}_v1",
        description=SCENARIOS[_name].description + " [legacy exchange law v1]",
        exchange_law="legacy",
    )


def cell_centre(index: int) -> float:
    """Return the coordinate of a cell centre along one grid axis."""
    return (index + 0.5) * CELL_SIZE_M


def write_sfincs_case(run_dir: Path, scenario: Scenario) -> None:
    """Write sfincs.inp, the elevation and mask grids and the rain series."""
    rows = []
    for j in range(N_CELLS_Y):
        y = cell_centre(j)
        rows.append(
            " ".join(
                f"{surface_elevation_m(cell_centre(i), y):.4f}"
                for i in range(N_CELLS_X)
            )
        )
    (run_dir / "sfincs.dep").write_text("\n".join(rows) + "\n")

    # All cells active (1); no boundary cells, so every edge is closed.
    mask_row = " ".join("1" for _ in range(N_CELLS_X))
    (run_dir / "sfincs.msk").write_text((mask_row + "\n") * N_CELLS_Y)

    if scenario.forcing == "inflow":
        _write_inflow(run_dir)
        rain_lines = {}
    else:
        rain_lines = {"precipfile": "sfincs.prcp"}

    # Block rain; the 1 s ramp at the end is included in the analytical volume.
    rain = [
        (0.0, RAIN_INTENSITY_MM_H),
        (RAIN_DURATION_S, RAIN_INTENSITY_MM_H),
        (RAIN_DURATION_S + 1.0, 0.0),
        (SIMULATION_DURATION_S, 0.0),
    ]
    (run_dir / "sfincs.prcp").write_text("".join(f"{t:.1f} {p:.3f}\n" for t, p in rain))

    lines = {
        "mmax": N_CELLS_X,
        "nmax": N_CELLS_Y,
        "dx": CELL_SIZE_M,
        "dy": CELL_SIZE_M,
        "x0": 0.0,
        "y0": 0.0,
        "rotation": 0.0,
        "tref": "20260101 000000",
        "tstart": "20260101 000000",
        "tstop": "20260101 010000",
        "inputformat": "asc",
        "depfile": "sfincs.dep",
        "mskfile": "sfincs.msk",
        **rain_lines,
        "manning": MANNING_N,
        "huthresh": WET_DRY_THRESHOLD_M,
        "alpha": SFINCS_ALPHA,
        "dtmax": SFINCS_DTMAX_S,
        "outputformat": "net",
        "dtout": 600.0,
        "dtmaxout": SIMULATION_DURATION_S,
        "dthisout": 60.0,
    }
    if scenario.forcing == "inflow":
        lines["srcfile"] = "sfincs.src"
        lines["disfile"] = "sfincs.dis"
    if scenario.conceptual_drainage_mm_h is not None:
        lines["urbfile"] = "sfincs.urb"
        (run_dir / "sfincs.urb").write_text(
            "[[urban_drainage_zone]]\n"
            'name            = "conceptual"\n'
            'type            = "piped_drainage"\n'
            "whole_grid      = true\n"
            f"design_precip   = {scenario.conceptual_drainage_mm_h:.1f}\n"
            "include_outfall = false\n"
        )
    (run_dir / "sfincs.inp").write_text(
        "".join(f"{key:<16}= {value}\n" for key, value in lines.items())
    )


def inflow_points() -> list[tuple[float, float]]:
    """Discharge points on the upstream edge, one per cell row."""
    return [(cell_centre(0), cell_centre(j)) for j in range(N_CELLS_Y)]


def outflow_points() -> list[tuple[float, float]]:
    """Cells of the downstream edge where the coupler removes outflowing water."""
    return [(cell_centre(N_CELLS_X - 1), cell_centre(j)) for j in range(N_CELLS_Y)]


def _write_inflow(run_dir: Path) -> None:
    """Write the SFINCS discharge points and their (equal) discharge series."""
    points = inflow_points()
    (run_dir / "sfincs.src").write_text(
        "".join(f"{x:.2f} {y:.2f} inflow_{j:02d}\n" for j, (x, y) in enumerate(points))
    )
    share = 1.0 / len(points)
    (run_dir / "sfincs.dis").write_text(
        "".join(
            f"{t:.1f} " + " ".join(f"{q * share:.6f}" for _ in points) + "\n"
            for t, q in INFLOW_HYDROGRAPH_M3S
        )
    )


def write_swmm_case(run_dir: Path, scenario: Scenario) -> Path:
    """Write the SWMM input file and return its path."""
    ground = {
        name: surface_elevation_m(x, y) for name, (x, y) in EXCHANGE_NODES_XY.items()
    }
    outfall_invert = (
        surface_elevation_m(OUTFALL_X_M, DRAINAGE_LINE_Y_M) - NODE_DEPTH_BELOW_SURFACE_M
    )

    junctions = "".join(
        f"{name:<6} {ground[name] - NODE_DEPTH_BELOW_SURFACE_M:.4f} "
        f"{NODE_DEPTH_BELOW_SURFACE_M:.2f} 0 {NODE_SURCHARGE_DEPTH_M:.1f} 0\n"
        for name in EXCHANGE_NODES_XY
    )
    if scenario.outfall_stage is None:
        outfall = f"OUT    {outfall_invert:.4f} FREE NO\n"
        timeseries = ""
    else:
        outfall = f"OUT    {outfall_invert:.4f} TIMESERIES STAGE NO\n"
        timeseries = "[TIMESERIES]\n" + "".join(
            f"STAGE 01/01/2026 {int(t // 3600):02d}:{int(t % 3600 // 60):02d}:00 "
            f"{stage:.3f}\n"
            for t, stage in scenario.outfall_stage
        )

    x = {name: xy[0] for name, xy in EXCHANGE_NODES_XY.items()}
    x["OUT"] = OUTFALL_X_M
    links = [("C1", "J1", "J2"), ("C2", "J2", "J3"), ("C3", "J3", "OUT")]
    conduits = "".join(
        f"{c:<4} {a:<4} {b:<4} {x[b] - x[a]:.1f} {PIPE_MANNING_N} 0 0 0 0\n"
        for c, a, b in links
    )
    xsections = "".join(
        f"{c:<4} CIRCULAR {scenario.pipe_diameters_m[c]:.3f} 0 0 0 1\n"
        for c, _, _ in links
    )

    text = f"""[TITLE]
SFINCS-SWMM coupling feasibility test, scenario {scenario.name}

[OPTIONS]
FLOW_UNITS           CMS
INFILTRATION         HORTON
FLOW_ROUTING         DYNWAVE
START_DATE           01/01/2026
START_TIME           00:00:00
REPORT_START_DATE    01/01/2026
REPORT_START_TIME    00:00:00
END_DATE             01/01/2026
END_TIME             01:00:00
REPORT_STEP          00:01:00
WET_STEP             00:00:01
DRY_STEP             00:00:01
ROUTING_STEP         {scenario.swmm_routing_step_s:g}
VARIABLE_STEP        0
ALLOW_PONDING        NO
INERTIAL_DAMPING     PARTIAL
NORMAL_FLOW_LIMITED  BOTH
SURCHARGE_METHOD     {scenario.surcharge_method}
MIN_SURFAREA         {NODE_SURFACE_AREA_M2}

[JUNCTIONS]
;;Name  Invert MaxDepth InitDepth SurDepth Aponded
{junctions}
[OUTFALLS]
;;Name  Invert Type [Stage/Series] Gated
{outfall}
[CONDUITS]
;;Name From To Length Roughness InOffset OutOffset InitFlow MaxFlow
{conduits}
[XSECTIONS]
;;Link Shape Geom1 Geom2 Geom3 Geom4 Barrels
{xsections}
{timeseries}
[REPORT]
NODES ALL
LINKS ALL
"""
    path = run_dir / "network.inp"
    path.write_text(text)
    return path
