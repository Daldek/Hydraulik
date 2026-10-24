# Progress

## Status

| Component | State | Note |
|---|---|---|
| Tooling: uv, gate, CI, live workflow, Dependabot | done | `scripts/gate.sh`, `.github/` |
| Extraction note and plan | done | `docs/plans/2026-10-24-sfincs-swmm-*.md`; the plan awaits `Approved:` |
| Error registry, settings, plain output writer | done | `_errors.py`, `settings.py`, `output.py`; ADR-0001 |
| Command catalog, envelope, CLI, AGENTS.md, llms.txt, schemas | done | commands `commands list\|schema\|guide`, `config show` |
| Exchange law, diagnostics, balance (`coupling/`) | done | pure functions from the experiment |
| SWMM network table, INP writer and reader, report parser | done | ADR-0002; runs on the real SWMM in `tests/integration` |
| SFINCS regular-grid writer (`engines/sfincs/model.py`) | done | ADR-0004; the live test passes on SFINCS v2.4.1 and main |
| Engine detection (`engines/detect.py`) | done | ADR-0003; no command uses it yet |
| SFINCS runner, results reader, BMI wrapper | planned | rest of plan step 10 |
| Coupler (BMI plus pyswmm, volume exchange) | planned | plan step 11 |
| Data adapters: Kartograf CLI, IMGWTools PMAXTP, Hydrolog hyetograph | planned | plan step 12 |
| Commands `engines check`, `rainfall build`, `terrain download`, `model build`, `model run`, `results read`, `results export` | planned | plan step 13 |
| README and live tests for the rest | planned | plan step 14 |
| Phase 2 items that need the author | blocked | see Open questions |

## Next

1. `src/hydraulik/engines/sfincs/run.py`: run a model directory with the install of
   `detect_sfincs` (executable, or `docker run --rm -v <dir>:/data --user <uid>:<gid>
   <image>`); stream the log, parse `NN% complete`, set `OMP_NUM_THREADS`, enforce
   `sfincs.timeout_s`; a non-zero exit is `EngineError` (reason `engine_failed`)
   carrying the log tail. Run inside the staging directory of `output.Writer`.
2. `engines/sfincs/results.py` (netCDF4): `hmax`, `zsmax`, `vmax`, `cumprcp`, `cuminf`
   from `sfincs_map.nc` (row 0 is the south row, masked below `huthresh`, fill value
   -99999), `point_zs` from `sfincs_his.nc`; the balance with the masking caveat of
   ADR-0004; GeoTIFF export of the maximum depth (rasterio).
3. `engines/sfincs/bmi.py`: the ctypes wrapper of the old `coupler.py::SfincsBmi`
   (`initialize`, `update_until`, `get_value_ptr`, `get_sfincs_cell_index`,
   `get_sfincs_cell_area`, `set_logical("qext")`) with `sfincs.qext_unit` (v2.4.1:
   `zs += qext * dt`, so divide the flow by the cell area).
4. Plan step 11, the coupler: one loop of the extraction note 3 over protocols for the
   surface and the network, with fakes in `tests/` and a live test on both SFINCS builds
   plus pyswmm (the three-node case of `tests/fixtures/swmm/network_chain.csv`);
   modes `swmm_flooding` (EXTRAN, `SurDepth` 0, default) and `coordinator` (SLOT,
   relaxation 0.1); automatic oscillation guard, off by default (README 3.9);
   `rim_tolerance_m` for user networks; per-cell cap when several nodes share a cell.
5. Plan steps 12 to 14. Every new command: declare it in `catalog/commands.py` with
   its Polish texts, add the function to `operations/` and `__all__`, regenerate
   `AGENTS.md` and `llms.txt`, add the flow to `agent_guide.FLOWS`, extend the README
   Capabilities table. Domain schemas go to `src/hydraulik/schemas/`.
6. Local engines for the live tests: build SFINCS with gfortran and netCDF-Fortran
   (`./configure --enable-shared`, plain `make`, extraction note 7) and set
   `HYDRAULIK_SFINCS_EXE` and `HYDRAULIK_SFINCS_LIBRARY`.

## Open questions

- Approve `docs/plans/2026-10-24-sfincs-swmm-integration.md` (adds the `Approved:`
  line, DEV-17.4); the ADRs are `proposed` until then.
- Q1: is the SWMM coupling part of the product? SCOPE.md (the author's, uncommitted)
  keeps full 1D sewer coupling out of the MVP.
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
