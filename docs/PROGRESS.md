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
| SWMM run and summary (`engines/swmm/run.py`), rain and hydrograph tables (`data/tables.py`) | done | integration tests on the real SWMM |
| SFINCS regular-grid writer (`engines/sfincs/model.py`) | done | ADR-0004; station names are quoted (SFINCS calls unquoted ones `station_001`) |
| Engine detection (`engines/detect.py`) | done | ADR-0003; used by `engines check` and `model run` |
| SFINCS runner, results reader, water balance (`engines/sfincs/{run,inp,results}.py`) | done | exe or Docker (Docker only with a fake `docker`: no daemon here) |
| Commands `engines check`, `model run`, `results read`, `results export` | done | live tests pass on SFINCS v2.4.1 and `main` (`-m live` with `HYDRAULIK_SFINCS_EXE`) |
| Command `swmm run` (`operations/swmm.py`) | done | network table or the user's INP, inflow hydrograph; tests on the real SWMM, run through the CLI |
| Command `rainfall build` (`operations/rainfall.py`, `data/rainfall.py`) | done | Hydrolog shapes, PMAXTP from a document or IMGWTools, Hydrolog document; only the network call is faked in tests |
| Command `terrain download` (Kartograf CLI adapter) | planned | Next 3; Kartograf has no plain mode yet |
| Command `model build`, step one: your own rasters (`terrain/`, `model/`, `operations/build.py`) | done | elevation, Manning, curve number or retention, rain, outlet, stations; live test on SFINCS v2.4.1 and `main` |
| `model build`, step two: land cover (BDOT10k) and soil (HSG) to the Manning and curve-number rasters | planned | Next 4; the class values need the author's review |
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

3. **`terrain download`** (`data/kartograf.py`, `operations/terrain.py`): Kartograf is
   called as a subprocess, never imported, and is targeted at the data-output
   convention (DEV-19, ECO-051), not at what it has today. Checked on 2026-10-25 in the
   working tree of Kartograf 0.8.0.dev0: `output_dir` is still `path_role: root` and
   required, the plan is `check_updates`, a file entry is `{unit, country, file: {path,
   status, label, sha256}}`, plain mode does not exist. So read `kartograf commands
   schema --command "<group> <verb>" --json` (`result.commands[0].options[]`: `name`,
   `path_role`), build the argv only from options the schema declares, and refuse with
   `missing_dependency` (reason `engine_missing`, the hint says Kartograf must offer
   `--output-dir`) when `output_dir` is not `path_role: output`. The contract to
   implement: `kartograf <group> <verb> ... --output-dir DIR --json` gives
   `kartograf-result/1` (exit 0, 10, 11; an error is the last stderr line,
   `kartograf-error/1`) with `files[]` = `{path, size_bytes, sha256, status}` and
   `skipped[]` = `{id, reason, message}`; `--check` gives a plan (`write`, `replace`,
   `conflict`; its field names are not fixed, relay it). What a PL area needs today:
   `elevation download --product nmt --country pl --resolution 1m --vertical-crs
   EVRF2007 --sheet-system 1992` (or `--cutout --horizontal-crs EPSG:2180`, one
   raster), `landcover download --product bdot10k`, `soil hsg --depth 0-5cm` (HSG
   GeoTIFF uint8: 1 A, 2 B, 3 C, 4 D, 0 no data); the area is `--bbox` with
   `--bbox-crs`, or `--geometry` with `--layer`. Command options: `bbox` + `crs` xor
   `geometry` + `layer` (AGI-3.4), `products`, `output_dir`, `force`, `check`; one
   sub-directory per product; result `hydraulik-terrain/1` with `files[]`. Tests: a fake
   `kartograf` program (like `fake_sfincs` in `tests/synthetic.py`) that serves the
   schema and writes files; the live test is marked `live` and skips itself while the
   schema lacks plain mode.
4. **`model build`, step two** (step one, from the user's rasters, is done:
   `terrain/grid.py`, `model/{options,build}.py`, `operations/build.py`; the options are
   `dem`, `dx_m`, `bbox` + `crs` or `geometry` + `layer`, `manning` or `manning_raster`,
   `curve_number_raster` or `retention_mm_raster`, `rain`, `recession_min` (default 60),
   `outlet` + `outlet_layer`, `observation_points`). What is still to build, land cover
   and soil to the two rasters, so that a model needs no raster of the user's own:
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

- English and Polish (AGI-9.2): machine output is English everywhere and Polish exists
  only in the translation resources (`cli/messages.py`, `i18n_pl` of the catalog); the
  new commands follow that and have Polish reason texts. Open: in Polish human output
  the hint and the notices stay English (ECO-042 wants the hint in the language of the
  message); a Polish table for hints and notice codes would close it.
- `rainfall build` names its options after `hydrolog precip hietogram` (`hietogram_type`,
  `total_mm`, `duration_min`, `timestep_min`, `alpha`, `beta`, `peak_position`) and
  `imgw pmaxtp fetch` (`latitude`, `longitude`, `method`), by AGI-1.2.
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
