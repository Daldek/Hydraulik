# Hydraulik: SFINCS flood models with an optional SWMM sewer coupling

`Hydraulik` builds 2D flood models for the SFINCS engine from terrain, land
cover and design rainfall, runs the external engine and reads its results, and
can couple SFINCS with an EPA SWMM sewer network through the SFINCS BMI. It is a
command-line tool and a Python library for hydrologists and for AI agents; it
belongs to the Nogat ecosystem of Polish and Czech geodata and hydrology tools.

## When to use

- Screen pluvial (rain-on-grid) flooding of a catchment or an urban area on a
  regular grid, from a digital elevation model (DEM, Polish NMT), BDOT10k land
  cover and a design hyetograph.
- Check how a sewer network that surcharges returns water to the street, by
  coupling a SWMM model to the SFINCS surface model.

## When not to use

- Operational forecasts or the design of structures: the results are a
  screening, not a calibrated model.
- Fluvial flooding that needs river bathymetry, or SFINCS subgrid and quadtree
  models: this version writes regular-grid models only.
- Downloading geodata (use Kartograf), design rainfall depths (use IMGWTools),
  hydrographs and hyetograph shapes (use Hydrolog).
- Sewer design or network editing (use SWMM, QGIS or PCSWMM).

## Install

```
uv tool install git+https://github.com/Daldek/Hydraulik          # CLI
uv add git+https://github.com/Daldek/Hydraulik                   # library
```

Python 3.12 or newer. Extras: `model` (rasters and vectors), `sfincs` (read
results), `swmm` (pyswmm), `rainfall` (Hydrolog and IMGWTools), `all`.

### Settings

Settings come from, in order: a command-line option, `HYDRAULIK_<KEY>` (the
shared key `lang` also `NOGAT_LANG`), the `[hydraulik]` table of `nogat.toml` in
the user configuration folder (or the file in `NOGAT_CONFIG`), the default. The
key `sfincs.exe` is the variable `HYDRAULIK_SFINCS_EXE`. `hydraulik config show`
lists every setting with its value and source. Hydraulik needs no credentials and
keeps no store or cache.

| Variable | Meaning | Default |
|---|---|---|
| `NOGAT_CONFIG` | settings file | `nogat.toml` in the user configuration folder |
| `HYDRAULIK_LANG`, `NOGAT_LANG` | language of human-readable output, `pl` or `en` | `pl` |
| `HYDRAULIK_LOG_LEVEL` | `debug`, `info`, `warning`, `error` | `warning` |
| `HYDRAULIK_SFINCS_EXE` | SFINCS executable | `sfincs` on `PATH` |
| `HYDRAULIK_SFINCS_IMAGE` | Docker image used when there is no executable | `deltares/sfincs-cpu:sfincs-v2.4.1` |
| `HYDRAULIK_SFINCS_LIBRARY` | `libsfincs` for the coupling | none |
| `HYDRAULIK_SFINCS_QEXT_UNIT` | unit of `qext` in that library, `m3s` or `ms` | `m3s` |
| `HYDRAULIK_SFINCS_TIMEOUT_S`, `HYDRAULIK_SFINCS_THREADS` | run timeout, OpenMP threads | 7200, all cores |
| `HYDRAULIK_DOCKER_EXE` | Docker command | `docker` |
| `HYDRAULIK_KARTOGRAF_EXE`, `HYDRAULIK_KARTOGRAF_TIMEOUT_S` | Kartograf command, download timeout | `kartograf` on `PATH`, 3600 |

### Engines are external

Hydraulik never bundles, installs or downloads an engine (ECO-041). It looks for
them and says what is missing:

| Engine | Found through | Licence |
|---|---|---|
| SFINCS executable | `HYDRAULIK_SFINCS_EXE`, `[hydraulik] sfincs_exe`, `sfincs` on `PATH`, or the Docker image `HYDRAULIK_SFINCS_IMAGE` | source GPL-3.0; executables and the `deltares/sfincs-cpu` image Deltares Freeware (no redistribution) |
| SFINCS shared library (coupling only) | `HYDRAULIK_SFINCS_LIBRARY`, built by you from the SFINCS sources with `--enable-shared` | as above |
| SWMM | the `swmm` extra (`pyswmm`, with `swmm-toolkit`) | BSD-2-Clause, CC0-1.0 and MIT or Apache-2.0 |
| `hydromt_sfincs` | not used by Hydraulik; install it yourself if you build subgrid models with it | GPL-3.0 |

## Quick start

```bash
hydraulik commands list --json
hydraulik commands schema --command 'config show' --lang en
hydraulik config show --lang en
```

The first call prints the command catalog `hydraulik-commands/1` inside the result
envelope `hydraulik-result/1`; the others describe one command and show how every
setting was resolved. In Python:

```python
import hydraulik

catalog = hydraulik.list_commands().to_dict()
print([command["name"] for command in catalog["commands"]])
```

Every command prints one JSON document with `--json`; logs go to stderr. On an
error stdout is empty and the last line of stderr is the error document.

The terrain, the BDOT10k land cover and the soil groups of an area come from Kartograf,
which Hydraulik starts as a program. It needs a Kartograf that writes plain files with
`--output-dir` (the data-output convention of the Nogat ecosystem); one without it is
refused, and `engines check` says which you have:

```sh
hydraulik engines check --require 'terrain download'
hydraulik terrain download --bbox 361500,504000,363000,505500 --crs EPSG:2180 \
    --output-dir ./data
```

Each product goes to its own sub-directory (`data/elevation`, `data/landcover`,
`data/soil`). Before the first byte the plan of every product is read, and a file that
exists (without `--force`) fails the whole call. The result lists the files with their
`sha256`, and the sources with their licences and the attribution to print: plain files
carry no sidecar. A product that fails after another succeeded gives status `partial`.

A design rain for a model is a Hydrolog hyetograph shape with a depth that you give or
the PMAXTP depth of IMGW-PIB, from the document of `imgw pmaxtp fetch --json` or, with
the network and IMGWTools, for a point:

```bash
hydraulik rainfall build --hietogram-type euler_ii --total-mm 40 --duration-min 120 --output ./rain.csv --check
```

```sh
hydraulik rainfall build --hietogram-type euler_ii --latitude 52.23 --longitude 21.01 \
    --probability-percent 10 --duration-min 60 --output ./rain.csv
hydraulik rainfall build --hietogram ./hietogram.json --output ./rain.csv
```

The second call converts the document of `hydrolog precip hietogram --json`. The table
has `time_min,depth_mm`; a PMAXTP depth comes with a notice to name IMGW-PIB as its
source.

A model is built from your terrain (GeoTIFFs in a metric CRS, for Poland EPSG:2180), the
rain table and, when you have them, a Manning raster and a curve-number raster (or the
SCS retention `S` in mm):

```sh
hydraulik model build --dem ./nmt_1m.tif --dx-m 5 --rain ./rain.csv \
    --curve-number-raster ./cn.tif --outlet ./outlet.gpkg --output-dir ./model
```

The grid is aligned to `--dx-m`; a terrain finer than the grid is averaged to it. The
domain is every cell with elevation, or `--geometry` (a polygon), or `--bbox` with
`--crs`; a cell of the domain without elevation or Manning `n` is an error, and where
the curve number has gaps there is no infiltration (a warning says how many cells).
Without `--outlet` the boundary is closed and all the rain stays in the model. Then a
run and its results:

```sh
hydraulik engines check --require 'model run'
hydraulik model run --model ./model --output-dir ./run
hydraulik results read --run ./run
hydraulik results export --run ./run --variable max_depth --output ./hmax.tif
```

`model run` writes `sfincs_map.nc`, `sfincs_his.nc` and `sfincs.log` only when SFINCS
finished and its map can be read. The water balance is `rain - infiltration - stored =
residual`: in a closed model the residual is the error and above 1 % of the rain it is
flagged; with outflow cells it is the water that left.

A sewer network on its own, from a network table (one row per node) and the inflow
hydrograph that Hydrolog gives (`time_min,discharge_m3s`):

```sh
hydraulik swmm run --network ./network.csv --inflow ./inflow.csv --inflow-node J1 \
    --output-dir ./swmm
```

`swmm run` writes `network.inp` and `network.rpt` and reports the water balance of
SWMM, the peaks of every node and conduit and, as a notice, a continuity error above
5 %. `--inp` runs your own SWMM input (SI units) instead of a table.

A model and a sewer network together (optional, it needs the SFINCS shared library that
you build yourself with `--enable-shared`, `HYDRAULIK_SFINCS_LIBRARY`, and `pyswmm`):

```sh
hydraulik engines check --require 'model couple'
hydraulik model couple --model ./model --network ./network.csv --output-dir ./coupled
```

Every `--exchange-interval-s` the nodes of the network take water from the SFINCS cell
they lie on and hand back what SWMM floods out of a full node; the volumes are exchanged,
not the rates, so the interface adds no mass error. The result books the water (rain,
infiltration, surface, network, outfall, exchange) and flags a residual above 1 %. Set
`HYDRAULIK_SFINCS_QEXT_UNIT=ms` for SFINCS v2.4.1 and `m3s` for newer builds: a wrong
unit shows as a balance that does not close. The coupled run happens in a process of its
own, because SFINCS keeps its state in global variables. It is a screening: the
description of the inlets is the main uncertainty.

## Capabilities

| Task | CLI | Python function | Writes |
|---|---|---|---|
| List the commands | `commands list` | `hydraulik.list_commands` | nothing |
| Describe one command | `commands schema` | `hydraulik.command_schema` | nothing |
| Render AGENTS.md, llms.txt or the block for another repository | `commands guide` | `hydraulik.render_guide` | `--inject` only |
| Show the settings and their sources | `config show` | `hydraulik.show_config` | nothing |
| Report the engines and packages found, and what each command needs | `engines check` | `hydraulik.check_engines` | nothing |
| Fetch the terrain, land cover and soil groups of an area (Kartograf) | `terrain download` | `hydraulik.download_terrain` | `--output-dir` |
| Write a SFINCS model directory from terrain, rain and optional rasters | `model build` | `hydraulik.build_model` | `--output-dir` |
| Run SFINCS on a model directory, read its maxima and water balance | `model run` | `hydraulik.run_model` | `--output-dir` |
| Read the maxima, flooded areas and water balance of a run | `results read` | `hydraulik.read_results` | nothing |
| Write a map as a GeoTIFF or the station series as a CSV table | `results export` | `hydraulik.export_results` | `--output` |
| Write a design rain as a rain table (Hydrolog shape, PMAXTP depth) | `rainfall build` | `hydraulik.build_rainfall` | `--output` |
| Run a SWMM sewer network with an inflow hydrograph, read its peaks | `swmm run` | `hydraulik.run_network` | `--output-dir` |
| Run SFINCS and a SWMM network together, book the water they exchange | `model couple` | `hydraulik.couple_model` | `--output-dir` |

Generic drivers for any command: `hydraulik.validate_command`,
`hydraulik.check_command`, `hydraulik.run_command`.

## For AI agents

- [llms.txt](https://raw.githubusercontent.com/Daldek/Hydraulik/main/llms.txt) and
  [AGENTS.md](https://raw.githubusercontent.com/Daldek/Hydraulik/main/AGENTS.md)
  are generated by `hydraulik commands guide --format llms|agents`.
- `hydraulik commands list --json` is the catalog; `hydraulik commands schema
  --command '<group> <verb>' --json` is one command with its options, effects,
  errors and examples. No engine, network or credentials are needed.
- Results are `hydraulik-result/1` envelopes, errors `hydraulik-error/1`.
- Every command that writes has `--check`, which prints the plan and writes
  nothing; data goes only to `--output-dir` or `--output`, and existing files are
  replaced only with `--force`.

## Related tools

- [Kartograf](https://github.com/Daldek/Kartograf) downloads the terrain and land
  cover that a model is built from; Hydraulik calls it as a program.
- [IMGWTools](https://github.com/Daldek/IMGWTools) gives design rainfall depths
  (PMAXTP) and [Hydrolog](https://github.com/Daldek/Hydrolog) the hyetograph
  shapes; Hydraulik uses both as libraries.
- Prefer HydroMT-SFINCS (GPL-3.0) for SFINCS models with subgrid tables or
  quadtree grids, and D-Flow FM or PCSWMM when the 1D and 2D models must be
  solved implicitly in one engine.

## Errors and exit codes

Codes come from the shared registry
([ERROR_REGISTRY](https://github.com/Daldek/Nogat/blob/develop/standards/ERROR_REGISTRY.md));
`details.reason` says more. Exit 0 is `ok`, 10 `partial`, 11 `failed`, 130
`cancelled`.

| Code | Exit | Typical cause and fix |
|---|---|---|
| `validation_error` | 2 | an option is unknown, mistyped or out of range; the error names it and lists the allowed values |
| `not_found` | 3 | a file or directory does not exist; check the path |
| `conflict` | 4 | an output exists (`output_exists`): use `--force` or another `--output-dir` |
| `missing_dependency` | 6 | an engine or an extra is not installed; the hint names the fix |
| `calculation_error` | 13 | an engine run failed; the error carries the end of its log |

## Data and licensing

Hydraulik is MIT. Data keeps its own terms: NMT and BDOT10k from GUGiK (free
reuse with attribution), PMAXTP from IMGW-PIB (attribution required), OpenStreetMap
under ODbL. Results are written only where you point `--output-dir` or `--output`.

## Documentation

- [CHANGELOG](docs/CHANGELOG.md)
- [Extraction note](docs/plans/2026-10-24-sfincs-swmm-extraction.md): what the
  earlier SFINCS and SWMM work decided, built and found
- [Plan](docs/plans/2026-10-24-sfincs-swmm-integration.md)

## Development

See [CLAUDE.md](CLAUDE.md). The gate is `scripts/gate.sh`; contributions follow
[CONTRIBUTING.md](CONTRIBUTING.md).

## Status, licence, author

Pre-alpha (registry status `research`). MIT licence, see [LICENSE](LICENSE).
Author: Piotr de Bever.
