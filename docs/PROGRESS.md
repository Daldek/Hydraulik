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
| Hydrolog hand-off: the tables of `hydrolog route network` as the inflow of `swmm run` and `model couple` (`--inflow`, `--inflow-node`) | done | ADR-0009; a fixture made by the real command (`tests/fixtures/hydrolog`), tests on the real SWMM, a live test that makes the tables again, and a live coupled run on both local SFINCS builds: 279 m3 fill a 0.15 m pipe until the manhole floods, the street holds 0.44 m, the balance closes (-0.23 %); contract tests against `hydrolog.testing` (ADR-0010) run in the gate |
| Producer pins of the `rainfall` extra | done | ADR-0011: Hydrolog `5fa22b35` (`feature/routing-schematic`, 1.0.0.dev0) and IMGWTools `6bd35a49` (`feature/data-output`, 3.0.0) by commit in `[tool.uv.sources]`, ranges `>=1.0.0.dev0,<2` and `>=3.0.0.dev0,<4` (REL-5.6); both commits are on GitHub, the tags replace them (Next 8). Gate on the earlier IMGWTools pin `3f7de36` (2026-10-25): 822 passed, 1 skipped (the python blocks of USAGE, none exist), 17 live deselected; `pytest -m live`: the Hydrolog test passed against the earlier pin `0719c41` (tables equal the fixture of 081fda2), 16 skip (SFINCS, `libsfincs` and Kartograf are not on this machine) |
| `docs/USAGE.md`, the README links, the last review | done | the task guide with offline examples run by `tests/contract/test_docs_examples.py`; README links absolute; no `TODO`, stub or alias left; three definitions without a caller removed; the agent surfaces are English whatever `LANG` is; `--inp` run live on both SFINCS builds; gate on a clean clone |
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
   own `--inp` is covered by a live test (the table of the bowl written as a SWMM input
   gives the volumes of the `--network` run within 1 %, SFINCS v2.4.1 and `main`); the
   SWMM clock of your input is set to 2000-01-01, so inflow series dated otherwise are
   lost; Windows and macOS are unchecked.
6. The weekly live workflow for the library tests (it has to build `libsfincs` with
   `--enable-shared`; the workflow pulls no engine today) and the live run of
   `terrain download` once Kartograf has plain mode.
7. **Hand-off of Hydrolog's `route network` tables, USAGE and the last review**:
   1. Done (commit `test(swmm)`): the tables of `hydrolog route network -o DIR` (checked
      on Hydrolog `feature/routing-network`, 081fda2, 2026-10-25) are the hydrograph
      table that `swmm run --inflow` reads. The fixture `tests/fixtures/hydrolog` was
      made by the real command; the tests read every table with the peak, time and
      volume that Hydrolog reports and run it through the real SWMM; the live test
      `test_hydrolog_live.py` makes the tables again (`uv run pytest -m live`: the
      `hydrolog` of the environment is the pinned head, and the test runs offline).
   2. Done (ADR-0009): `model couple --inflow FILE --inflow-node NODE`. The loop sums the
      discharge with the exchange of the node in one call, `couple()` takes a mapping
      from node to a series with `at(time_s)`, the worker's job file carries it,
      `coupled_balance` has `network_inflow_m3`, the result has `coupling.inflow`.
      Not built, and a question for the author: SFINCS discharge points (`srcfile`,
      `disfile`) as the place for a hydrograph that enters the surface.
   3. Done (`docs/USAGE.md`): the task flow from `terrain download` to `results export`,
      the land-cover options, `swmm run` with a routed hydrograph and `model couple`;
      `tests/contract/test_docs_examples.py` runs its `bash` blocks (the `--check`
      examples on the fixtures of the repository). The long walkthrough of the README
      moved there.
   4. Done: the last review of the branch. README links absolute; a search for `TODO`,
      `FIXME`, `not wired`, stub, placeholder, deprecated, shim and alias found nothing;
      stale counts none; every Markdown link resolves; `known_groups`, `chain_names` and
      `ExportVariable` had no caller and are gone; `commands list|schema|guide`, `config
      show`, `engines check` and the error document print English with `LANG=pl_PL` and
      no `HYDRAULIK_LANG` (Polish only in `i18n.pl` of the catalog and in human output,
      which defaults to `pl`); the gate passes on a clean clone.
8. **Resolving the pins** (ADR-0011). The `rainfall` extra pins Hydrolog
   `5fa22b35e5e1ec9076c41d0be04d2a99458f5049` (`feature/routing-schematic`) and IMGWTools
   `6bd35a49b329f99b591ffdee39367daec0e75af7` (`feature/data-output`) in
   `[tool.uv.sources]`; both commits are on GitHub, so `uv lock`, `uv sync --locked`, the CI
   jobs and a Docker build resolve them without a local git cache. When the tags exist, the
   release pull request narrows the ranges to `>=1.0.0,<2` and `>=3.0.0,<4`, replaces the two
   source entries with the tags (or removes them), runs `uv lock` and the gate, and records
   the fixtures again if the producers changed them.

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
- The Hydrolog hand-off (ADR-0009) has five questions for the author:
  1. A hydrograph that enters the SFINCS SURFACE (a river that flows into the 2D domain,
     discharge points `srcfile` and `disfile`) is not built; only the network inflow is
     (ADR-0009 option C). Do you want the surface variant?
  2. `--inflow` takes one node, like `swmm run`; the library takes a mapping. Should the
     option repeat for several nodes?
  3. Do not give the rain of the catchment that the hydrograph came from to the surface
     as well (the usage guide says so): no check can see the water counted twice.
  4. `--exchange-interval-s` stays 1 s. At 5 s a flooding manhole raises the
     `exchange_oscillation` notice (31 sign flips) and the street volume is 1.3 % off
     the 1 s run, but 75 min take 16 s instead of 81 s. Is 5 s acceptable as a
     documented speed option?
  5. Closed by ADR-0011: the `rainfall` extra pins Hydrolog `5fa22b35` (`feature/routing-schematic`)
     and IMGWTools `6bd35a49` (`feature/data-output`) by commit, so `route network` and
     `hydrolog.testing` are there and `tests/contract/test_hydrolog_testing.py` runs in the
     gate. Still open: the weekly live workflow (it needs `libsfincs` built with
     `--enable-shared`) that runs `test_hydrolog_live.py`, and the tags that replace the
     commits (Next 8).
- `flooded_m3` of a node in the coupled result is a GROSS volume when a manhole floods
  (2258 m3 for 279 m3 of hydrograph at 5 s: the street returns water whenever the pipe
  has room); the net volume is `exchanged_m3`. ADR-0009, the `CoupleDocument` docstring
  and the usage guide say so; decide whether the result should also carry a net volume
  per node under a name that cannot be misread.
- Skipped because they need the author: history rewrite (ADOPTION_PLAN phase 1),
  `main` as default branch, GitHub rulesets, Dependabot security updates and private
  vulnerability reporting (DEV-3.6, DEV-13.6, DEV-13.7), licence and CLA text, tags,
  pushes, committing the proof of concept from the worktree (DEV-3.5), and the merge
  below.

## Merge plan

State on 2026-10-25, read only. The main tree `~/workspace/Hydraulik` is on `develop` at
`de97009` (Initial commit: README, LICENSE, CONTRIBUTING, CONTRIBUTORS, `docs/CLA.md`).
`feature/sfincs-swmm` is 29 commits ahead of that same commit, so `develop` can
fast-forward to it. Nothing here was pushed, tagged or merged.

**The author's uncommitted files in the main tree and the branch**

| File | Main tree | Branch | Overlap |
|---|---|---|---|
| `.gitignore` | empty | 52 lines | path collision |
| `CLAUDE.md` | 25 lines, Polish, "Faza badawcza, brak kodu"; hydromt_sfincs adapter, container only | 114 lines, English, the working rules of the code | path collision; its statements are out of date |
| `docs/PROGRESS.md` | 50 lines, Polish: the research (2026-08-19) and brainstorming (2026-08-20) sessions, spec "waits for review" | the progress of this branch | path collision; their sessions exist nowhere on the branch |
| `docs/PRD.md`, `docs/SCOPE.md`, `docs/research/`, `docs/superpowers/` | the product requirements, the MVP scope, the feasibility report, the design spec | none | no collision; they stay as untracked files |
| `.claude/worktrees/poc-poznan-screening` | the proof of concept, branch `worktree-poc-poznan-screening` at `de97009`, uncommitted | none | see below |

Git refuses to overwrite the three colliding untracked files (tried in a scratch clone:
`git merge --ff-only` stops and names `.gitignore`, `CLAUDE.md`, `docs/PROGRESS.md`).
Procedure that worked in that clone: move those three aside, `git merge --ff-only
feature/sfincs-swmm`, and the other untracked files stay where they are. The branch's
`.gitignore` ignores `.claude/`, so the PoC worktree disappears from `git status`; it
stays registered as a worktree.

**Where the content contradicts the branch** (the author's decisions, not mine)

- Builder. `SCOPE.md` and the spec say HydroMT-SFINCS with subgrid behind an adapter
  (`hydromt_sfincs==2.0.0rc3`, GPL-3.0). The branch writes regular-grid models itself
  and has no `hydromt_sfincs` (ADR-0004, ECO-041), so no subgrid and no quadtree.
  Mountain flash floods, the main goal of the old `CLAUDE.md`, need what the branch
  lacks (the spec's pilot is the Biala Ladecka, July 1997).
- Sewer. `SCOPE.md` keeps the 1D sewer coupling out of the MVP and takes a constant
  capture capacity subtracted from the rain. The branch has the coupling, as an optional
  feature (decided 2026-10-24), and no constant capacity.
- Interface. The spec has a YAML scenario, a run directory with `metadata.json`, an
  `Engine` protocol and a Polish CLI; the branch has the Nogat command catalog, plain
  files and English machine output. Polish text exists in human output only.
- Licence and repository. The old `PROGRESS.md` says private repository without a
  licence; the old `CLAUDE.md` says MIT (2026-08-21); the branch is MIT.
- Aligned: BDOT10k, NMT and PMAXTP as inputs, buildings by raising the terrain
  (`--building-raise-m`), the Hydrolog hyetograph, `deltares/sfincs-cpu:sfincs-v2.4.1`.
- Not on the branch at all: the correction of the terrain and culvert detection, the
  division into catchments, the scenario matrix and the ensemble, passability and
  exposure, scenario cards, the QA report.

**The proof of concept** is a package with the SAME import name `hydraulik`, with
`hydromt_sfincs==2.0.0rc3` and `kartograf` as dependencies. Its paths collide with the
branch in `pyproject.toml`, `.gitignore`, `README.md` (modified there too),
`src/hydraulik/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, and a module of
the PoC is a package on the branch for `catalog`, `cli`, `data` and `terrain`.

**Recommended order**

1. Commit the PoC on its own branch from its worktree (DEV-3.5) and do not merge it into
   `develop`: two packages named `hydraulik` cannot live in one tree, and its GPL-3.0
   dependency is what the branch avoids on purpose.
2. Move `.gitignore` (empty), `CLAUDE.md` and `docs/PROGRESS.md` of the main tree aside
   and fast-forward `develop` to this branch. Then add the author's research and
   brainstorming sessions to `docs/PROGRESS.md` as an appendix (they are history), and
   commit `docs/PRD.md`, `docs/SCOPE.md`, `docs/research/` and `docs/superpowers/` in a
   docs commit, with a note in `SCOPE.md` for the contradictions above. The old
   `CLAUDE.md` is replaced by the branch's.
3. Decide for each contradiction above which side wins before more code: either the
   branch gains a subgrid adapter (the open `hydromt_sfincs` question) or `SCOPE.md` is
   changed to say what the branch is.
