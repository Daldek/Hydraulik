# Hydraulik: agent guide

> Builds SFINCS flood models from Kartograf terrain and Hydrolog or IMGWTools rainfall, runs the external SFINCS engine and couples it with an EPA SWMM sewer network. CLI and library.

## Purpose and scope

Use Hydraulik to turn terrain, land cover and a design rainfall into a SFINCS
flood model, run the external SFINCS engine, read the result with a mass
balance, and optionally couple SFINCS with an EPA SWMM sewer network.

Do not use it for operational forecasts, for river bathymetry or subgrid and
quadtree models (regular grids only), to download geodata (Kartograf), to look
up design rainfall depths (IMGWTools), to design a hyetograph shape alone
(Hydrolog) or to edit a sewer network (SWMM, QGIS).

## Install

- CLI: `uv tool install git+https://github.com/Daldek/Hydraulik`
- Library: `uv add git+https://github.com/Daldek/Hydraulik`
- Extras: `model` (rasters and vectors), `sfincs` (read results), `swmm`
  (pyswmm), `rainfall` (Hydrolog and IMGWTools), `all`. Python 3.12 or newer.
- The engines are not part of the package and are never installed by it; a
  missing one is `missing_dependency` and the hint names how to install it.

## Interfaces

A CLI (`hydraulik <group> <verb>`) and a Python library (the functions named in
the command index). There is no MCP server and no REST API.

## Workflow

1. Discover: `hydraulik commands list --json`, then
   `hydraulik commands schema --command '<group> <verb>' --json`.
2. Check: every command that writes has `--check`; it prints the plan (each
   target with the action `write`, `replace` or `conflict`) and writes nothing.
3. Run the command. Data is written only to `--output-dir` or `--output`, never
   to a default place; existing files are never overwritten without `--force`.
4. Read: the files are listed in `files[]` of the result (`path`, `size_bytes`,
   `sha256`, `status`); the numbers that matter are in the result document.

## Result envelope

`--json` prints exactly one document on stdout, `hydraulik-result/1`:
`schema`, `tool`, `version`, `command`, `check`, `status` (`ok`, `partial`,
`failed`, `cancelled`), `result` (the domain document, `hydraulik-<kind>/<n>`),
and, when present, `items` (per-unit outcomes) and `notices`. Logs go to stderr.
Exit code 0 is `ok`, 10 `partial`, 11 `failed`, 130 `cancelled`.

## Errors

On an error stdout is empty and the last line of stderr is the document
`hydraulik-error/1` (`code`, `title`, `message`, `hint`, `details`, `exit_code`).
Codes come from the shared registry
<https://github.com/Daldek/Nogat/blob/develop/standards/ERROR_REGISTRY.md>;
`details.reason` says more. Typical: `validation_error` (2, the option is named),
`not_found` (3), `conflict` (4, existing output, reason `output_exists`),
`missing_dependency` (6, an engine is not installed, the hint names the fix),
`calculation_error` (13, an engine run failed).

## Commands

- `commands list` (`hydraulik.list_commands`): List every command of Hydraulik with its options, effects and errors. Details: `hydraulik commands schema --command 'commands list'`.
- `commands schema` (`hydraulik.command_schema`): Describe one command of Hydraulik: options, result, effects and errors. Details: `hydraulik commands schema --command 'commands schema'`.
- `commands guide` (`hydraulik.render_guide`): Render AGENTS.md, llms.txt or the block for another repository's AGENTS.md. Details: `hydraulik commands schema --command 'commands guide'`.
- `config show` (`hydraulik.show_config`): Show every setting of Hydraulik with its value and where the value came from. Details: `hydraulik commands schema --command 'config show'`.
- `engines check` (`hydraulik.check_engines`): Report the engines and packages Hydraulik can use on this machine. Details: `hydraulik commands schema --command 'engines check'`.
- `rainfall build` (`hydraulik.build_rainfall`): Write a design rain as a rain table from a Hydrolog shape and a PMAXTP depth. Details: `hydraulik commands schema --command 'rainfall build'`.
- `model build` (`hydraulik.build_model`): Write a SFINCS model directory from your terrain, rain and optional rasters. Details: `hydraulik commands schema --command 'model build'`.
- `model run` (`hydraulik.run_model`): Run SFINCS on a model directory and read its maxima and water balance. Details: `hydraulik commands schema --command 'model run'`.
- `model couple` (`hydraulik.couple_model`): Run SFINCS and a SWMM sewer network together and book the water they exchange. Details: `hydraulik commands schema --command 'model couple'`.
- `results read` (`hydraulik.read_results`): Read the maxima, flooded areas and water balance of a SFINCS run. Details: `hydraulik commands schema --command 'results read'`.
- `results export` (`hydraulik.export_results`): Write a map of a run as a GeoTIFF, or the station series as a CSV table. Details: `hydraulik commands schema --command 'results export'`.
- `swmm run` (`hydraulik.run_network`): Run a SWMM sewer network with an inflow hydrograph and read its peaks. Details: `hydraulik commands schema --command 'swmm run'`.

## Typical flows

**Learn the interface without any engine**

1. See every command: `hydraulik commands list --json`
2. Read the options of one command: `hydraulik commands schema --command 'config show' --json`

**See how the settings were resolved**

1. List each setting with its value and source: `hydraulik config show --json`

**Find out what this machine can run**

1. List the engines and packages and what each command needs: `hydraulik engines check --json`

**Make the design rain of a model**

1. Write a rain table from a Hydrolog shape and a depth, or from a Hydrolog or IMGWTools document (add --check to plan, it fetches nothing): `hydraulik rainfall build --hietogram-type euler_ii --total-mm 40 --duration-min 120 --output ./rain.csv --json`

**Build a model from your terrain**

1. Write the model directory from elevation rasters and the rain table (add --check to plan): `hydraulik model build --dem ./nmt_1m.tif --dx-m 5 --rain ./rain.csv --output-dir ./model --json`

**Run a model and read the result**

1. Run SFINCS on a model directory (add --check to plan): `hydraulik model run --model ./model --output-dir ./run --json`
2. Read the maxima, flooded areas and water balance: `hydraulik results read --run ./run --json`
3. Write a flood map as a GeoTIFF: `hydraulik results export --run ./run --variable max_depth --output ./hmax.tif --json`

**Couple a model with a sewer network**

1. Run SFINCS and the network together; first `engines check --require 'model couple'` (add --check to plan): `hydraulik model couple --model ./model --network ./network.csv --output-dir ./coupled --json`

**Run a sewer network on its own**

1. Run a network table or a SWMM input with an inflow hydrograph (add --check to plan): `hydraulik swmm run --network ./network.csv --inflow ./inflow.csv --inflow-node J1 --output-dir ./swmm --json`

## Things not to do

- Do not bundle, download or install an engine from a script; install it
  yourself and tell Hydraulik where it is (the settings of `config show`).
- Do not pass `--force` unless replacing the files is intended.
- Do not read results from a failed run; the error says why it failed.
- Do not edit this file: it is generated by `hydraulik commands guide`.

Developing this repository? Read CLAUDE.md.
