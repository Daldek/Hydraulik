# ADR-0004: Write the regular-grid SFINCS model ourselves, without hydromt_sfincs

- Status: accepted (the plan of 2026-10-24 was approved by delegation on that day)
- Date: 2026-10-24
- Requirements: ECO-041, DEV-13.5, DEV-6.4, DEV-6.5; extraction note 2, 4 and 5

## Context

The proof of concept builds models with `hydromt_sfincs` 2.0.0rc3 (GPL-3.0, about
90 more packages, a release candidate whose API changes, and a defect that smears
walls and Manning classes, upstream issue 425). The author's decisions say
`hydromt_sfincs` stays behind one adapter and is an optional extra, and that code is
written from the algorithms, never copied from GPL code. The input formats of SFINCS
are small and were read in the sources of v2.4.1.

## Options considered

| Option | Verdict |
|---|---|
| A. An own writer for the regular-grid model; formats checked against the SFINCS sources and a real run | Chosen |
| B. `hydromt_sfincs` as a hard dependency, as in the proof of concept | Rejected: GPL-3.0 in every install, a heavy and unstable stack |
| C. `hydromt_sfincs` as an optional extra with one adapter, later, for subgrid tables | Kept open: no author decision yet (PROGRESS) |
| D. Call `hydromt build sfincs` as a program | Rejected: the same licence question and no control of the files |

## Decision

Option A (`hydraulik.engines.sfincs.model`). Binary input mode, checked in
`sfincs_input.f90`, `sfincs_domain.f90` and `sfincs_infiltration.f90` of v2.4.1:
`sfincs.ind` (int32 count, then 1-based cell indices, column-major), and per active
cell `sfincs.msk` (int8; 1 active, 3 outflow), `sfincs.dep`, `sfincs.man` and
`sfincs.scs` (float32; `S = 1000/CN - 10` in inches). The rain file always ends with
a flat segment that reaches `tstop`, because SFINCS extrapolates the last segment.
Arrays are `(rows, columns)` with row 0 at the south. `storecumprcp = 1` is always
set. The writer ran on the real engine, v2.4.1 and `main`, in the live test: the
closed basin infiltrates and stores what the SCS equation says to within 0.05 mm.

## Consequences

- Regular grids only: no subgrid tables, no quadtree, no rotation. Resolution is the
  cell size, so a 1 m terrain must be averaged to the cell (`dx_m`).
- SFINCS masks water shallower than `huthresh` in the map output, so the stored
  volume of a run that is not coupled is not fully visible; the result reader reports
  the balance with that caveat (the coupler reads the unmasked arrays through the BMI).
- If the author chooses option C, an ADR amends this one and the adapter becomes the
  only importer of `hydromt_sfincs`.

## Errata

None.
