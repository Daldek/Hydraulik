# Progress

## Status

| Component | State | Note |
|---|---|---|
| Tooling: uv, gate, CI, live workflow, Dependabot | done | `scripts/gate.sh`, `.github/` |
| Extraction note and plan | done | `docs/plans/2026-10-24-sfincs-swmm-*.md`; the plan is approved (delegated, 2026-10-24) |
| Error registry, settings, plain output writer | done | `_errors.py`, `settings.py`, `output.py`; ADR-0001 |
| Command catalog, envelope, CLI, AGENTS.md, llms.txt, schemas | done | `commands list\|schema\|guide`, `config show` |
| Exchange law, diagnostics, balance (`coupling/`) | done | pure functions from the experiment |
| SWMM network table, INP writer and reader, report parser | done | ADR-0002; runs on the real SWMM in `tests/integration` |
| SWMM run and summary (`engines/swmm/run.py`), rain and hydrograph tables (`data/tables.py`) | done | integration tests on the real SWMM; library only, `swmm run` is not declared yet |
| SFINCS regular-grid writer (`engines/sfincs/model.py`) | done | ADR-0004; station names are quoted (SFINCS calls unquoted ones `station_001`) |
| Engine detection (`engines/detect.py`) | done | ADR-0003; used by `engines check` and `model run` |
| SFINCS runner, results reader, water balance (`engines/sfincs/{run,inp,results}.py`) | done | exe or Docker (Docker only with a fake `docker`: no daemon here) |
| Commands `engines check`, `model run`, `results read`, `results export` | done | live tests pass on SFINCS v2.4.1 and `main` (`-m live` with `HYDRAULIK_SFINCS_EXE`) |
| Command `swmm run` | planned | Next 1 |
| Command `rainfall build` (Hydrolog, IMGWTools) | planned | Next 2 |
| Command `terrain download` (Kartograf CLI adapter) | planned | Next 3; Kartograf has no plain mode yet |
| Command `model build` (`terrain/`, land cover to Manning, HSG and land cover to SCS S) | planned | Next 4 |
| SFINCS BMI wrapper, coupler, command `model couple` | planned | Next 5; optional feature (needs a user-built libsfincs) |
| Live tests of the rest, README and ADR-0005 | planned | Next 6 |
| Phase 2 items that need the author | blocked | see Open questions |

## Next

Every new command: declare it in `catalog/commands.py` with its Polish texts, add the
function to `operations/` and to `__all__` (import heavy packages inside the function:
a contract test checks that `import hydraulik` loads none), write the schema in
`src/hydraulik/schemas/`, add the flow to `agent_guide.FLOWS`, the row to the README
Capabilities table, regenerate the guides (`python -m hydraulik commands guide --format
agents > AGENTS.md`, `--format llms > llms.txt`), add the Polish reason texts to
`cli/messages.py`, test with fakes (`tests/synthetic.py`) and, where an engine is
involved, with a `live` test. Option names `path`, `root` and `store` are forbidden (a
contract test). Write source files with the `write` tool or a quoted heredoc, never with
a Python string that holds backslashes.

1. **`swmm run`** (`operations/swmm.py::run_network`, function `hydraulik.run_network`):
   options `network` (CSV table) xor `inp` (the user's file, CMS), `inflow` (hydrograph
   table, `data.tables.read_hydrograph`) with `inflow_node`, `duration_min`,
   `routing_step_s` (0.5), `surcharge_method`, `output_dir`, `force`, `check`. Writes
   `network.inp` and `network.rpt` (the `.out` stays in staging); result
   `hydraulik-swmm/1` from `SwmmSummary` (totals, nodes, conduits, continuity error).
   A network table has no inflow of its own, so `inflow` is required with it. pyswmm
   allows one open simulation per process.
2. **`rainfall build`** (`data/rainfall.py`): Hydrolog `EulerIIHietogram(peak_position)`,
   `BetaHietogram(alpha, beta)`, `BlockHietogram`, `TriangularHietogram` with
   `.generate(total_mm, duration_min, timestep_min)`; depth either given (`depth_mm`) or
   from IMGWTools `fetch_pmaxtp(lat, lon, method).data.get_precipitation(duration_min,
   probability_percent)` (durations 15, 30, 45, 60, 90, 120, 180 min; probabilities 1,
   2, 5, 10, 20, 50 %; `None` is `no_data`); output `--output` a rain table
   (`data.tables.render_rain_table`); `--check` plans without the network call; the
   result carries the IMGW-PIB attribution.
3. **`terrain download`**: Kartograf is called as a subprocess, never imported. Facts
   from KartografAdopt7 on 2026-10-25: plain mode (`--output-dir`) does not exist yet,
   `-o/--output` is still the store root and `--check-updates` the plan. So read
   `kartograf commands schema --command "<group> <verb>" --json` (`result.commands[0]
   .options[]`: `name`, `path_role` output = plain directory, root = store) and refuse
   with `missing_dependency` (reason `engine_missing`) when no option has `path_role`
   output; do not hard-code flags. The envelope `kartograf-result/1` (exit 0, 10, 11; an
   error is the last line of stderr, `kartograf-error/1`) is stable. A file entry is
   `e.get("path") or e.get("file", {}).get("path")`, `size_bytes` is optional,
   `targets[]`, `conflicts[]` and `action` are unknown. Products: `elevation download
   --product nmt`, `landcover download --product bdot10k`, `soil hsg --depth 0-5cm`
   (HSG GeoTIFF uint8: 1 A, 2 B, 3 C, 4 D, 0 no data); one sub-directory per product.
4. **`model build`** (`terrain/`, `model/`; the design is settled, nothing is written):
   grid aligned to `dx_m` from the domain polygon or the DEM extent; DEM reprojected
   with `rasterio.warp.reproject` (average when finer than the grid, bilinear
   otherwise), several files one after the other; BDOT10k classes painted on a finer
   grid (`OT_PT*_A` polygons, roads `OT_SKJZ_L` buffered, buildings `OT_BUBD_A` last;
   layer to class: water PTWP, forest PTLZ, shrub PTRK, arable PTUT, grass PTTR, built_up
   PTZB, paved PTKM and PTPL, bare PTGN, PTWZ, other PTNZ, PTSO), the class fractions per
   cell give the Manning `n` (area-weighted mean) and the composite CN by HSG (TR-55
   values as in Hydrolog's `cn_lookup`, table overridable with `--classes FILE`);
   `ModelInputs.curve_number` then gives `S = 1000/CN - 10`; HSG reprojected nearest,
   0 = `--default-hsg`; outlet cells = cells of the outlet geometry on the edge of the
   domain (`msk = 3`); `--building-raise-m` (SCOPE: the MVP raises the DEM at
   buildings; default 0); `tstop` = rain end + `recession_min`, `dtout` = `tstop`;
   rain table to `precip_breakpoints`. Real inputs for a smoke run (read only, never
   write there): `~/hydraulik-work/poznan_rataje_poc/data` (`nmt_1m.tif`, EPSG:2180,
   `bdot10k/bdot10k_teryt_3064.gpkg`).
5. **BMI wrapper, coupler, `model couple`**: `engines/sfincs/bmi.py` is the ctypes
   wrapper of the old `coupler.py::SfincsBmi` (`initialize`, `update_until(t_abs)`,
   `finalize`, `get_value_ptr` for `zs` (double), `zb` and `qext` (float),
   `get_var_shape`, `set_logical("qext")`, `get_sfincs_cell_index(x, y)` 1-based,
   `get_sfincs_cell_area`, `get_last_bmi_error` on `main` only); `qext` is m3/s per cell
   on `main` and m/s on v2.4.1 (`sfincs.qext_unit`); the arrays hold the active cells
   only; SFINCS reads `sfincs.inp` from the working directory, so change into the
   staging directory for the whole run; one model per process (global Fortran state), so
   a live test runs the CLI in a subprocess. The loop (extraction note 3) goes in
   `coupling/coupler.py` over two protocols: the surface (cell of a point, level, bed,
   area, `qext`, advance, stored volume) and the network, which `SwmmStepper` already is
   (`head_m`, `rim_m`, `add_inflow`, `flooding_volume_m3`, `outfall_flow_m3s`,
   `stored_volume_m3`, `advance`); fakes in `tests/`; modes `swmm_flooding` (default,
   `SurDepth` 0) and `coordinator`; sum `qext` over nodes that share a cell and cap the
   sum; refuse when the rim differs from the bed by more than `rim_tolerance_m`; book
   rain and infiltration from the final map (`cumprcp`, `cuminf`), not from the BMI;
   with outflow cells the residual is not an error. `model couple` refuses before any
   work when `sfincs.library` or pyswmm is missing (`engines check --require 'model
   couple'`). Local engines for the live tests: build SFINCS v2.4.1 and `main` with
   gfortran and netCDF-Fortran (`./configure --enable-shared`, plain `make`, extraction
   note 7) and set `HYDRAULIK_SFINCS_EXE` and `HYDRAULIK_SFINCS_LIBRARY`; the built
   library finds `libnetcdff` through its run path, no `LD_LIBRARY_PATH` is needed.
6. README Quick start for the new commands, ADR-0005 (the coupler), the weekly live
   workflow for the new live tests, final PROGRESS.

## Open questions

- Decided on 2026-10-24 by the coordinator, the author's delegate: the plan is approved
  (`Approved:` line, ADR-0001 to ADR-0004 accepted); the SWMM coupling stays an optional
  feature (`SCOPE.md` keeps the full 1D sewer coupling out of the MVP), so Q1 is closed.
- `hydromt_sfincs` and subgrid: the writer here is regular-grid only (ADR-0004);
  decide whether an optional adapter extra follows.
- Which SFINCS build does the coupling target? The release v2.4.1 and the pinned
  image have `qext` in m/s and no library; the default `sfincs.qext_unit` is `m3s`.
- Provisional thresholds: the sustained-spill volume (1 m3) and the spike tolerance
  (0.05 m, hold time 10 s) are still open in the experiment's README 7.1.
- May CI pull `deltares/sfincs-cpu` for the weekly live workflow?
- Kartograf has no plain mode yet (KartografAdopt7, 2026-10-25): `terrain download` cannot
  be exercised on the real tool until the data-output convention is implemented there.
- The values of the land-class table (Manning `n`, TR-55 curve numbers by soil group) and
  the default `--building-raise-m` are mine, from the literature and the author's
  documents; the author should review them before a result is used.
- The author's uncommitted files overlap what this branch adds (`CLAUDE.md`,
  `docs/PROGRESS.md`, `.gitignore`) and the PoC package uses the same import name:
  decide the order in which the PoC and this branch reach `develop`.
- Skipped because they need the author: history rewrite (ADOPTION_PLAN phase 1),
  `main` as default branch, GitHub rulesets, Dependabot security updates and private
  vulnerability reporting (DEV-3.6, DEV-13.6, DEV-13.7), licence and CLA text, tags,
  pushes, committing the proof of concept from the worktree (DEV-3.5).
