# Land cover to Manning n and curve number

How BDOT10k features become the Manning `n` and the SCS curve number of a model
(`hydraulik.model.landcover`, ADR-0007), and where every value comes from. The tables are
`src/hydraulik/_data/landcover/classes.csv` (the classes and their values, with the source
of each value) and `mapping.csv` (which BDOT10k feature is which class). `--classes FILE`
replaces values of the first. **The values are literature values that nobody has
calibrated or reviewed for Polish catchments; the author is asked to review them before a
result is used** (see the open questions in `docs/PROGRESS.md`).

`model build` uses them through `--landcover`, `--hsg`, `--default-hsg`, `--classes` and
`--building-raise-m` (ADR-0008; "In `model build`" below).

## Method

1. The features of the layers in `mapping.csv` are read from the GeoPackage within the
   extent of the grid and painted as classes on a grid of cells of about 1 m (at most ten
   to a cell of the model), in the order of the mapping, so a later row lies over an
   earlier one. Land that no polygon covers is the class `unclassified` (grass values; a
   warning when it is 1 % of the domain or more).
2. Roads (`OT_SKJZ_L`) are lines: those on the ground are buffered by half the width of
   their surface (`SZEROKOSCNAWIERZCHNI`, 5 m when it is missing) and painted with the
   class of their material (`MATERIALNAWIERZCHNI`). Bridges and tunnels
   (`POLOZENIE` other than `na powierzchni gruntu`) and the conventional lines of
   crossings (`CECHAGEOMETRII` = `linia umowna`) are not painted. Footpaths and tracks
   are not painted.
3. Buildings (`OT_BUBD_A`) are a mask over the classes. A roof is impervious (class
   `building`, CN 98 in every group). Its roughness applies only where the buildings are
   raised (`--building-raise-m`, the water then runs off the roof); otherwise the water
   crosses the footprint like any other ground and the `n` of the class under the roof is
   kept.
4. In each cell of the model, Manning `n` is the area-weighted mean of the `n` of the
   classes, and the curve number is the area-weighted mean of the CN of the classes for
   the soil group of the cell (the composite curve number of TR-55, figure 2-3). The soil
   group is the nearest cell of the HSG raster (uint8, 1 A to 4 D, 0 no data), or the
   default group.

## In `model build`

```sh
hydraulik model build --dem ./data/elevation/nmt.tif --dx-m 5 --rain ./rain.csv \
    --landcover ./data/landcover/1465.gpkg --hsg ./data/soil/hsg.tif --default-hsg C \
    --output-dir ./model
```

* `--landcover` paints the classes; the model gets `sfincs.man` and `manning.tif`.
* `--hsg` is the raster of soil groups (the nearest cell is taken); `--default-hsg` fills
  the cells it does not cover or, alone, every cell. With either the model gets
  `sfincs.scs` and `curve_number.tif`; with neither infiltration is off.
* `--classes FILE` replaces values (a `class` column and any of `manning_n`, `cn_a` to
  `cn_d`; a blank cell keeps the shipped value; comma or semicolon, decimal point or
  comma).
* `--building-raise-m H` raises the cells that are half or more under roofs by `H` metres
  and applies the roughness of a roof there. The default is 0: the buildings are ground
  that the water crosses.
* `manning.tif` and `curve_number.tif` are GeoTIFFs on the grid of the model, written
  beside it to look at (SFINCS does not read them).
* The result has a `landcover` key: the area of every class, the roads that were painted
  or skipped, the attribute values the mapping does not name and the buildings.
  `infiltration.hsg` counts the cells of each soil group.
* `--landcover` excludes `--manning` and `--manning-raster`; `--hsg` and `--default-hsg`
  exclude `--curve-number-raster` and `--retention-mm-raster`; the four other options
  need `--landcover`.

## The classes

Manning `n` is for shallow overland flow [s/m^(1/3)]: it is the value of the sheet-flow
tables of TR-55 and of Kalyanapu et al. (2009), several times higher than the values of
channel and floodplain tables for the same cover (HEC-RAS: forest 0.10 to 0.20, grass
0.025 to 0.05), which are for flow deeper than 0.3 m. SFINCS has no roughness that depends
on the depth, so the choice moves the timing of the flood; use `--classes` to try the
others.

| class | n | CN A | CN B | CN C | CN D |
|---|---|---|---|---|---|
| `water` | 0.035 | 100 | 100 | 100 | 100 |
| `forest` | 0.4 | 30 | 55 | 70 | 77 |
| `shrub` | 0.4 | 35 | 56 | 70 | 77 |
| `grass` | 0.15 | 49 | 69 | 79 | 84 |
| `arable` | 0.06 | 72 | 81 | 88 | 91 |
| `permanent_crops` | 0.24 | 43 | 65 | 76 | 82 |
| `barren` | 0.011 | 77 | 86 | 91 | 94 |
| `built_up_low` | 0.068 | 61 | 75 | 83 | 87 |
| `built_up_dense` | 0.068 | 77 | 85 | 90 | 92 |
| `commercial` | 0.04 | 89 | 92 | 94 | 95 |
| `industrial` | 0.068 | 81 | 88 | 91 | 93 |
| `road_paved` | 0.011 | 98 | 98 | 98 | 98 |
| `road_gravel` | 0.011 | 76 | 85 | 89 | 91 |
| `road_dirt` | 0.011 | 72 | 82 | 87 | 89 |
| `building` | 0.011 | 98 | 98 | 98 | 98 |
| `unclassified` | 0.15 | 49 | 69 | 79 | 84 |

## Sources

The curve numbers are those of USDA-NRCS, *Urban Hydrology for Small Watersheds*, TR-55
(1986), tables 2-2a to 2-2c, which Hydrolog's `cn_lookup` repeats (a test compares every
class that has a row there). The tables were read in the copy of TR-55 that the US
Nuclear Regulatory Commission publishes (ML14219A437).

| class | Manning `n` | curve number |
|---|---|---|
| `water` | HEC-RAS 2D manual (Chow 1959): open water 0.025 to 0.05; 0.035 is the typical value of `r.manning` | water is impervious, CN 100 (Hydrolog `WATER`) |
| `forest` | TR-55 table 3-1: woods, light underbrush 0.40 (dense underbrush 0.80); Kalyanapu: mixed forest 0.40 | table 2-2c: woods, good condition (protected from grazing, litter and brush cover the soil) |
| `shrub` | Kalyanapu: shrub/scrub 0.40 (TR-55 has no brush row for sheet flow) | table 2-2c: brush-weed-grass mixture, fair condition |
| `grass` | TR-55 table 3-1: short grass prairie 0.15 (dense grasses 0.24, Bermudagrass 0.41) | table 2-2c: pasture, grassland or range, fair condition |
| `arable` | TR-55 table 3-1: cultivated soils, residue cover up to 20 % 0.06 (above 20 %: 0.17) | table 2-2b: row crops, straight row, poor condition |
| `permanent_crops` | TR-55 table 3-1: dense grasses 0.24, the ground cover of an orchard (assigned) | table 2-2c: woods-grass combination (orchard or tree farm), fair |
| `barren` | TR-55 table 3-1: smooth surfaces (bare soil) 0.011; Kalyanapu: barren land 0.011 | table 2-2b: fallow, bare soil |
| `built_up_low` | Kalyanapu: developed, low intensity (20 to 49 % impervious) 0.068 | table 2-2a: residential districts, 1/4 acre lots (38 % impervious); assigned: a plot of 500 to 1000 m2 |
| `built_up_dense` | Kalyanapu: developed, medium intensity (50 to 79 %) 0.068 | table 2-2a: residential, 1/8 acre or less, town houses (65 %) |
| `commercial` | Kalyanapu: developed, high intensity (80 to 100 %) 0.04 | table 2-2a: commercial and business (85 %) |
| `industrial` | Kalyanapu: developed, medium intensity 0.068 (72 % impervious) | table 2-2a: industrial (72 %) |
| `road_paved` | TR-55 table 3-1: smooth surfaces (concrete, asphalt, gravel or bare soil) 0.011 | table 2-2a: paved streets and roads with curbs and storm sewers, paved parking lots 98 |
| `road_gravel` | TR-55 table 3-1: smooth surfaces 0.011 | table 2-2a: gravel streets and roads, including right-of-way |
| `road_dirt` | TR-55 table 3-1: smooth surfaces 0.011 | table 2-2a: dirt streets and roads, including right-of-way |
| `building` | TR-55 table 3-1: smooth surfaces 0.011 (used only where buildings are raised) | table 2-2a: roofs 98 |
| `unclassified` | as `grass` | as `grass` |

Kalyanapu, Burian and McPherson (2009), *Effect of land use-based surface roughness on
hydrologic model output*, Journal of Spatial Hydrology 9(2): 51-71, table 2. The paper
could not be opened; its values are those of the NLCD table in the GRASS GIS add-on
`r.manning` (`NLCD_KALYANAPU`), which cites it. The Manning values of TR-55 are those of
Engman (1986) for flow about 0.1 ft deep. The HEC-RAS values are from the *HEC-RAS
Mapper User's Manual*, "Published Manning's n Values" (adapted from Chow 1959).

## The mapping

BDOT10k classification of the land cover (`pokrycie terenu`, GUGiK) and the class it
becomes; an attribute is compared case-insensitively.

| layer | attribute = value | class |
|---|---|---|
| `OT_PTWP_A` (woda powierzchniowa) | any | `water` |
| `OT_PTLZ_A` (teren leśny i zadrzewiony) | any | `forest` |
| `OT_PTRK_A` (roślinność krzewiasta) | any | `shrub` |
| `OT_PTTR_A` (roślinność trawiasta i uprawa rolna) | `RODZAJ` = roślinność trawiasta | `grass` |
| | `RODZAJ` = uprawa na gruntach ornych | `arable` |
| `OT_PTUT_A` (uprawa trwała) | any | `permanent_crops` |
| `OT_PTGN_A`, `OT_PTSO_A`, `OT_PTWZ_A` (grunt nieużytkowany, składowisko odpadów, wyrobisko i zwałowisko) | any | `barren` |
| `OT_PTZB_A` (zabudowa) | `RODZAJ` = jednorodzinna, pozostała zabudowa | `built_up_low` |
| | `RODZAJ` = wielorodzinna | `built_up_dense` |
| | `RODZAJ` = handlowo-usługowa | `commercial` |
| | `RODZAJ` = przemysłowo-składowa | `industrial` |
| `OT_PTNZ_A` (pozostały teren niezabudowany) | any | `industrial` |
| `OT_PTKM_A` (teren pod drogami kołowymi, szynowymi i lotniskowymi) | any | `road_paved` |
| `OT_PTPL_A` (plac), `OT_SKJZ_L` (jezdnia) | `MATERIALNAWIERZCHNI` = grunt naturalny | `road_dirt` |
| | = żwir, tłuczeń | `road_gravel` |
| | any other (asphalt, concrete, slabs, paving blocks, sett) | `road_paved` |
| `OT_BUBD_A` (budynek) | any | `building` |

A value the mapping does not name (a change of the classification) is not painted and is
reported in `unmapped` and in a warning.

## What this does not do

* The curve numbers of the built-up classes are composite values for whole plots (TR-55
  counts 98 for the impervious share and open space for the rest), while roofs and mapped
  roads are painted at 98 on top: in dense blocks the impervious share is counted twice,
  a few curve-number points to the wet side.
* The soil group comes from a 250 m raster (SoilGrids): it does not follow plots.
* Roughness is one value per class: no dependence on the season or on the depth.
* Land cover outside Poland (ZABAGED, CORINE) is not mapped.
