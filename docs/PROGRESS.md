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
| Engine detection (`engines/detect.py`) | done | ADR-0003; used by `engines check`, `model run` and `terrain download` |
| SFINCS runner, results reader, water balance (`engines/sfincs/{run,inp,results}.py`) | done | exe or Docker (Docker only with a fake `docker`: no daemon here) |
| Commands `engines check`, `model run`, `results read`, `results export` | done | live tests pass on SFINCS v2.4.1 and `main` (`-m live` with `HYDRAULIK_SFINCS_EXE`) |
| Command `swmm run` (`operations/swmm.py`) | done | network table or the user's INP, inflow hydrograph; tests on the real SWMM, run through the CLI |
| Command `rainfall build` (`operations/rainfall.py`, `data/rainfall.py`) | done | Hydrolog shapes, PMAXTP from a document or IMGWTools, Hydrolog document; only the network call is faked in tests |
| Command `terrain download` (`data/kartograf.py`, `operations/terrain.py`) | done | ADR-0006; written against the data-output convention, tested with a fake Kartograf; refuses a Kartograf whose `output_dir` is a store root; the live test skips until Kartograf has plain mode |
| Command `model build`, step one: your own rasters (`terrain/`, `model/`, `operations/build.py`) | done | elevation, Manning, curve number or retention, rain, outlet, stations; live test on SFINCS v2.4.1 and `main` |
| `model build`, step two: land cover (BDOT10k) and soil (HSG) to Manning `n` and the curve number | done | `--landcover`, `--hsg`, `--default-hsg`, `--classes`, `--building-raise-m` (`model/{options,build,classes,landcover}.py`, `operations/build.py`, `_data/landcover/`, `docs/LAND_COVER.md`, ADR-0007, ADR-0008); tested on synthetic GeoPackages with hand-computed values; by hand on the real BDOT10k and NMT of Poznan, a square kilometre at 10 m, on SFINCS v2.4.1; the class values need the author's review |
| End-to-end chain test (`tests/integration/test_terrain_to_model.py`) | done | a fake Kartograf delivers a real GeoTIFF, GeoPackage and soil raster; then the real commands `terrain download`, `rainfall build`, `model build` (land cover, soil groups, stations), `model run`, `results export`; the build is in the gate, the run is `live`; on SFINCS v2.4.1 and `main` the infiltration of each half of the catchment is the SCS equation of its curve number (51.4 and 6.0 mm of 100 mm; 286.9 m3 in all, 286.9 expected) and the balance closes (0.002 %) |
| SFINCS BMI wrapper, coupler, command `model couple` (`engines/sfincs/{bmi,layout}.py`, `coupling/{coupler,worker,process}.py`, `operations/couple.py`) | done | ADR-0005; the coupled run is a worker process; live tests on the local `libsfincs` of SFINCS v2.4.1 (`ms`) and `main` (`m3s`); a wrong unit is flagged by the balance |
| Weekly live workflow for the library tests | planned | Next 6; ADR-0005 is written |
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
4. **`model build`, step two: wire the land cover in**: done (ADR-0008). The options
   `landcover`, `hsg`, `default_hsg`, `classes` and `building_raise_m` are in
   `BuildOptions`, the catalog (English and Polish texts, rules, an example), the schema
   (`landcover` key, `infiltration.hsg`) and the README; `manning.tif` and
   `curve_number.tif` are written beside the model. Checked by hand on the real data of
   the proof of concept (read only: `~/hydraulik-work/poznan_rataje_poc/data`, a 1 km
   square of Poznan at 10 m, group C, 40 mm in 2 h: 1.7 s to build, infiltration 66 %
   of the rain, balance residual -0.003 %; group D, 100 mm in 1 h, buildings raised by
   3 m: 1.6 m deepest, 0.12 km2 deeper than 0.1 m, residual 0.0002 %).
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
   `--enable-shared`; the workflow pulls no engine today) and the live run of
   `terrain download` once Kartograf has plain mode.
7. **Hand-off of Hydrolog's `route network` tables, USAGE and the last review**: not
   done; this is where to start.
   1. Finding (checked on Hydrolog `feature/routing-network`, 081fda2, 2026-10-25):
      `hydrolog route network --network-file N.json --inflows-file I.csv -o DIR` writes
      `<id>.csv` for every node with the header `time_min,discharge_m3s` at a regular
      step. That is the hydrograph table that `data.tables.read_hydrograph` and `swmm run
      --inflow F --inflow-node NODE` read today, so `swmm run` takes such a file as it
      is. Missing: a fixture from the real command (a small network: subcatchment A, a
      `lag` reach of 10 min, outlet; A = 0, 0.05, 0.15, 0.25, 0.2, 0.12, 0.06, 0.02, 0 m3/s
      at 5 min; keep the network document and the inflows beside the output) and a test
      that `run_network` accepts `A.csv`, `R1.csv` and `OUT.csv`.
   2. `model couple` has no inflow option. The plan does not call for one (steps 12 and 13
      name Kartograf, IMGWTools PMAXTP and Hydrolog hyetographs; the registry entry lists
      `BetaHietogram` and `EulerIIHietogram` only); Hydrolog's INTEGRATION.md and ADR-0010
      describe the hand-off from their side and call a reader in Hydraulik a `request`
      issue. If you want it: `Network.add_inflow` sets the rate, so the external rate must
      be summed with the exchange rate of a node in one call (`coupling/coupler.py`, after
      `network.add_inflow(name, taken / length_s)`); `couple()` takes a mapping node to
      a series with `at(time_s)`; `CouplerResult` records the volume given; `coupled_balance`
      needs its own `network_inflow_m3` term (`inflow_m3` is water that enters the
      surface); the job file of the worker carries the series; the catalog gets `--inflow`
      and `--inflow-node` as `swmm run` has them; a live test on `libsfincs` fills a
      network until it floods the street.
   3. `docs/USAGE.md` (optional by DOC-1.1; `tests/contract/test_docs_examples.py` runs
      its `bash` blocks): the task flow from `terrain download` to `results export`, the
      land-cover options, `swmm run` with a routed hydrograph, `model couple`.
   4. Last review of the branch: the README links of the Documentation section are
      relative (DOC-2.1 row 12 wants absolute ones), a search for leftovers (`not wired`,
      `TODO`, stale counts), and the gate on a clean checkout.

## Open questions

- Values of the land-class tables (`docs/LAND_COVER.md`), all mine and all to review:
  Manning `n` for shallow overland flow (forest 0.40, shrub 0.40, grass 0.15, arable
  0.06, roads 0.011, built-up 0.04 to 0.068) is several times the floodplain values of
  HEC-RAS; which set do you want as the default? Grass takes the curve number of pasture
  in fair condition (49 69 79 84), not of meadow (30 58 71 78); arable land that of row
  crops in poor condition; forest that of woods in good condition. The built-up classes
  use the TR-55 composite for a whole plot while roofs and roads are painted at 98 on
  top (a few points to the wet side); single-family land is taken as 1/4 acre lots,
  multi-family as 1/8 acre. The developed-land `n` values are Kalyanapu et al. (2009)
  through `r.manning`; the paper was not available. Roads without a width get 5 m,
  bridges and conventional lines are not painted, footpaths are not painted.
- Hydrograf's `core/cn_tables.py` maps the BDOT10k codes against the GUGiK
  classification: PTZB (`zabudowa`, built-up land) gets the meadow curve numbers, PTRK
  (`roślinność krzewiasta`, shrubs) and PTUT (`uprawa trwała`, permanent crops) get
  those of arable land, and PTTR (grass and arable land) is missing. This branch cannot
  change another project: it is a `request` issue for Hydrograf (DEV-17.5).
- `--building-raise-m` is 0 by default: the houses then do not obstruct the water and the
  roof roughness does not apply (a notice says so). A regular-grid SFINCS model has no
  building footprints, and raising the cells that are half or more under roofs is the
  usual way to make the flow go round them. Which default do you want for an urban
  model, and which height (3 m is what I used in the checks)?
- Kartograf has no plain mode yet (KartografAdopt7, 2026-10-25): `terrain download`
  cannot be exercised on the real tool until the data-output convention is implemented
  there; the field names of its plan and the ids of its items are the unknowns.
- Soil groups come from `soil hsg --depth 0-5cm` (SoilGrids, 250 m); is the top layer
  the depth you want, and is 250 m enough for plots?
- `model build` takes `recession_min` 60 and Manning `n` 0.04 when not given;
  `model couple` takes `rim_tolerance_m` 0.1, an exchange interval of 1 s, relaxation 1
  (`swmm_flooding`) or 0.1 (`coordinator`) and calls more than 20 sign changes of the
  exchange of a node an oscillation. The default `huthresh` of the model writer, 0.05 m,
  keeps water under 5 cm where it fell: a light rain does not run off (the live tests
  use 100 mm). Should `model build` expose `huthresh`?
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
- The author's uncommitted files overlap what this branch adds (`CLAUDE.md`,
  `docs/PROGRESS.md`, `.gitignore`) and the PoC package uses the same import name:
  decide the order in which the PoC and this branch reach `develop`.
- Skipped because they need the author: history rewrite (ADOPTION_PLAN phase 1),
  `main` as default branch, GitHub rulesets, Dependabot security updates and private
  vulnerability reporting (DEV-3.6, DEV-13.6, DEV-13.7), licence and CLA text, tags,
  pushes, committing the proof of concept from the worktree (DEV-3.5).
