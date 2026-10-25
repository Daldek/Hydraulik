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
| Command `terrain download` (`data/kartograf.py`, `operations/terrain.py`) | done | ADR-0006; written against the data-output convention, tested with a fake Kartograf; refuses a Kartograf whose `output_dir` is a store root; the live test skips until Kartograf has plain mode |
| Command `model build`, step one: your own rasters (`terrain/`, `model/`, `operations/build.py`) | done | elevation, Manning, curve number or retention, rain, outlet, stations; live test on SFINCS v2.4.1 and `main` |
| `model build`, step two: land cover (BDOT10k) and soil (HSG) to the Manning and curve-number rasters | planned | Next 4; the class values need the author's review |
| SFINCS BMI wrapper, coupler, command `model couple` (`engines/sfincs/{bmi,layout}.py`, `coupling/{coupler,worker,process}.py`, `operations/couple.py`) | done | ADR-0005; the coupled run is a worker process; live tests on the local `libsfincs` of SFINCS v2.4.1 (`ms`) and `main` (`m3s`); a wrong unit is flagged by the balance |
| Weekly live workflow for the library tests, README quick start of `terrain download` | planned | Next 6; ADR-0005 is written |
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

3. **`terrain download`**: done (ADR-0006). Kartograf is started as a program with
   `--output-dir`, one sub-directory per product; the options come from `kartograf
   commands schema`; a Kartograf whose `output_dir` is not `path_role: output` is
   refused (`engine_incompatible`), also by `engines check`. Not exercised on the real
   tool: Kartograf 0.8.0.dev0 has no plain mode yet (checked 2026-10-25: `output_dir` is
   `path_role: root`, the plan is `check_updates`). When it ships, run `pytest -m live
   tests/integration/test_terrain_live.py` with `HYDRAULIK_KARTOGRAF_EXE`; the plan
   field names (read as any entry with `action` and `path`) and the item ids are what
   may differ.
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
5. **BMI wrapper, coupler, `model couple`**: done, see ADR-0005. Live tests: build SFINCS
   v2.4.1 and `main` with gfortran and netCDF-Fortran (`./configure --enable-shared`,
   plain `make`, extraction note 7) and run `pytest -m live` with
   `HYDRAULIK_SFINCS_LIBRARY` (the `libsfincs.so` it made; it finds `libnetcdff` through
   its run path, no `LD_LIBRARY_PATH` is needed), `HYDRAULIK_SFINCS_QEXT_UNIT` (`ms` for
   v2.4.1, `m3s` for `main`) and, for the model tests, `HYDRAULIK_SFINCS_EXE`. Open in
   the coupling: the unit of `qext` is not probed, the balance flags a wrong one; your
   own `--inp` is covered by tests with a fake worker but has had no live run (the live
   runs use `--network`); the SWMM clock of your input is set to 2000-01-01, so inflow
   series dated otherwise are lost; Windows and macOS are unchecked.
6. The weekly live workflow for the library tests (it has to build `libsfincs` with
   `--enable-shared`; the workflow pulls no engine today), the README quick start of
   `terrain download`, the final PROGRESS.

## Open questions

- English and Polish (AGI-9.2): machine output is English everywhere and Polish exists
  only in the translation resources (`cli/messages.py`, `i18n_pl` of the catalog); the
  new commands follow that and have Polish reason texts. Open: in Polish human output
  the hint and the notices stay English (ECO-042 wants the hint in the language of the
  message); a Polish table for hints and notice codes would close it.
- Choices of mine that the author should review: `model build` takes `recession_min` 60
  and Manning `n` 0.04 when not given; `model couple` takes `rim_tolerance_m` 0.1, an
  exchange interval of 1 s, relaxation 1 (`swmm_flooding`) or 0.1 (`coordinator`) and
  calls more than 20 sign changes of the exchange of a node an oscillation. The default
  `huthresh` of the model writer, 0.05 m, keeps water under 5 cm where it fell: a light
  rain does not run off (the live tests use 100 mm).
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
