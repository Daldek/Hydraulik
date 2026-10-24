# Extraction note: SFINCS and SWMM integration

Written: 2026-10-24. Input to
[the integration plan](2026-10-24-sfincs-swmm-integration.md); a record of what
earlier work decided, built and found, not a requirement document. Facts about
engines were checked against the SFINCS v2.4.1 and `main` sources, the SFINCS
documentation and the installed packages on the date above; anything not
checked is marked `[INFERENCE]`.

## 1. What was studied

| Source | What it is | Where it stands |
|---|---|---|
| Remote branch `origin/claude/elegant-planck-v242bb` | 24 commits from 2026-10-20 to 2026-10-21 on `de97009`, all under `experiments/sfincs_swmm_coupling/` (75 files, about 34 000 lines, mostly generated results): a feasibility study of coupling SFINCS to EPA SWMM through the SFINCS BMI, a validation on laboratory data, a D-Flow FM comparison and a literature review. Commit messages are Polish and carry `Claude-Session:` trailers. | Read in full. Cited here by short commit hash; not merged (a clean re-application is `feature/sfincs-swmm`). |
| Uncommitted files of the `develop` working tree (8 entries) | `CLAUDE.md`, `.gitignore` (empty), `docs/PRD.md`, `docs/SCOPE.md`, `docs/PROGRESS.md`, `docs/research/2026-08-19-hydromt-sfincs-integracja-research.md`, `docs/superpowers/specs/2026-08-20-hydraulik-mvp-design.md`, `.claude/` (agent worktrees). All Polish. | Read-only. Untouched. They overlap files this branch adds (see 8). |
| Worktree `poc-poznan-screening` (branch `worktree-poc-poznan-screening`, still at `de97009`) | The author's proof of concept: about 9 000 lines of `src/hydraulik` (urban pluvial screening for Poznań-Rataje and Pobiedziska through `hydromt_sfincs` 2.0.0rc3 and the SFINCS Docker image), 22 test modules, `docs/poc/`, `docs/architektura/` (integration with Hydrograf, decisions D-1 to D-21, JSON Schemas of the job documents). Uncommitted. | Read-only. Not copied. Treated as the author's existing SFINCS code (ADOPTION_PLAN phase 2: committing it is the author's decision). |
| The author's scratch directory `hydraulik-work` (16 GB) | Outputs and logs of the PoC runs. | Context only. |
| Nogat standard 2.1 (commit `cc656e7`), registry entry of Hydraulik, Hydrograf `docs/PROGRESS.md` (session 99) | The rules this branch follows; Hydraulik is `tool`, status `research`, CLI `hydraulik`, no MCP, no REST, data source `osm`, provides `hydraulik-job`, depends on Kartograf (CLI), IMGWTools (`fetch_pmaxtp`), Hydrolog (`BetaHietogram`, `EulerIIHietogram`). Hydrograf paused its side of the integration until Hydraulik is mature. | Rules applied in 3. |

## 2. Decisions that are already taken

| # | Decision | Source |
|---|---|---|
| 1 | Hydraulik stays MIT. SFINCS is an external engine: users run it themselves, for example from a Docker image; the repository never bundles or redistributes it. `README.md` and `CLAUDE.md` name SFINCS and `hydromt_sfincs` (GPL-3.0) as external (DEV-13.5). | ECO-041, 2026-10-20 |
| 2 | Engine release pinned and overridable: `deltares/sfincs-cpu:sfincs-v2.4.1`. | spec 2026-08-20 decision 4; PoC `engine.image` |
| 3 | `hydromt_sfincs` is isolated behind one adapter module and is an optional extra, never a hard dependency. Own code is written from the algorithms, not copied from GPL code. | spec decisions 3 and 13; PoC D-13 |
| 4 | Engines are pluggable behind an `Engine` protocol (`build`, `run`, `read`; later `capabilities`); the scenario and the input data carry no SFINCS concepts. | spec decision 13; PoC D-7 |
| 5 | Inputs: terrain from Kartograf (DEM), land cover (BDOT10k with `cn_value`), design rain from Hydrolog hyetographs with depths from IMGWTools PMAXTP. Rain-on-grid only, uniform in space. | spec decisions 5 to 7; registry |
| 6 | Losses by SCS-CN rasterised from `land_cover.cn_value` (SFINCS variant `cna`, no recovery, `storecumprcp = 1`); Manning from a literature table class → n with `overland` values, versioned inside Hydraulik and overridable per scenario. | spec decisions 6 and 9; PoC D-12 |
| 7 | Domain: polygon (catchment plus buffer); the outflow boundary (`msk = 3`) only where the water leaves, closed elsewhere; the solver and the subgrid builder read `huthresh` from one place. | spec section 4; research 9.2 |
| 8 | Results in one engine-independent format; an automatic mass balance whose residual above 1 percent is a warning (a hard criterion in the pilot). | spec section 6 |
| 9 | Full 1D sewer coupling (SWMM) is **out of the MVP** of the urban screening: the sewer is a constant capacity subtracted from the rain. The coupling studied on the old branch is research that no document of the author has accepted into the product. | SCOPE.md "Poza zakresem" |
| 10 | All documents of a project are English, identifiers carry units, errors come from the shared registry. | DEV-2.1, DEV-8.2, ERR-1 |

Decisions 3 and 9 pull in different directions on this branch: the assignment
asks for a SWMM integration, SCOPE.md keeps it out of the product. The branch
builds it as an optional, separately switched feature and leaves the product
decision open (question Q1 in PROGRESS).

## 3. Data flows

```
kartograf download (CLI subprocess, --output-dir, --json)
   DEM GeoTIFF, BDOT10k GeoPackage ──┐
IMGWTools fetch_pmaxtp (library)     │
   depth P [mm] for duration, p [%] ─┼─▶ Hydrolog hyetograph ─▶ rain series [mm/h]
land-cover table (class → n, CN)     │
domain polygon, outlet, network ─────┘
                       │
         model build (terrain.grid, SFINCS writer, SWMM writer)
                       ▼
 model directory: sfincs.inp, sfincs.ind, sfincs.msk, sfincs.dep,
   sfincs.man, sfincs.scs, sfincs.precip, [network.inp, exchange.json]
                       │
   run ── SFINCS executable or Docker image         (uncoupled)
       └─ libsfincs.so (BMI, ctypes) + pyswmm       (coupled, every Δt_c)
                       ▼
 sfincs_map.nc, sfincs_his.nc, sfincs_log.txt, SWMM report, coupler series
                       ▼
 read ─▶ maxima, hydrographs, mass balance, summary.json ─▶ floodmap GeoTIFF
```

The coupled loop of the old branch (`coupler.py`), one exchange interval `Δt_c`:

1. read the water level `zs` of the exchange cell (SFINCS) and the head `H` of
   the node (SWMM);
2. compute the exchange discharge `Q` (positive = surface → network);
3. limit `Q > 0` to the water standing in the cell over the longest possible
   SFINCS interval, `Q ≤ h·A_cell / (Δt_c + dtmax)`, because SFINCS clips the
   level at the bed and silently creates water otherwise;
4. impose `-Q` as `qext` and advance SFINCS with `update_until(t_{k+1})`;
5. SFINCS overshoots the target by up to one adaptive step, so the volume that
   left the surface is `V = Q·(t_new − t_old)`; give SWMM exactly `V/Δt_c` as
   lateral inflow and advance SWMM by `Δt_c`;
6. read the volume SWMM flooded and return it to the surface cell in the next
   interval (volume in transit is tracked, so the balance closes).

Exchanging volumes instead of rates makes the interface mass-conservative by
construction; what remains is a time shift of at most one SFINCS step
(old README 2.4, 3.1).

Exchange law (v2, continuous in `zs` and `H`; Rubinato et al. 2017,
doi:10.1016/j.jhydrol.2017.06.024, referenced as in Itzï to the node area `A`
and the perimeter `P = 2·sqrt(πA)`): `H ≥ zs`: spill, `Q = −Q_o(H − zs)`;
otherwise a free weir `Q_w = ⅔·C_w·P·(zs − z_t)^1.5·√(2g)` with the Villemonte
(1947) submergence factor once `H` passes the rim `z_t`, capped by the orifice
law `Q_o(Δh) = C_o·A·√(2gΔh)`, linearised below `Δh = 1 cm`; defaults
`C_w = 0.54`, `C_o = 0.167`, `A = 1.167 m²` (SWMM `MIN_SURFAREA`).

## 4. File formats

SFINCS inputs, checked in `sfincs_input.f90` and `sfincs_domain.f90` of v2.4.1:

| File | Format |
|---|---|
| `sfincs.inp` | `key = value` text; keys used: `mmax nmax dx dy x0 y0 rotation epsg tref tstart tstop dtout dtmaxout dthisout dtmax alpha huthresh advection manning inputformat outputformat depfile mskfile indexfile manningfile scsfile qinffile precipfile srcfile disfile obsfile crsfile storecumprcp storevelmax sfacinf timestep_analysis` |
| grid | regular, `x0, y0` is the lower-left cell edge, `rotation` in degrees, cell index `(m−1)·nmax + n` (n fastest, row `n = 1` at the south edge) |
| `inputformat = bin` (default) | `indexfile`: int32 `np`, then `np` int32 cell indices; `mskfile`: int8 for the active cells; `depfile`: float32 for the active cells; all in the order of the index file (m outer, n inner) |
| `inputformat = asc` | `mskfile` and `depfile` as `nmax` rows of `mmax` values, south row first (the old branch ran on this). `manningfile`, `scsfile` and `qinffile` are binary streams of `np` float32 values in active-cell order **in both modes** |
| `scsfile` | `S = 1000/CN − 10` in inches (converted by ×0.0254), runoff `Q = (P − λS)² / (P + (1 − λ)S)` with `λ = sfacinf` (default 0.2) |
| `qinffile` | mm/h |
| `precipfile` | `time [s] intensity [mm/h]`, linearly interpolated. **Past the last record the last segment is extended linearly**: a series that ends falling goes negative and removes water without a warning. End with a flat segment that reaches `tstop` (PoC upstream issue draft, reproduced on v2.4.1) |
| `srcfile` / `disfile` | `x y name` per point; `time [s]` and one discharge `[m³/s]` column per point |
| `sfincs_map.nc` | `zs`, `zsmax`, `vmax`, `cumprcp`, `cuminf`, `qinf`, `zb`, `msk`; `n = 0` is the south row |
| `sfincs_his.nc` | `point_zs`, `crosssection_discharge`, station and cross-section names |

SFINCS BMI (shared library `libsfincs`, called through `ctypes`): `initialize`,
`update_until(t_target_s)`, `finalize`, `get_current_time`, `get_end_time`,
`get_var_shape`, `get_value_ptr` (arrays `zs` double, `zb` and `qext` float, no
copy), `set_logical("qext")`, `get_sfincs_cell_index(x, y)` (1-based),
`get_sfincs_cell_area`. `update_until` takes an absolute time, does not clip
the last step, and a target in the past still runs one step (old README 6).

**`qext` unit differs between versions.** In v2.4.1 `zs += qext·dt`, so `qext`
is a rate in m/s. On `main` after PR #355 (2026-09-23) it is a flow in m³/s per
cell and the source says so; a coupler written for one unit is wrong by the
cell area on the other. The old branch ran on `main` commit `db08c6a`
(m³/s).

SWMM (EPA SWMM 5.2.4 through `pyswmm` 2.2.0 and `swmm-toolkit` 0.17.0):
`[OPTIONS]` with `FLOW_ROUTING DYNWAVE`, `SURCHARGE_METHOD EXTRAN|SLOT`,
`ROUTING_STEP`, `VARIABLE_STEP 0`, `MIN_SURFAREA`; `[JUNCTIONS]` with
`SurDepth` (100 m so SWMM never floods by itself, or 0 so it floods and the
coupler hands the volume back), `[OUTFALLS]` (`FREE` or `TIMESERIES` stage),
`[CONDUITS]`, `[XSECTIONS]`, `[TIMESERIES]`. Read in the loop through pyswmm:
`Node.head`, `Node.generated_inflow()`, `Node.statistics["flooding_volume"]`,
`Link.flow`; the continuity error comes from the text report.

## 5. Binaries and licensing

| Component | Licence | Handling in Hydraulik |
|---|---|---|
| Hydraulik | MIT | the only thing the repository distributes |
| SFINCS source | GPL-3.0 | not copied, not linked at build time |
| SFINCS executables and the `deltares/sfincs-cpu` image | Deltares Freeware: commercial use and research publishing allowed, no distribution, no modification (SFINCS `README.rst`, "Licensing conditions") | detected on the user's machine: environment variable, `PATH`, or Docker; never bundled, never pulled by Hydraulik |
| `libsfincs` for the coupling | built by the user from a SFINCS checkout with `--enable-shared`; the container carries no library `[INFERENCE: the old branch built it from source]` | path set by the user |
| `hydromt_sfincs` | GPL-3.0 | optional extra, one adapter module, named in README and CLAUDE.md |
| EPA SWMM, `swmm-toolkit` | `CC0-1.0 AND (MIT OR Apache-2.0)` (package metadata of 0.17.0) | comes with the `pyswmm` wheel as an optional extra |
| `pyswmm` | BSD-2-Clause (metadata of 2.2.0) | optional extra |
| `hydrolog`, `imgwtools` | MIT | optional extra, pinned to release tags |
| NetCDF4, rasterio, geopandas | MIT, BSD-3-Clause | extras |
| Kartograf | MIT | called as a CLI subprocess |
| Data | GUGiK (NMT, BDOT10k) free reuse with attribution; IMGW-PIB PMAXTP attribution required, commercial terms unverified; OSM ODbL | licence and attribution go into the result documents |

## 6. What works (evidence on the old branch)

All numbers are from the old README; none was reproduced in this branch except
where PROGRESS says so.

- Coupling through the unchanged SFINCS BMI and pyswmm works without a change
  in either model (3.1).
- The interface adds no mass error: the surface-side error equals the error of
  SFINCS alone (0.035 m³ with rain, −0.045 m³ with inflow) in all 45
  sensitivity runs and the 45 laboratory runs; the network-side error equals
  SWMM's own continuity error (3.1, 3.9, 3.13).
- Two stable sets: **SWMM flooding** (`EXTRAN`, node `SurDepth = 0`, flooded
  volume returned to the cell, SWMM step 0.5 s, `Δt_c` about 1 s): balance
  error 0.00 to 0.03 percent, no oscillation even without relaxation, but the
  backwater outflow is about twice the orifice-law value (conservative for
  screening); and **coordinator spill** (`SLOT`, relaxation `w = 0.1`, SWMM step
  0.5 s): outflow limited by the calibrated orifice law, but `SLOT` loses 2 to
  17 percent of the water in sustained pressurised flow (3.10, 3.11, 4).
- Exchange step `Δt_c`: 1 s and 5 s agree within 1.5 percent for a surcharged
  network; 30 s halves the exchange. Backwater needs `Δt_c ≤ 1 s` for a stable
  split between nodes (3.3).
- Laboratory check (A Coruña, Zenodo 7941067, CC BY 4.0, Sañudo et al. 2024,
  doi:10.1002/hyp.15068): street-to-network direction only; timing of the inlet
  response −7 to +15 s, split between inlets within 5 to 7 percentage points,
  but a single inlet coefficient does not transfer from steady state to rain
  (3.13, validation README). The spill direction is untested on measurements.
- Own SFINCS regular-grid writer in ASCII input mode ran on the real engine for
  2 100 and 19 766 cells.

## 7. Known defects and limits

Engines:

1. **SWMM 5.2.4 `SLOT` loses water in sustained pressurised flow** (2 to 17
   percent), independent of step and tolerance; `EXTRAN` is exact there (3.10).
2. **`EXTRAN` diverges under explicit coupling** with a surcharged network, also
   with relaxation and a 0.25 s step; stable only for free-flowing networks
   (3.2, 3.10).
3. **`EXTRAN` head spikes at the onset of pressurised flow**: 1.3 to 1.4 m in
   1 s that ends at the ground level; 26 to 27 of 30 manholes, in 5 to 6 of them
   the maximum is raised by more than 5 cm. Water balance unaffected (0.16 m³
   of 199 m³), screening maxima and spill flags affected. Direction chosen, not
   built: report the highest head held for at least `T` seconds (start 10 s),
   keep the raw maximum next to it, flag a possible numerical spike beyond
   about 5 cm; no percentiles (they depend on record length) (7.1).
4. **A spill orifice to an outfall at the rim loses 8 to 26 percent** in
   `EXTRAN`, with or without SFINCS; that variant is unusable (3.12).
5. SFINCS: a `qext` sink larger than the water in the cell creates water
   silently (`max(·, zb)` in the continuity step) (old README 6, item 1).
6. `pyswmm`: `step_advance` takes whole seconds only; `routing_stats["final_storage"]`
   is in ft³ although the flow unit is CMS (old README 6, items 7 and 8).
7. SFINCS `dtmax` defaults to 60 s: a dry domain starts with a 30 s step, so the
   coupler sets `dtmax ≤ Δt_c` explicitly.
8. `make -j` of SFINCS stops on Fortran module dependencies; plain `make` works.

Coupler and model:

9. Relaxation `w = 0.1` and SWMM step 0.5 s are not universal: denser networks
   and stiffer inlets need more damping (3.9). The README asks for automatic
   detection of oscillation (sign flips of the exchange in a node) and a
   correction, not fixed settings.
10. The equalisation limiter and the semi-implicit exchange are dead ends
    (3.2, 3.8); the first cuts the backwater outflow almost sevenfold.
11. The uncertainty is the inlet description, not the numerics: coefficients
    change the exchange by 10 to 30 percent and the definition of depth over a
    grate (mean or maximum of the cells) by 40 to 50 percent (3.9, 3.13).
12. Regular grid only; subgrid depth would have to be taken relative to
    `subgrid_z_zmin`, untested. One cell per node; the laboratory case used the
    footprint of a grate.
13. `[LOSSES]` are absent from the old SWMM files (zero local losses); the
    canonical input needs non-zero defaults. The backwater boundary is not
    consistent (free surface edge below the outfall stage, no flap gate) (7.2).
14. Only Linux was exercised; `libsfincs` on Windows and macOS is unchecked.
15. Timings are from a tiny domain and not representative.

## 8. What the old branch hands over, and what it does not

| Old content | Verdict | Where it goes |
|---|---|---|
| `coupler.py`: exchange laws v2, BMI wrapper, coupling loop, mass bookkeeping, steady-state statistics | carry, rewritten: no module globals, no `chdir`, engines behind protocols | `hydraulik.coupling`, `hydraulik.engines.sfincs.bmi` |
| `case_setup.py`: SFINCS and SWMM writers | carry the writers, not the idealised case | `hydraulik.engines.sfincs`, `hydraulik.engines.swmm`; the idealised case becomes a test fixture |
| `swmm_only.py`: continuity error from the SWMM report | carry the parser | `hydraulik.engines.swmm.report` |
| `swmm_spikes.py`, README 7.1 | carry the held-maximum and spike flag as a pure function | `hydraulik.coupling.diagnostics` |
| `validation/coruna` (45 runs, needs the Zenodo data) | do not carry; reproducible from the old commits | cited only |
| `dflowfm/` (build kit with 62 KB of patches, 1D2D comparison) | obsolete: a different engine and a compiler study | not carried |
| exchange law v1, equalisation limiter, semi-implicit exchange, `swmm_orifice` spill | negative or superseded results | not carried; recorded here |
| `results/summary.json` (640 KB), figures, `plots.py`, `sensitivity.py`, `viz/export_3d.py` | generated evidence and presentation | not carried |
| `reports/` and `research_notes/` (Polish literature review) | knowledge, no code | cited by commit `4e669bb`; findings summarised in 3 and 6 |
| The coordinator's habits: one process per scenario because of SFINCS global state, `sys.path` edits, global `INLET`, `os.chdir`, hard-coded geometry | defects of an experiment | the coupler runs one model per process behind `hydraulik model run`, with explicit objects |

The author's uncommitted `CLAUDE.md`, `docs/PROGRESS.md`, `docs/PRD.md`,
`docs/SCOPE.md`, `docs/research/` and `docs/superpowers/` stay as they are. The
branch adds its own English `CLAUDE.md` and `docs/PROGRESS.md`; merging it into
`develop` needs the untracked copies moved aside first (git refuses to overwrite
untracked files). The PoC package uses the same import name `hydraulik`, so the
two code bases collide in `__init__.py`, `cli.py`, `config.py`, `data.py` and
`pyproject.toml` when the author decides to commit the PoC.

## 9. Questions for the author

Recorded in PROGRESS as Open questions: the product status of the SWMM coupling
(decision 9), where `hydromt_sfincs` and the subgrid belong (the regular-grid
writer of this branch needs neither), the order in which the PoC and this
branch reach `develop`, which SFINCS build the coupling targets while v2.4.1
has the other `qext` unit, and the `Approved:` line of the integration plan.

## 10. Sources of the old branch, by commit

`50c260f` feasibility test; `c69b9f5` inflow variant; `7210606`, `42913d4`,
`f3de7a2`, `7b3b581`, `4e669bb` literature notes and report; `5084f61`,
`93364c9`, `f58c3a7` D-Flow FM; `044f9ab` continuous exchange law;
`4d36696` semi-implicit exchange; `74e27df` sensitivity; `451f6c1` SWMM alone;
`ed9ebea` flooding by SWMM; `3740262` manhole as SWMM orifice; `478891a`,
`e7ef64d`, `a78bd80`, `01cd8b0` validation on A Coruña; `647539b`, `4223046`
3D export; `26cd61e` pressure spikes.
