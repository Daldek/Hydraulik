# Plan: SFINCS and SWMM integration

Status: proposed, awaiting the author's `Approved:` line (DEV-17.4). The work
on `feature/sfincs-swmm` started on the coordinator's assignment of 2026-10-24
relayed from the author, before that line exists; CLAUDE.md lists the
deviation.

Requirements: DEV §5, §10, §11, §18, §19, AGI §2 to §4, §7, ERR §3, ECO-041,
ECO-051. Input: the [extraction note](2026-10-24-sfincs-swmm-extraction.md).

## Goal

A `hydraulik` package and CLI that
1. builds a SFINCS regular-grid model from terrain, land cover and design
   rain;
2. runs the external SFINCS engine and reads its results with a mass balance;
3. builds a SWMM sewer network and couples it with SFINCS through the SFINCS
   BMI and pyswmm, exchanging volumes;
4. offers every operation through one command catalog, as CLI and Python
   library, with the shared envelope, error codes and `--check`;
5. writes data only through `--output-dir` and `--output` (DEV-19.1);
6. is tested offline with fixtures and fake engines, and with `live` tests
   that use the real engines when they are present.

## Options

| Option | Verdict |
|---|---|
| A. Keep the experiment scripts under `experiments/` | Rejected: Polish, module globals, `chdir`, no tests, not importable |
| B. Re-apply the experiment as a package, engines behind small protocols | Chosen |
| C. Build the SFINCS model with `hydromt_sfincs` (the PoC way) | Rejected for the core: a GPL-3.0 dependency and about 90 more packages in every install; possible later as an extra for subgrid models (ADR-0004) |
| D. Own writer for the regular-grid model, formats checked against the v2.4.1 source | Chosen (ADR-0004). No subgrid, no quadtree |
| E. SWMM network from a user-supplied `.inp` plus a generated chain from a table | Chosen (ADR-0002). Importing GIS sewer layers is not offered |
| F. Coupling: explicit volume exchange through BMI and pyswmm | Chosen (ADR-0005). An implicit scheme needs state rollback that neither interface offers; a file exchange has no mass guarantee; SFINCS's own `urban_drainage` module is a lumped sink, not a network |
| G. Engines are found, never installed or bundled: setting, `PATH`, Docker | Chosen (ADR-0003) |
| H. No store: every writing command takes `--output-dir` or `--output` | Chosen (ADR-0001) |

## Decision

B, D, E, F, G and H, recorded as ADR-0001 to ADR-0005 in `docs/DECISIONS.md`
(each ADR is added by the step that implements its decision). The SWMM coupling
is an optional feature of the package, not a product decision (extraction note
2, decision 9).

## Steps

One commit per step, the gate green before each:

1. Tooling and repository files (done).
2. This plan and the extraction note.
3. `CLAUDE.md`, README, PROGRESS, CHANGELOG and the DECISIONS index.
4. Error registry: vendored copies, generated `_errors.py`, `HydraulikError`.
5. Settings: `nogat.toml`, `HYDRAULIK_*`, `config show`.
6. Plain output writer: preflight, staging, `--force`, `files[]`.
7. Command catalog, envelope, CLI, generated AGENTS.md and llms.txt, schemas.
8. Exchange laws and diagnostics (pure functions).
9. SWMM: network model, INP writer and reader, report parser, runner.
10. SFINCS: model writer, runner, results reader, mass balance, BMI wrapper.
11. The coupler.
12. Data adapters: Kartograf CLI, IMGWTools PMAXTP, Hydrolog hyetographs.
13. Model build from terrain and land cover; commands `model build`, `model run`,
    `results read`, `results export`.
14. Live tests and the weekly workflow; README and PROGRESS final.

## Results

State on 2026-10-24, when the run stopped at its request budget. Steps 1 to 9
are done, the writer, the engine detection and the live test of step 10 are done;
the rest of step 10 (runner, results reader, BMI wrapper, the commands) and steps
11 to 14 are open. `docs/PROGRESS.md` gives the starting point of each. Verified on
real engines: the SWMM input runs on SWMM 5.2.4 (pyswmm 2.2.0); the SFINCS model
runs on SFINCS v2.4.1 and on `main` and reproduces the SCS equation. Not verified:
the coupling itself, the Kartograf, IMGWTools and Hydrolog adapters, Windows and macOS.
