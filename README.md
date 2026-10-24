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

## Engines are external

Hydraulik never bundles, installs or downloads an engine (ECO-041). It looks for
them and says what is missing:

| Engine | Found through | Licence |
|---|---|---|
| SFINCS executable | `HYDRAULIK_SFINCS_EXE`, `[hydraulik] sfincs_exe`, `sfincs` on `PATH`, or the Docker image `HYDRAULIK_SFINCS_IMAGE` | source GPL-3.0; executables and the `deltares/sfincs-cpu` image Deltares Freeware (no redistribution) |
| SFINCS shared library (coupling only) | `HYDRAULIK_SFINCS_LIBRARY`, built by you from the SFINCS sources with `--enable-shared` | as above |
| SWMM | the `swmm` extra (`pyswmm`, with `swmm-toolkit`) | BSD-2-Clause, CC0-1.0 and MIT or Apache-2.0 |
| `hydromt_sfincs` | not used by Hydraulik; install it yourself if you build subgrid models with it | GPL-3.0 |

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
