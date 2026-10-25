# Changelog

All notable changes to Hydraulik are recorded here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- The uv project, the Nogat quality gate, CI and Dependabot workflows, and the
  repository files of standard 2.1.
- The extraction note and the plan of the SFINCS and SWMM integration.
- The shared Nogat error registry: vendored copies in `schemas/nogat/`, the
  generated `hydraulik._errors`, `HydraulikError` with its subclasses and the
  `hydraulik-error/1` document (ERR-3, ERR-4, DEV-11.1).
- Settings of the user environment: `nogat.toml`, `HYDRAULIK_*` variables, the
  precedence of DEV-18.1 and `.env.example` (DEV-18.1, DEV-18.3).
- The plain-mode output writer: preflight with `--check` plan, conflicts for
  duplicate names, existing files and directories inside a Nogat store, staging
  and atomic replacement, `files[]` records (DEV §19, ADR-0001).
- The command catalog `hydraulik-commands/1` with validation, the five generic
  functions `list_commands`, `command_schema`, `validate_command`,
  `check_command` and `run_command`, the result envelope `hydraulik-result/1`,
  the CLI generated from the catalog (`commands list|schema|guide`,
  `config show`), generated `AGENTS.md` and `llms.txt`, and the schemas of the
  documents (AGI-1.1, AGI-2.1 to AGI-2.4, AGI-3.1 to AGI-3.8, AGI-4.1 to
  AGI-4.4, AGI-7.1, AGI-7.2, AGI-8.1, AGI-8.2).
- The SWMM network table and the SWMM input writer and reader, the exchange law,
  diagnostics and balance of the coupling, the SFINCS regular-grid model writer
  (checked on SFINCS v2.4.1 and main), the detection of the engines, a live test
  that runs a written model on the real SFINCS and the weekly live workflow
  (ADR-0002, ADR-0003, ADR-0004). These are library modules; their commands
  follow.
- Running SFINCS on a model directory (an executable or a Docker image that is
  already present): streamed progress, a timeout that also kills the container, the
  `Error :` line of SFINCS and the end of its log in the error; and reading its
  results: grid and masks, maximum depth and velocity, flooded areas, stations, the
  water balance (rain, infiltration, storage, residual, flags) and GeoTIFF export. The
  live tests pass on SFINCS v2.4.1 and on `main`; ADR-0004 has an erratum on the
  masking of the map (`h` is not masked). These are library modules; their commands
  follow.
- Running a SWMM input through pyswmm in strides of whole seconds (`SwmmStepper`:
  heads, rims, lateral inflows, flooded volumes, the flow through the outfalls, the
  stored volume) and `run_swmm` with inflow hydrographs at nodes; the summary has the
  totals in cubic metres, the statistics of every node and conduit and SWMM's own
  continuity error, which the totals reproduce to 0.01 percent. The rain table and the
  hydrograph table (`time_min`, `depth_mm` and `time_min`, `discharge_m3s`) are read
  and written by `hydraulik.data.tables`.
- The commands `engines check` (the engines and Python packages found, what each
  command needs, `--require` for scripts), `model run` (SFINCS on a copy of the model
  directory in staging; the map, the station file and the log reach `--output-dir` only
  after a successful run; maxima, flooded areas and the water balance in the result),
  `results read` and `results export` (a map as a GeoTIFF in the CRS of the model, or the
  station series as CSV), each with `--check` where it writes, the domain schemas
  `hydraulik-engines/1`, `-run/1`, `-results/1` and `-export/1`, and the optional
  `blockers` of `hydraulik-plan/1` (an engine or an extra that would stop the run). Live
  tests of the four commands pass on SFINCS v2.4.1 and on `main`.
- The command `swmm run` (`hydraulik.run_network`): EPA SWMM through pyswmm on a network
  table or on the user's own SWMM input (SI units), with an inflow hydrograph at one
  node; `network.inp` and `network.rpt` reach `--output-dir` only after SWMM finished;
  the result `hydraulik-swmm/1` has the water balance of SWMM and the peaks of every
  node and conduit, and the notices flag a continuity error above 5 %, flooded nodes
  and an inflow that outlasts the run. `--check` plans it. `engines check` no longer
  lists numpy as a need of `swmm run`.
- The command `rainfall build` (`hydraulik.build_rainfall`): the rain table
  (`time_min,depth_mm`) of a model from a Hydrolog hyetograph shape (`block`,
  `triangular`, `beta`, `euler_ii`, the options of `hydrolog precip hietogram`) with a
  given depth or the PMAXTP depth of IMGW-PIB for a duration and a probability, taken
  from the document of `imgw pmaxtp fetch --json` or fetched for a point through
  IMGWTools; or the result of `hydrolog precip hietogram --json` converted as it is.
  Hydrolog and IMGWTools are used through their public classes, functions and
  documents only. The result `hydraulik-rain/1` says how the depth was found; a PMAXTP
  depth comes with a notice to name IMGW-PIB; `--check` fetches nothing. The rain table
  now has six decimals per step.
- The command `model build` (`hydraulik.build_model`), the first step from your own
  rasters: elevation GeoTIFFs (several, the first sets the CRS and wins) are averaged
  (finer than the grid) or interpolated (coarser) onto a grid of `--dx-m` cells aligned
  to `--dx-m`; the domain is a polygon (`--geometry`, `--layer`), a rectangle (`--bbox`
  with `--crs`, any CRS) or every cell with elevation; Manning `n` is a number, a
  raster or 0.04; the SCS curve number is a raster or comes from the retention `S` in
  mm (`CN = 25400 / (S + 254)`); the rain is the table of `rainfall build`; `--outlet`
  geometries become outflow cells on the edge of the domain; `--observation-points`
  are stations. A cell of the domain without elevation or Manning `n` is an error, a
  gap in the curve numbers a warning, and the notices name the defaults that were
  applied and the closed boundary. The result `hydraulik-model/1` describes the grid
  and every input; `--check` plans the grid and the files. The model ran on SFINCS
  v2.4.1 and on `main` in a live test that checks the orientation of the whole chain
  (water collects at the low edge, the balance closes). `hydraulik.data.tables` reads
  station tables; `FILES` moved from the model writer to `engines.sfincs.inp`.
- The command `model couple` (`hydraulik.couple_model`) and the coupling of SFINCS with
  a SWMM network (ADR-0005): the SFINCS BMI through `ctypes` (`engines.sfincs.bmi`, the
  layout of the active cells from the index file in `engines.sfincs.layout`), the
  exchange loop over two small protocols (`coupling.coupler`: volumes are exchanged,
  the water taken from a cell is limited to what stands there, nodes that share a cell
  share the limit, SWMM's flooding returns to the cell or, in the `coordinator` mode,
  the exchange law spills the node with relaxation), and a worker process
  (`coupling.worker`, `coupling.process`) because SFINCS keeps its state in global
  variables and prints to its standard output. `--network` or your own `--inp`
  (run with a fixed routing step, the clock of the model and the surcharge depth of the
  mode; the copy is `network.inp`). The command refuses before any work when
  `sfincs.library` or pyswmm is missing; `--check` plans it. The result
  `hydraulik-couple/1` books the water (rain, infiltration, surface, network, outfall,
  exchange, pending, lost) and flags a residual above 1 %; notices flag a wrong
  `sfincs.qext_unit` (as a balance that does not close), a continuity error above 5 %,
  an oscillation, a head spike and nodes off the domain. Live tests on the local builds
  of SFINCS v2.4.1 (`ms`) and `main` (`m3s`) pass; a wrong unit is flagged on both.
  `coupled_balance` books infiltration and flooding without a cell; `stage_model` is
  shared with `model run`.
- The command `terrain download` (`hydraulik.download_terrain`, ADR-0006): the terrain,
  the BDOT10k land cover and the soil groups of an area, fetched by starting Kartograf
  as a program with `--output-dir` (plain files, one sub-directory per product:
  `elevation` the 1 m NMT as one GeoTIFF in EPSG:2180, `landcover` the BDOT10k county
  GeoPackage, `soil` the HSG GeoTIFF). It is written against the data-output
  convention: the options come from `kartograf commands schema`, an argument is built
  only from a declared option, and a Kartograf whose `output_dir` is a store root
  (`path_role: root`, as in Kartograf 0.8.0.dev0) is refused with `missing_dependency`
  (reason `engine_incompatible`) before anything is fetched; `engines check` reports it
  the same way. The plan of every product is read before the first byte and a conflict
  in any of them fails the call (DEV-19.6); `--check` returns those plans. The result
  `hydraulik-terrain/1` lists `files[]`, `skipped[]`, the per-unit `items[]` (status
  `partial` or `failed` when units fail) and the sources with their licences. Tested
  with a fake Kartograf program; the live test skips until Kartograf ships plain mode.
  `rebuild_error` (exceptions) maps an error document back to its exception class (the
  coupling worker uses it too) and `sigterm_as_error` (output) is shared by the writer.
- The land-cover tables and the painter of `model build` step two (ADR-0007), as library
  modules: `classes.csv` (16 classes, each with a Manning `n` for shallow overland flow,
  the SCS curve number for the soil groups A to D and the source of every value,
  `docs/LAND_COVER.md`) and `mapping.csv` (BDOT10k layer, attribute and value to class);
  `model.classes` reads them and the `--classes` override (comma or semicolon, decimal
  point or comma; it replaces values, never adds classes), and `model.landcover` paints
  the features on a grid of about 1 m in tiles (polygons, roads as lines buffered by half
  their width, buildings as a mask) and averages `n` and the curve number into every
  cell. `terrain.grid` gains `resample_codes` (nearest cell, for the soil groups) and
  `write_grid_raster`, which `export_geotiff` uses now. The values are literature values
  that the author has not reviewed.
- `model build` makes Manning `n` and the SCS curve number from the BDOT10k land cover
  (ADR-0008): `--landcover FILE` paints the classes into `sfincs.man`, `--hsg FILE` (the
  raster of hydrologic soil groups, the nearest cell) and `--default-hsg A|B|C|D` (the
  cells it does not cover, or every cell) make the curve number of `sfincs.scs`,
  `--classes FILE` replaces class values and `--building-raise-m H` raises the cells that
  are half or more under roofs (default 0: the buildings are ground the water crosses).
  `manning.tif` and `curve_number.tif` are written beside the model to look at. The
  combinations are checked before a file is read (`--landcover` excludes `--manning` and
  `--manning-raster`; the soil options exclude the curve-number and retention rasters;
  the other four options need `--landcover`), `--check` reads the class table, and the
  result `hydraulik-model/1` gets the `landcover` key (areas of the classes, roads,
  buildings, attribute values the mapping lacks) and `infiltration.hsg`. Checked on the
  real BDOT10k of Poznań: a square kilometre at 10 m builds in under 2 s and runs on
  SFINCS v2.4.1 with a balance that closes.
- `model couple` takes an inflow hydrograph (ADR-0009): `--inflow FILE --inflow-node
  NODE`, the table of `time_min,discharge_m3s` that `swmm run` reads and that `hydrolog
  route network --output-dir` writes for every node of a river network, for water that
  comes from outside the model, such as a catchment that the grid does not cover. The
  discharge at the middle of each exchange interval is added to the exchange of the node
  in one call (SWMM takes the value as the rate of the node); the node is a junction of
  the table or any node of your input, on the model or not. The balance has a term of
  its own, `network_inflow_m3` (`coupled_balance(network_inflow_m3=...)`), the result
  has `coupling.inflow` (file, node, volume of the table, volume given), and a table
  that outlasts the run is cut with the notice `inflow_cut`. The unit-test fakes, the
  worker on the real SWMM and the command with a fake worker cover it; a live test fills
  a 0.15 m pipe with the 279 m3 of a Hydrolog table until the manhole floods and the
  street holds 0.44 m (-0.23 %, SFINCS v2.4.1 and `main`, and the coordinator mode).
- A fixture made by the real `hydrolog route network` (`tests/fixtures/hydrolog`: the
  network document, the inflows, the five tables and the result without its paths) and
  tests that every table is read with the peak, time and volume that Hydrolog reports
  and runs through `swmm run` on the real SWMM; a live test makes the tables again.
- Contract tests against `hydrolog.testing` (DEV-10.6, ADR-0010): the case and the `precip hietogram` envelope that Hydrolog builds equal the recorded fixtures and are read by the readers of Hydraulik; the module runs in the gate.
- `docs/USAGE.md`: the tasks of a flood study from `terrain download` to `model couple`,
  with the examples that the offline tests run; the long walkthrough that the README
  held moved there, and the links of the README are absolute (DOC-1.4).

### Changed

- The `rainfall` extra declares the supported ranges `hydrolog>=1.0.0.dev0,<2` and
  `imgwtools>=3.0.0.dev0,<4` (REL-5.6) and pins the producers' development heads by commit in
  `[tool.uv.sources]`: Hydrolog `5fa22b35` (`feature/routing-schematic`, 1.0.0.dev0) and
  IMGWTools `3f7de36` (`feature/data-output`, 3.0.0), both on GitHub, instead of the tags
  v0.7.0 and v2.1.1 (REL-5.3, ADR-0011). `tests/fixtures/rain/hietogram_euler_ii.json` is recorded
  again from the real command.

### Fixed

- The PMAXTP tables keep a fractional probability of the 27 that IMGW-PIB publishes: the key
  `"0.5"` was read as 5 and met `"5"` of the same table (ADR-0011 erratum 1).
- SFINCS keeps the name of an observation point only when the name is quoted in
  `sfincs.obs`; the writer quotes it (an unquoted name became `station_001`) and refuses
  a name that is empty or holds a quote.
- `rainfall build --latitude` passed `method` to `imgwtools.fetch_pmaxtp` by position;
  IMGWTools 3.0.0 made it keyword-only, so the call failed with `TypeError` against the
  real function (the fakes of the tests accepted a positional argument).
