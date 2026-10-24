# CLAUDE.md

## Project

Hydraulik builds SFINCS flood models from terrain, land cover and design rain,
runs the external SFINCS engine, and optionally couples it with an EPA SWMM
sewer network. Profile: `tool` (DEV §1), registry status `research`. Overview:
[README.md](README.md).

SFINCS (GPL-3.0 source, Deltares Freeware binaries and image), `hydromt_sfincs`
(GPL-3.0) and SWMM are external: Hydraulik is MIT, finds the engines on the
user's machine and never bundles, installs or redistributes them (ECO-041,
DEV-13.5). Nothing in this repository imports `hydromt_sfincs`.

## Critical rules

- Without the author's approval in this session: no merges, tags, releases,
  force-pushes or history rewrites (DEV-3.3). Work on a topic branch from
  `develop`; do not push.
- Change only this repository; a need in another project is a GitHub issue
  labelled `request` in that project (DEV-17.5). Do not edit the author's
  uncommitted files in the main checkout (`CLAUDE.md`, `docs/PRD.md`,
  `docs/SCOPE.md`, `docs/research/`, `docs/superpowers/`, the PoC worktree).
- Never bundle, download or `pip install` an engine from the code. Detect it
  (`hydraulik engines check`), and raise `missing_dependency` with the install
  hint when it is absent.
- Data is written only through `--output-dir` and `--output` (DEV-19.1) with
  the plain-write rules of `hydraulik.output` (DEV §19). Hydraulik has no store.
- Every error is a registry code (`schemas/nogat/error_registry.json`);
  precision goes to `details.reason` (ERR-1). Never invent a code.
- Never edit generated files: `src/hydraulik/_errors.py`
  (`uv run scripts/generate_errors.py`), `AGENTS.md` and `llms.txt`
  (`hydraulik commands guide`); a contract test compares each with its source.
- Unit tests never touch the network or an engine: use `tests/fixtures/` and the
  fake engines of `tests/`. A test that needs an engine or the network carries
  `@pytest.mark.live` (DEV-10.1) and skips itself when the engine is missing.
- Units are in names: `dx_m`, `discharge_m3s`, `intensity_mm_h` (DEV-8.2).
- No shims, aliases or deprecated paths; migrate every caller (ECO-020).

## Environment and commands

```
uv sync --locked --all-extras      # environment in .venv (DEV-6.2, DEV-6.3)
scripts/gate.sh                    # before every commit (DEV-7.6)
uv run pytest                      # tests without live (default)
uv run pytest -m live              # tests that use the real engines
uv run scripts/generate_errors.py  # regenerate src/hydraulik/_errors.py
uv run hydraulik commands guide --format agents   # regenerate AGENTS.md
```

Engines (settings in `nogat.toml` `[hydraulik]` or environment, see README):
`HYDRAULIK_SFINCS_EXE`, `HYDRAULIK_SFINCS_IMAGE`, `HYDRAULIK_SFINCS_LIBRARY`
(shared library for the coupling), `HYDRAULIK_KARTOGRAF_EXE`.

## Code map

```
src/hydraulik/
  __init__.py, exceptions.py, _errors.py   public API, errors (generated registry)
  settings.py                              nogat.toml, HYDRAULIK_*, config show
  output.py                                plain-mode writer (preflight, staging, files[])
  catalog/, cli/, agent_guide.py           command catalog, envelope, CLI, AGENTS.md
  engines/{detect,sfincs,swmm}             find, write, run and read the engines
  coupling/                                exchange laws, coupler, balance, diagnostics
  data/                                    Kartograf CLI, IMGWTools PMAXTP, Hydrolog rain
  terrain/, model/                         DEM and land cover to model files
  schemas/                                 JSON Schemas of the result documents
tests/{unit,integration,contract,fixtures}
```

## Documentation map

| Task | Read |
|---|---|
| Start a session | `docs/PROGRESS.md`, `docs/plans/` |
| What earlier work found about SFINCS and SWMM | `docs/plans/2026-10-24-sfincs-swmm-extraction.md` |
| Why a decision was taken | `docs/DECISIONS.md` and `docs/decisions/` |
| Change the agent interface | the Nogat standard, AGI §2 to §4 and §7 |

## Session workflow

Start: this file, `docs/PROGRESS.md`, `git status`, `git log --oneline -10`,
the open `request` issues of the repository (DEV-17.1). Plan first for a change
of a public interface or of more than one module (DEV-17.4). End: update
`docs/PROGRESS.md` and `docs/CHANGELOG.md` (DEV-17.3, DOC-7.2), run the gate.

## Cross-project context

Registry entry: <https://github.com/Daldek/Nogat/blob/develop/ecosystem.yaml>
(Hydraulik). Kartograf is called as a CLI subprocess, IMGWTools and Hydrolog as
libraries, all optional.

## Deviations

- DEV-17.4: the plan `docs/plans/2026-10-24-sfincs-swmm-integration.md` has no
  `Approved:` line; the work started on the coordinator's assignment.
- DEV-3.1: `main` is not yet the default branch on GitHub (author's setting).
- DEV-13.7: `SECURITY.md` exists; private vulnerability reporting is a GitHub
  setting for the author.
- ERR-3, AGI-4.1: the copies in `schemas/nogat/` come from Nogat commit
  `cc656e7`, because the tag `std-2.1` does not exist yet.
- DEV-10.6: not applicable, Hydraulik provides no store or file format that
  another project reads.
- AGI §5, §6: not applicable, the registry declares no MCP server and no REST API.
