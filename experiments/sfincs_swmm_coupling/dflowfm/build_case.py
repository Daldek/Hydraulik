"""Build the D-Flow FM 1D2D version of the idealised surface-inflow test case.

The 2D grid, bed levels, pipes, manholes and the stepped surface inflow are
taken from ../case_setup.py, so the model mirrors the SFINCS-SWMM Q scenarios.
Only free tools are used: HYDROLIB-core and MeshKernel (both from Deltares, MIT).
Boundary files (.ext, .bc, .pli) are written as plain text, which is simpler
than HYDROLIB-core's validated models for this small case.

Usage: python build_case.py <scenario> <run_dir>
Scenarios: DQ0 (no network), DQ1 (free network), DQ2 (surcharged network),
DQ3 (backwater from the outfall). Append "_inlet" to DQ1-DQ3 to use 1D2D
links of type 'street inlet' (5) instead of the default 'embedded' (3).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import meshkernel as mk
import netCDF4
import numpy as np
from hydrolib.core.dflowfm import (
    CrossDefModel,
    CrossLocModel,
    FMModel,
    IniFieldModel,
    InitialField,
    StorageNodeModel,
)
from hydrolib.core.dflowfm.crosssection.models import CircleCrsDef, CrossSection
from hydrolib.core.dflowfm.net.models import Branch
from hydrolib.core.dflowfm.storagenode.models import StorageNode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import case_setup as cs  # noqa: E402

REFERENCE_DATE = "2026-01-01 00:00:00"
NODE_SPACING_M = 10.0  # 1D computational node spacing along the pipes
STREET_INLET_WIDTH_M = 0.5  # same opening as the SFINCS-SWMM grate (0.5 x 0.5 m)
STREET_INLET_HEIGHT_M = 0.5
FREE_OUTFLOW_DROP_M = 0.1  # downstream water level this far below the lowest bed
CONTACT_TYPE_STREET_INLET = 5

MANHOLES = list(cs.EXCHANGE_NODES_XY)  # J1, J2, J3
# The 1D network lies 0.5 m beside the drainage line, still inside the manhole
# cells: a 1D node exactly on a 2D cell centre gives a zero-length 1D2D link,
# which D-Flow FM silently drops. Levels are taken on the drainage line, as in
# SFINCS-SWMM. The outfall lies 5 m outside the 2D domain, so the 2D outflow
# boundary does not claim the 1D end node.
NETWORK_Y_OFFSET_M = 0.5
OUTFALL_X_M = cs.N_CELLS_X * cs.CELL_SIZE_M + 5.0
PIPES = [("C1", "J1", "J2"), ("C2", "J2", "J3"), ("C3", "J3", "OUT")]

SCENARIO_NETWORK = {
    "DQ1": {"diameters": {"C1": 0.6, "C2": 0.6, "C3": 0.6}, "stage": None},
    "DQ2": {"diameters": cs.BOTTLENECK, "stage": None},
    "DQ3": {
        "diameters": {"C1": 0.6, "C2": 0.6, "C3": 0.6},
        "stage": cs.BACKWATER_STAGE,
    },
}


def level_xy(name: str) -> tuple[float, float]:
    """Point on the drainage line whose surface elevation sets the node levels."""
    if name == "OUT":
        return (OUTFALL_X_M, cs.DRAINAGE_LINE_Y_M)
    return cs.EXCHANGE_NODES_XY[name]


def xy(name: str) -> tuple[float, float]:
    """Position of the node in the 1D network geometry."""
    x, y = level_xy(name)
    return (x, y + NETWORK_Y_OFFSET_M)


def node_id(name: str) -> str:
    """Network node id as HYDROLIB-core generates it ("x_y")."""
    x, y = xy(name)
    return f"{x:.6f}_{y:.6f}"


def invert_m(name: str) -> float:
    x, y = level_xy(name)
    return cs.surface_elevation_m(x, y) - cs.NODE_DEPTH_BELOW_SURFACE_M


def write_bed_samples(path: Path) -> None:
    """Bed level samples on (and one cell beyond) every 2D cell centre."""
    rows = []
    for i in range(-1, cs.N_CELLS_X + 1):
        for j in range(-1, cs.N_CELLS_Y + 1):
            x, y = cs.cell_centre(i), cs.cell_centre(j)
            rows.append(f"{x:.3f} {y:.3f} {cs.surface_elevation_m(x, y):.4f}\n")
    path.write_text("".join(rows))


def write_polyline(path: Path, name: str, points: list[tuple[float, float]]) -> None:
    rows = "".join(f"{x:.3f} {y:.3f}\n" for x, y in points)
    path.write_text(f"{name}\n{len(points)} 2\n{rows}")


def forcing_block(name: str, quantity: str, unit: str, rows) -> str:
    data = "".join(f"{t:.1f} {v:.6f}\n" for t, v in rows)
    return (
        "[forcing]\n"
        f"name              = {name}\n"
        "function          = timeseries\n"
        "timeInterpolation = linear\n"
        "quantity          = time\n"
        f"unit              = seconds since {REFERENCE_DATE}\n"
        f"quantity          = {quantity}\n"
        f"unit              = {unit}\n"
        f"{data}\n"
    )


def boundary_block(quantity: str, location: str) -> str:
    key = "nodeId" if location.endswith(tuple("0123456789")) else "locationFile"
    return (
        "[Boundary]\n"
        f"quantity     = {quantity}\n"
        f"{key:<12} = {location}\n"
        "forcingFile  = boundaries.bc\n\n"
    )


def build(scenario: str, run_dir: Path) -> Path:
    base = scenario.replace("_inlet", "")
    street_inlet = scenario.endswith("_inlet")
    has_network = base in SCENARIO_NETWORK
    run_dir.mkdir(parents=True, exist_ok=True)

    model = FMModel()
    model.filepath = run_dir / "case.mdu"
    model.geometry.netfile.filepath = Path("case_net.nc")
    network = model.geometry.netfile.network
    x_max = cs.N_CELLS_X * cs.CELL_SIZE_M
    y_max = cs.N_CELLS_Y * cs.CELL_SIZE_M
    network.mesh2d_create_rectilinear_within_extent(
        extent=(0.0, 0.0, x_max, y_max), dx=cs.CELL_SIZE_M, dy=cs.CELL_SIZE_M
    )

    # Surface inflow over the full upstream edge. Free outflow at the downstream
    # edge: a water level just below the lowest bed, so water leaves unhindered.
    write_polyline(run_dir / "inflow.pli", "inflow", [(0.0, 0.0), (0.0, y_max)])
    write_polyline(run_dir / "outflow.pli", "outflow", [(x_max, 0.0), (x_max, y_max)])
    boundaries = [
        boundary_block("dischargebnd", "inflow.pli"),
        boundary_block("waterlevelbnd", "outflow.pli"),
    ]
    forcings = [
        forcing_block("inflow_0001", "dischargebnd", "m3/s", cs.INFLOW_HYDROGRAPH_M3S)
    ]
    level = cs.surface_elevation_m(x_max, cs.DRAINAGE_LINE_Y_M) - FREE_OUTFLOW_DROP_M
    constant = [(0.0, level), (cs.SIMULATION_DURATION_S, level)]
    forcings += [
        forcing_block(point, "waterlevelbnd", "m", constant)
        for point in ("outflow_0001", "outflow_0002")
    ]

    if has_network:
        setup = SCENARIO_NETWORK[base]
        definitions, locations = [], []
        for pipe, a, b in PIPES:
            geometry = np.array([xy(a), xy(b)])
            length = float(np.hypot(*(geometry[1] - geometry[0])))
            count = max(2, int(round(length / NODE_SPACING_M)) + 1)
            network.mesh1d_add_branch(
                Branch(
                    geometry=geometry, branch_offsets=np.linspace(0.0, length, count)
                ),
                name=pipe,
            )
            definition = f"circle_{pipe}"
            definitions.append(
                CircleCrsDef(
                    id=definition,
                    diameter=setup["diameters"][pipe],
                    frictiontype="Manning",
                    frictionvalue=cs.PIPE_MANNING_N,
                )
            )
            for end, chainage in ((a, 0.0), (b, length)):
                locations.append(
                    CrossSection(
                        id=f"{pipe}_{end}",
                        branchid=pipe,
                        chainage=chainage,
                        definitionid=definition,
                        shift=invert_m(end),
                    )
                )
        model.geometry.crossdeffile = CrossDefModel(definition=definitions)
        model.geometry.crossdeffile.filepath = Path("crsdef.ini")
        model.geometry.crosslocfile = CrossLocModel(crosssection=locations)
        model.geometry.crosslocfile.filepath = Path("crsloc.ini")

        model.geometry.storagenodefile = StorageNodeModel(
            storagenode=[
                StorageNode(
                    id=name,
                    name=name,
                    manholeid=name,
                    nodeid=node_id(name),
                    usetable=False,
                    bedlevel=invert_m(name),
                    area=cs.NODE_SURFACE_AREA_M2,
                    streetlevel=invert_m(name) + cs.NODE_DEPTH_BELOW_SURFACE_M,
                    storagetype="reservoir",
                    streetstoragearea=cs.NODE_SURFACE_AREA_M2,
                )
                for name in MANHOLES
            ]
        )
        model.geometry.storagenodefile.filepath = Path("nodes.ini")

        boundaries.append(boundary_block("waterlevelbnd", node_id("OUT")))
        invert_out = invert_m("OUT")
        stage = setup["stage"] or [
            (0.0, invert_out),
            (cs.SIMULATION_DURATION_S, invert_out),
        ]
        forcings.append(forcing_block(node_id("OUT"), "waterlevelbnd", "m", stage))

        # One 1D2D link per manhole: manhole node <-> 2D cell containing it.
        mesh1d = network._mesh1d
        mesh1d._set_mesh1d()
        mesh2d = network._mesh2d
        n1d, n2d = [], []
        for name in MANHOLES:
            x, y = xy(name)
            n1d.append(
                int(
                    np.argmin(
                        np.hypot(mesh1d.mesh1d_node_x - x, mesh1d.mesh1d_node_y - y)
                    )
                )
            )
            n2d.append(
                int(
                    np.argmin(
                        np.hypot(mesh2d.mesh2d_face_x - x, mesh2d.mesh2d_face_y - y)
                    )
                )
            )
        network._link1d2d.meshkernel.contacts_set(
            mk.Contacts(np.array(n1d, dtype=np.int32), np.array(n2d, dtype=np.int32))
        )

    model.geometry.bedlevtype = 1  # bed levels at cell centres
    write_bed_samples(run_dir / "bedlevel.xyz")
    model.geometry.inifieldfile = IniFieldModel(
        initial=[
            InitialField(
                quantity="bedlevel",
                datafiletype="sample",
                datafile=Path("bedlevel.xyz"),
                interpolationmethod="triangulation",
            )
        ]
    )
    model.geometry.inifieldfile.filepath = Path("inifields.ini")

    model.time.refdate = 20260101
    model.time.tunit = "S"
    model.time.tstart = 0.0
    model.time.tstop = cs.SIMULATION_DURATION_S
    model.time.dtuser = 10.0
    model.time.dtmax = 1.0
    model.physics.uniffrictcoef = cs.MANNING_N
    model.physics.uniffricttype = 1  # Manning
    model.numerics.epshu = cs.WET_DRY_THRESHOLD_M
    model.output.mapinterval = [10.0]
    model.output.hisinterval = [10.0]
    if street_inlet:
        model.geometry.uniformwidth1dstreetinlets = STREET_INLET_WIDTH_M
        model.geometry.uniformheight1dstreetinlets = STREET_INLET_HEIGHT_M
        model.geometry.uniformtyp1dstreetinlets = -2  # closed rectangle (grate opening)
    model.save(recurse=True)

    (run_dir / "boundaries.ext").write_text("".join(boundaries))
    (run_dir / "boundaries.bc").write_text("".join(forcings))
    mdu = model.filepath.read_text()
    mdu = re.sub(r"(?im)^(extForceFileNew\s*=).*$", r"\1 boundaries.ext", mdu)
    # HYDROLIB-core 1.5.0 still writes keywords that the current kernel rejects.
    mdu = re.sub(r"(?im)^\s*(qhrelax|wrishp_enc)\s*=.*\n", "", mdu)
    model.filepath.write_text(mdu)

    if has_network and street_inlet:
        with netCDF4.Dataset(run_dir / "case_net.nc", "a") as dataset:
            for name, variable in dataset.variables.items():
                if name.endswith("contact_type"):
                    variable[:] = CONTACT_TYPE_STREET_INLET
    return model.filepath


if __name__ == "__main__":
    print(build(sys.argv[1], Path(sys.argv[2]).resolve()))
