# Decisions

Architecture decision records (DOC §8). Each ADR is a file in
[`decisions/`](decisions/); this table is the index.

| ID | Title | Status | Date |
|---|---|---|---|
| [ADR-0001](decisions/0001-plain-output-only.md) | Plain output only, Hydraulik has no store | accepted | 2026-10-24 |
| [ADR-0002](decisions/0002-swmm-network-input.md) | SWMM network from a table or from the user's own input file | accepted | 2026-10-24 |
| [ADR-0003](decisions/0003-engines-are-found-not-bundled.md) | Engines are found on the user's machine, never bundled, installed or pulled | accepted | 2026-10-24 |
| [ADR-0004](decisions/0004-own-regular-grid-writer.md) | Write the regular-grid SFINCS model ourselves, without hydromt_sfincs | accepted | 2026-10-24 |
| [ADR-0005](decisions/0005-coupler.md) | Couple SFINCS and SWMM by exchanging volumes through the BMI, in a process of its own | accepted | 2026-10-25 |
| [ADR-0006](decisions/0006-kartograf-adapter.md) | Fetch the data through the Kartograf program and the data-output convention | accepted | 2026-10-25 |
| [ADR-0007](decisions/0007-land-cover-classes.md) | Paint BDOT10k classes on a fine grid and average them into each cell | accepted (values provisional) | 2026-10-25 |
| [ADR-0008](decisions/0008-land-cover-options-of-model-build.md) | The land cover enters `model build` through five options, and roofs are raised only on request | accepted (values provisional) | 2026-10-25 |
