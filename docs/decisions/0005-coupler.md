# ADR-0005: Couple SFINCS and SWMM by exchanging volumes through the BMI, in a process of its own

- Status: accepted (the plan of 2026-10-24 was approved by delegation on that day; the
  coupling stays an optional feature, never a requirement of `model build` or `model run`)
- Date: 2026-10-25
- Requirements: ECO-041, DEV-13.5, DEV-19; extraction note 3, 4, 6 and 7

## Context

SWMM computes the sewer network, SFINCS the surface. Water leaves the street through a
manhole into the network and, when the network surcharges, comes back. The feasibility
test (extraction note 3) coupled the two through the SFINCS BMI and pyswmm and found the
settings that are stable. This ADR records how the package carries that over, and what the
live runs of `model couple` on the real library showed.

## Options considered

| Option | Verdict |
|---|---|
| A. Explicit exchange of volumes every interval, through the SFINCS BMI and pyswmm | Chosen |
| B. An implicit scheme that iterates inside an interval | Rejected: it needs state rollback that neither interface offers |
| C. Exchange through files and restarts | Rejected: no mass guarantee, slow |
| D. The `urban_drainage` module of SFINCS | Rejected: a lumped sink, not a network |
| E. Load `libsfincs` into the process of the command | Rejected: SFINCS keeps its state in global variables, prints to the standard output of its process (it would corrupt `--json`) and a crash would take the caller with it |
| F. Run the coupled simulation in a worker process (`python -m hydraulik.coupling.worker`) with a job file and a result file | Chosen |

## Decision

Options A and F.

- **The loop** (`hydraulik.coupling.coupler`) knows two small protocols, a surface and a
  network, not the engines; the tests drive it with fakes. Every interval `dt_c` (whole
  seconds, a multiple of the 1 s stride of pyswmm) the discharge `Q` from the surface into
  a node is computed from the level of its cell and the head of the node
  (`coupling.laws`), relaxed, and limited to the water that stands in the cell over
  `dt_c + dtmax` (SFINCS clips the level at the bed and would create water); nodes that
  share a cell share one limit. SFINCS is advanced to the end of the interval and
  overshoots by up to one step, so the volume is `V = Q (t_new - t_old)`; SWMM gets
  `V / dt_c` as lateral inflow. Volumes, not rates, are exchanged: the interface adds no
  mass error. `dtmax` is set to at most `dt_c` in the copy of the model in staging.
- **Two ways to spill** (`--mode`): `swmm_flooding` (default) gives the junctions no
  surcharge depth, SWMM floods them and the flooded volume returns to the cell over the
  next interval (EXTRAN, no relaxation); `coordinator` gives them 100 m, so the exchange law
  spills the node itself, with relaxation 0.1 (SLOT, because EXTRAN diverges when the
  network is pressurised). The user's own SWMM input is run with a fixed routing step, the
  clock of the model and the surcharge depth of the mode, and the copy that ran is
  published as `network.inp`.
- **`qext` has two units**: m/s up to v2.4.1, m3/s per cell on `main` since PR 355
  (`sfincs.qext_unit`, `ms` or `m3s`). The library cannot tell which it has, so the water
  balance is the safety net: a wrong unit is a wrong discharge by the cell area, and the
  balance flags it.
- **Cells** are numbered by the index file (`engines.sfincs.layout`): a point is looked up
  there, the library is asked only for a point on an active cell and must agree. Regular,
  unrotated grids in binary input mode only. The rim of a node must lie within
  `--rim-tolerance-m` (default 0.1, a choice of mine) of the bed of its cell.
- **The worker** runs in the staging directory; the parent publishes the files only when
  the worker finished, reads the map, books the water (rain and infiltration from
  `cumprcp` and `cuminf` of the map, the stored water from the unmasked levels of the
  BMI) and flags a residual above 1 %. With outflow cells the residual is the water that
  left; only a gain is an error. Water that SWMM floods out of a node without a cell is
  booked as lost.

## Evidence

Live runs of `model couple` on the local builds of SFINCS v2.4.1 (`ms`) and `main` (`m3s`),
a bowl of 20 x 20 cells of 5 m, 60 mm of rain in 30 min, a manhole with a 0.15 m pipe, one
hour (the pipe takes a fraction of the rain; about 1000 m3 flood out of the node and
return to the cell):

| Run | Total error (percent of the rain) | Remarks |
|---|---|---|
| v2.4.1, `ms`, `dt_c` = 1 s, 3600 intervals | -0.125 | surface side 0.008 m3 (SFINCS alone), network side -0.76 m3 (SWMM's own continuity error, -0.07 %); 24 s |
| `main`, `m3s`, `dt_c` = 5 s | -0.114 | 8.5 s |
| both, coordinator, `w` = 0.1 | +0.25 | SWMM continuity error -2.3 % (SLOT) |
| `main` with `ms` (wrong unit) | -12.1 | flagged `balance_residual` |
| v2.4.1 with `m3s` (wrong unit) | +19.0 | flagged, with an oscillation and a spike notice |

## Consequences

- The coupling is a screening: the description of the inlets moves the exchange by 10 to
  30 % (extraction note 7), and `SLOT` loses 2 to 17 % of the water in pressurised flow.
  A continuity error above 5 %, an oscillation (more than 20 sign changes of the exchange
  of a node) and a head spike above the head held for 10 s are notices.
- It needs a `libsfincs` that the user built (ADR-0003); the weekly live workflow does not
  build one yet, so the live tests run on a machine that has it (`HYDRAULIK_SFINCS_LIBRARY`
  and `HYDRAULIK_SFINCS_QEXT_UNIT`). Only Linux was exercised.
- A model for which `get_sfincs_cell_index` differs from the index file (subgrid, quadtree)
  is refused, not guessed.
