# Using Hydraulik

This guide follows the tasks, in the order of a flood study. The options of every
command are not repeated here: `hydraulik commands schema --command '<group> <verb>'`
lists them with their ranges, defaults, rules and errors, and `hydraulik <group> <verb>
--help` prints the same for a person. Install, settings and the engines Hydraulik looks
for are in the [README](../README.md).

Rules that hold for every command:

- A command that writes has `--check`: it prints the plan (the files it would write,
  the steps, `blockers` for whatever is missing) and writes nothing. Exit 0 with a
  blocker means the plan is fine and the machine is not ready.
- Data goes only to `--output-dir` (a directory) or `--output` (one file). A file that
  exists stops the call, before the first byte is written, unless you give `--force`.
- `--json` prints one `hydraulik-result/1` envelope on stdout; logs go to stderr. On an
  error stdout is empty and the last line of stderr is the `hydraulik-error/1` document,
  with `code`, `details.reason` and a `hint`.
- Human-readable text is Polish unless `--lang en` or `HYDRAULIK_LANG=en`; JSON is
  English always.
- Times in every table are minutes elapsed since the start of the run
  (`time_min`), discharges are `m3/s`, depths `mm`, coordinates metres in the CRS of the
  model.

The examples with `--check` below run as they are in a clone of the repository (the
test fixtures supply the small inputs) and are run by the test suite. The others need
data and engines of your own.

## 1. Check what the machine has

```sh
hydraulik engines check
hydraulik engines check --require 'model run'
```

The first call lists the SFINCS executable (or Docker image), the SFINCS library, the
Kartograf command and the Python packages found, and for every command what it still
needs. `--require` makes the exit code non-zero when that command cannot run. Hydraulik
does not install engines; see "Engines are external" in the README.

## 2. Get the terrain, the land cover and the soil

Kartograf downloads the digital elevation model (DEM, Polish NMT), the BDOT10k land
cover and the hydrologic soil groups of an area. Hydraulik starts it as a program, so
it must be a Kartograf that writes plain files with `--output-dir`.

```bash
hydraulik terrain download --bbox 361500,504000,363000,505500 --crs EPSG:2180 --output-dir ./data --check
```

Without `--check` each product goes to its own sub-directory, `data/elevation`,
`data/landcover` and `data/soil`. The result lists the files with their `sha256`, the
sources with their licences and the attribution to print. A product that fails after
another succeeded gives status `partial`; `--products` selects some of the three. Your
own rasters work as well, so this step is optional. A Kartograf without plain files is
refused, and `engines check --require 'terrain download'` says which one you have.

## 3. Make the design rain

A rain table has the columns `time_min,depth_mm`. Its shape is a Hydrolog hyetograph
type, its depth is yours or the PMAXTP depth of IMGW-PIB.

```bash
hydraulik rainfall build --hietogram-type euler_ii --total-mm 40 --duration-min 120 --output ./rain.csv --check
hydraulik rainfall build --pmaxtp tests/fixtures/rain/pmaxtp_fetch.json --hietogram-type euler_ii --duration-min 60 --probability-percent 10 --output ./rain.csv --check
```

The second call takes the depth for a 60 minute rain of probability 10 % from the
document of `imgw pmaxtp fetch --json`; with `--latitude` and `--longitude` instead of
`--pmaxtp` and with IMGWTools installed it fetches the depth for a point (that needs the
network). A PMAXTP depth comes with a notice to name IMGW-PIB as its source. A shape
that Hydrolog already computed (`hydrolog precip hietogram --json`) goes in with
`--hietogram FILE`.

```sh
hydraulik rainfall build --hietogram-type euler_ii --latitude 52.23 --longitude 21.01 \
    --probability-percent 10 --duration-min 60 --output ./rain.csv
hydraulik rainfall build --hietogram ./hietogram.json --output ./rain.csv
```

## 4. Build the model

The terrain must be a GeoTIFF in a metric CRS (for Poland EPSG:2180). The grid is
aligned to `--dx-m`; a finer terrain is averaged to it, and the grid has at most 25
million cells. The domain is every cell with elevation, or `--geometry` (a polygon), or
`--bbox` with `--crs`. A cell of the domain without elevation or Manning `n` is an error.

With your own rasters, and a boundary that is closed (all rain stays in the model):

```sh
hydraulik model build --dem ./nmt_1m.tif --dx-m 5 --rain ./rain.csv \
    --curve-number-raster ./cn.tif --output-dir ./model
```

`--manning N` or `--manning-raster` set the roughness (0.04 without them),
`--curve-number-raster` or `--retention-mm-raster` switch infiltration on (a gap in the
raster means no infiltration there, and a warning counts the cells), `--outlet` (lines,
points or polygons) makes the cells it touches on the edge of the domain outflow cells,
`--observation-points` (CSV `name,x_m,y_m`) makes SFINCS write the water level at
stations, `--recession-min` sets how long the model runs after the rain (60).

With the land cover and soil of step 2, Manning `n` and the curve number are made for
you:

```sh
hydraulik model build --dem ./data/elevation/nmt.tif --dx-m 5 --rain ./rain.csv \
    --landcover ./data/landcover/bdot10k.gpkg --hsg ./data/soil/hsg.tif \
    --default-hsg C --building-raise-m 3 --output-dir ./model
```

- The features are painted as classes on a grid of about 1 m and averaged into every
  cell. [LAND_COVER.md](LAND_COVER.md) has every value and its source; they are
  literature values that nobody has calibrated for Polish catchments, and `--classes`
  replaces any of them from a CSV.
- The soil group is the nearest cell of `--hsg`; `--default-hsg` fills the cells it does
  not cover. Without a soil group infiltration is off.
- A roof is ground that the water crosses unless `--building-raise-m` raises the cells
  that are half or more under roofs. A regular grid has no building footprints, so for an
  urban model raise them (3 m is what the checks of this project used); a notice says
  when the option is 0.
- `manning.tif` and `curve_number.tif` are written beside the model, and the `landcover`
  part of the result lists the area of every class: look at both before you run.

## 5. Run SFINCS and read the results

```sh
hydraulik engines check --require 'model run'
hydraulik model run --model ./model --output-dir ./run
hydraulik results read --run ./run --thresholds-m 0.1,0.3,0.5
hydraulik results export --run ./run --variable max_depth --output ./hmax.tif
hydraulik results export --run ./run --variable stations --output ./stations.csv
```

`model run` writes `sfincs_map.nc`, `sfincs_his.nc` (with stations) and `sfincs.log`
only when SFINCS finished and its map can be read. `results read` gives the largest
depth and velocity, the area flooded deeper than each threshold, the maximum at each
station and the water balance. `results export` writes `max_depth`, `max_velocity`,
`final_depth` or `infiltration` as a GeoTIFF for QGIS, or the `stations` series as CSV.

Read the balance first. It is `rain - infiltration - stored = residual`. In a closed
model the residual is the numerical error, and above 1 % of the rain it is flagged
(`flags` in the result); with outflow cells it is the water that left. SFINCS keeps no
water under its wet/dry threshold, 5 cm by default: a light rain does not run off, so
test a design storm and not 5 mm.

## 6. Run a sewer network on its own

The network table has one row per node, upstream first, and one row with an empty `to`
for the outfall: `name,x_m,y_m,rim_m,depth_m,to,diameter_m`. The inflow is a hydrograph
table, `time_min,discharge_m3s`, applied at one node. The table of one node of
`hydrolog route network --output-dir DIR` (which writes `<id>.csv` for every node of a
river network) is read as it is.

```bash
hydraulik swmm run --network tests/fixtures/swmm/network_chain.csv --inflow tests/fixtures/hydrolog/out/OUT.csv --inflow-node J1 --output-dir ./swmm --check
```

Without `--check` it writes `network.inp` and `network.rpt` and reports the water
balance of SWMM, the peaks of every node and conduit and, as a notice, a continuity error
above 5 %. The run lasts until 10 minutes (`--recession-min`) after the hydrograph.
`--inp FILE` runs your own SWMM input (SI units, `FLOW_UNITS CMS`) instead of a table;
then `--inflow` is optional and the node may be any node of the file.

## 7. Couple the model and the network

This is for a sewer that surcharges and returns water to the street. It needs a SFINCS
shared library that you build yourself with `--enable-shared`, named in
`HYDRAULIK_SFINCS_LIBRARY`, and `pyswmm`. The model comes from step 4; the table is as
in step 6 and its `x_m`, `y_m` must lie in the CRS of the model, `rim_m` being the
ground.

```sh
hydraulik engines check --require 'model couple'
hydraulik model couple --model ./model --network ./network.csv --output-dir ./coupled --check
hydraulik model couple --model ./model --network ./network.csv --output-dir ./coupled
```

`--check` says which nodes lie on the domain, which are outside it (they take part in the
network only) and what is missing. Every `--exchange-interval-s` (default 1 s) the nodes
take water from the cell they lie on and hand back what SWMM floods out of a full node.
The volumes are exchanged, not the rates, so the interface adds no mass error.

Set `HYDRAULIK_SFINCS_QEXT_UNIT=ms` for SFINCS v2.4.1 and `m3s` for newer builds: a
wrong unit shows as a balance that does not close.

Water that comes from outside the model, for example the routed hydrograph of a
catchment that the grid does not cover, enters one node with `--inflow FILE
--inflow-node NODE`:

```sh
hydraulik model couple --model ./model --network ./network.csv \
    --inflow ./OUT.csv --inflow-node J1 --output-dir ./coupled
```

The table is the one of step 6 and its time is elapsed time from the start of the model
run, as in the rain table. It has a term of its own in the balance
(`network_inflow_m3`); a hydrograph that outlasts the run is cut, with a notice. Do not
give the rain of the catchment that the hydrograph came from to the surface as well: no
check can see that the water is counted twice.

How to read the result (`hydraulik-couple/1`):

- `balance` books the water: rain, infiltration, surface, network, outfall, exchange and
  the external inflow. `total_error_percent` is the residual against the water that came
  in; above 1 % a flag says so, and SWMM's own continuity error is a separate notice.
- Per node, `exchanged_m3` is the NET volume from the network to the street (negative
  where the street gave water to the network). `flooded_m3` is GROSS: a flooding manhole
  takes water back whenever the pipe has room, so it can be several times the net volume.
  Use `exchanged_m3`.
- Notices to act on: `exchange_oscillation` (more than 20 sign changes of one node's
  exchange: shorten `--exchange-interval-s`), `numerical_spike`, `nodes_outside_domain`,
  `flooding_lost` and `continuity_error`.
- `coupling.csv` in the output directory is the exchange of every node and interval, and
  `sfincs_map.nc` is read with `results read --run ./coupled` as for a run without the
  network.

The coupled run happens in a process of its own, because SFINCS keeps its state in global
variables. Most options (`--mode`, `--relaxation`, the weir and orifice coefficients of a
manhole, `--surcharge-method`) have defaults for a manhole and are described by `hydraulik
commands schema --command 'model couple'`. The result is a screening: the description of
the inlets is the main uncertainty.

## 8. When something fails

| You see | Do |
|---|---|
| `validation_error` (2) | read `message` and `details`: the option is named, with its range or the allowed values |
| `not_found` (3) | a path is wrong; paths in the error are as you gave them |
| `conflict` (4), `output_exists` | choose another `--output-dir` or give `--force` |
| `missing_dependency` (6) | `hydraulik engines check` names the engine or extra, and the hint the fix |
| `calculation_error` (13) | an engine run failed; the error carries the end of its log |
| exit 10, `partial` | some items succeeded and some failed; `items` says which |
