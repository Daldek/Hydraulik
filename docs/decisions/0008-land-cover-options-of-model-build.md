# ADR-0008: The land cover enters `model build` through five options, and roofs are raised only on request

- Status: accepted for the wiring (delegated approval of the plan, 2026-10-24); the class
  values stay provisional (ADR-0007, PROGRESS open questions)
- Date: 2026-10-25
- Requirements: ADR-0001, ADR-0004, ADR-0007, AGI-1.2, AGI-3.1, DEV-19.1

## Context

ADR-0007 gave the tables and the painter as a library module. Making them a part of
`model build` raises five questions: how the user names the inputs, how they combine with
the Manning and curve-number options that exist, what SFINCS can do with a building, what
a soil raster must hold, and how the user sees what was made from the land cover.

## Options considered

| Option | Verdict |
|---|---|
| A. Five options of `model build` (`--landcover`, `--hsg`, `--default-hsg`, `--classes`, `--building-raise-m`); the land cover is painted in memory on the grid of the model and two check rasters are written beside the model | Chosen |
| B. A command that writes Manning and curve-number rasters, which `model build` reads through `--manning-raster` and `--curve-number-raster` | Rejected: the painting needs the grid of the model (cell size, domain), so the user would give both twice and the two commands would have to agree; the roofs change the elevation, which is not a raster of the first command |
| C. Raise every roof by a default height | Rejected: the height would be a number nobody reviewed in every model, and a model of a terrain that the user gave would no longer be that terrain |

## Decision

Option A (`hydraulik.model.options`, `hydraulik.model.build`, `hydraulik.operations.build`).

- **Names.** `landcover` is the product of `terrain download` that the file comes from,
  `hsg` the raster of the hydrologic soil groups, `default_hsg` one of `A` to `D`,
  `classes` the CSV that replaces values (ADR-0007) and `building_raise_m` a height in m.
- **Combinations.** The roughness has one source: `landcover` excludes `manning` and
  `manning_raster`. The curve number has one source: `hsg` and `default_hsg` exclude
  `curve_number_raster` and `retention_mm_raster` (a curve-number raster beside
  `landcover` is allowed: the roughness comes from the land cover, the infiltration from
  the raster). `hsg`, `default_hsg`, `classes` and `building_raise_m` need `landcover`
  (`option_not_applicable`). The catalog's `one_of` names one group per option and cannot
  say this, so `_prepare` refuses the combinations (`exclusive_options`) before any file
  is read, and the `rules` of the command say it too.
- **Soil groups.** The raster is read by the nearest cell (a group is a class: no mean, no
  interpolation) with the codes that Kartograf writes: 1 A to 4 D, 0 no data. A code above
  4 in the domain means it is not a raster of soil groups (`invalid_hsg`). A cell without
  a group gets `default_hsg` (a warning when a raster was given and left cells open, an
  info when the default is the only source); without a default it has no curve number
  (the `cn_gaps` warning, as for a curve-number raster; an error when no cell has one).
  With neither `hsg` nor `default_hsg` infiltration is off and a notice names both options.
- **Buildings.** A regular-grid model has no building footprints: a roof is ground that
  the water crosses, or it is higher ground. A cell with half or more of its area under
  roofs is raised by `building_raise_m`, whose default is 0, and only then does the
  roughness of a roof (0.011) count. The result lists the cells (`landcover.buildings`)
  and a notice says whether they were raised. The statistics of the elevation are those
  of the model as written.
- **Checking it.** `manning.tif` and `curve_number.tif` are written beside the model
  files (GeoTIFFs on the grid of the model, north-up, in its CRS, with the source in the
  tags). SFINCS does not read them; `model run` copies them like any other file of the
  directory. They are planned and reported like the other files (`files[]`, conflicts).
- **Result.** `hydraulik-model/1` gets the optional `landcover` key (the areas of the
  classes, the roads, the buildings, the attribute values the mapping lacks) and, in
  `infiltration`, `source: landcover` and the `hsg` counts. Adding keys keeps the schema at
  `/1` (AGI-4.1); `infiltration.path` and `infiltration.resampling` are no longer
  required, because a default group has neither.
- **`--check`.** It looks for the land-cover file and the soil raster, reads the class
  table (so a table that a run would refuse fails the plan) and names the classes, the
  soil group and the raise in a step. It does not read the GeoPackage.

## Consequences

- A model with `--landcover` and no soil information runs without infiltration; the notice
  says how to switch it on.
- With the default raise of 0 buildings do not obstruct the flow; the notice says so. A
  model of an urban area needs `--building-raise-m` to let the water run round the
  houses: the author may want a default (PROGRESS, open questions).
- The tiles of the painter keep the memory flat, so the size of the model is limited by
  the 25 million cells of the grid and not by the land cover.
- Checked on the real data of the proof of concept (BDOT10k of Poznań, a square
  kilometre at 10 m): the model is built in under 2 s and runs on SFINCS v2.4.1 with a
  balance that closes (PROGRESS).

## Errata

None.
