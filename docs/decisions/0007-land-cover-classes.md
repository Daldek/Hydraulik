# ADR-0007: Paint BDOT10k classes on a fine grid and average them into each cell

- Status: accepted for the method; the class values are provisional until the author
  reviews them (PROGRESS, open questions)
- Date: 2026-10-25
- Requirements: ADR-0004, ECO-041; extraction note decisions 6 and 9

## Context

A model needs a Manning `n` and an SCS curve number in every cell. The land cover is
BDOT10k (GUGiK), the soil is a raster of hydrologic soil groups (HSG, 250 m, from
Kartograf), and the cells are 5 to 25 m. In BDOT10k roads are lines (a street is narrower
than a cell), buildings are 80 000 small polygons per county and the land-cover polygons
carry the kind of cover in an attribute (`PTTR` is grass and arable land, `PTZB` has five
kinds of built-up land). The curve numbers of the author's Hydrograf table map BDOT10k
codes that do not mean what the table says (PTZB, the built-up land, as meadow; PTRK, the
shrubs, as arable land), so the classification list of GUGiK is the reference here.

## Options considered

| Option | Verdict |
|---|---|
| A. Paint the classes on a grid of about 1 m, in the order of a mapping table (polygons, roads as buffered lines, buildings as a mask), and average `n` and CN over the area of each cell | Chosen |
| B. The class of the cell centre or the dominant class | Rejected: a street one cell wide and a row of houses vanish, and these are the flow paths and the blocks of an urban flood |
| C. Exact intersection areas of the polygons with every cell | Rejected: the same result as A at the accuracy of BDOT10k (1 to 3 m), at the cost of intersecting 80 000 buildings with a grid |
| D. `hydromt_sfincs` reclassification | Rejected: GPL-3.0, ADR-0004 |

## Decision

Option A (`hydraulik.model.landcover`, tables in `hydraulik/_data/landcover`,
documented in `docs/LAND_COVER.md`).

- The tables are two CSV files that ship with the package: `classes.csv` (each class with
  Manning `n`, the curve number for the groups A to D and the source of each value) and
  `mapping.csv` (layer, attribute, value, class; the rows are painted in order). A
  user's `--classes` file replaces values; it never adds classes.
- Manning `n` is the area-weighted mean, the curve number the area-weighted mean for the
  soil group of the cell (TR-55 composite curve number). The soil group is the nearest cell
  of the raster; a cell without one has no curve number (a warning), unless a default
  group fills it.
- Roads on the ground are buffered by half the width of their surface, 5 m where it is
  missing; bridges, tunnels and conventional lines are not painted. Buildings are a mask:
  they are impervious (CN 98) and change `n` only where they are raised.
- The values are literature values for shallow overland flow (TR-55 table 3-1, Kalyanapu
  et al. 2009) and TR-55 curve numbers, each with its source in the table. Nobody has
  reviewed or calibrated them for Polish catchments.
- The painting is done in tiles, so the memory does not depend on the size of the model.

## Consequences

- Built-up classes count the impervious share of a plot (TR-55) and roofs and roads are
  painted at 98 over them: a few curve-number points to the wet side in dense blocks.
- The shallow-flow `n` values are several times those of floodplain tables; they slow the
  water on vegetated land. SFINCS has no roughness that depends on the depth.
- The painter and the tables are a library module; wiring them into `model build`
  (options, result, files) is the next step.

## Errata

None.
