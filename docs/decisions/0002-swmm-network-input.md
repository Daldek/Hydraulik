# ADR-0002: SWMM network from a table or from the user's own input file

- Status: proposed (accepted when the author approves the plan of 2026-10-24)
- Date: 2026-10-24
- Requirements: DEV-11.3, DEV-13.3; extraction note 3, 4 and 7

## Context

The coupling needs a sewer network that SWMM can run and whose nodes have a
position on the SFINCS grid. The feasibility test generated three nodes and a
chain of conduits from code. Real networks come from a survey, QGIS or PCSWMM and
are SWMM input files (`.inp`). The experiment also found that the file must carry
settings that the defaults of SWMM do not have: a fixed routing step of 0.5 s,
`SurDepth` 0 or 100 m by the spill mode, an explicit `MIN_SURFAREA`, local losses
(README 7.2).

## Options considered

| Option | Verdict |
|---|---|
| A. A network table (CSV: one row per node, the downstream node, the diameter) that Hydraulik turns into an input file, and an input file of the user's own that Hydraulik patches and reads | Chosen |
| B. Only generated chains, as in the experiment | Rejected: no real network can be run |
| C. Only the user's input file | Rejected: a small or synthetic network (a test, a teaching case) should need no SWMM installation to write |
| D. Import sewer layers from GIS (shapefile, GeoPackage) into SWMM objects | Rejected for now: layer schemas differ by city; QGIS and PCSWMM already export `.inp` |

## Decision

Option A. `read_network_table` reads the table and `write_inp` writes the file
with the settings of the experiment, including non-zero local losses and an
optional flap gate and stage series at the outfall. For the user's file,
`engines.swmm.inp` reads options, junctions and coordinates and patches the
options and the surcharge depth of the junctions; every other line is untouched.
Only `FLOW_UNITS CMS` is supported (`unsupported`, reason `flow_units`). The
SWMM start date of every run is 2000-01-01 00:00:00, so a model time is the
number of seconds since it, as for SFINCS `tref`.

## Consequences

- A user's file with subcatchments would let SWMM make runoff of its own from
  rain that SFINCS already puts on the surface; the model build warns about it
  (notice `swmm_subcatchments`) and does not remove them.
- The rim of a node in a user's file rarely equals the ground of the DEM. The
  coupler takes the ground from SFINCS and checks the difference against a
  tolerance (`rim_tolerance_m`) instead of requiring equality.
- Which junctions exchange water is explicit: all junctions with coordinates
  inside the active domain, or a list the user gives.

## Errata

None.
