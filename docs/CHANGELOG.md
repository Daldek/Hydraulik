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
