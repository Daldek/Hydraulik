# SFINCS: urban drainage representation, documented model couplings and urban/pluvial applications (state of knowledge 2026-10-20)

Method note for the report writer. Sources were (1) a local checkout of the SFINCS source and docs at commit `db08c6a` (2026-10-19, author Tim Leijnse), (2) a blobless clone of the full SFINCS git history (tags, commit log), (3) shallow clones of public GitHub repos found through GitHub code search (`jdhughes-dev/nywsc_compound_flooding`, `Deltares-research/cht_sfincs`, `Deltares-research/FloodAdapt`), and (4) web search. Publisher sites, Crossref, OpenAlex, Semantic Scholar, ResearchGate, readthedocs, publicwiki.deltares.nl and Copernicus could NOT be opened from this session (proxy policy 403 / DNS failure). Literature claims therefore rest on search-engine abstracts and snippets, not on full texts. They are rated "medium" unless a DOI and title were seen in two independent sources. Code and docs claims were read directly and are rated "high". DOIs below were all seen in at least one source. None were constructed.

## Q1. Is there any published or documented coupling of SFINCS with SWMM, or with any 1D sewer/pipe-network model?

### Takeaway
No peer-reviewed paper, thesis, conference abstract, Deltares report or GitHub artefact couples SFINCS with SWMM or with any 1D sewer/pipe-network model (D-HYDRO/SOBEK/Delft3D FM 1D, MIKE URBAN, InfoWorks). The nearest artefacts are listed below. A Deltares project page announces a BMI coupling of SFINCS with D-Hydro 1D as one of two options. The USGS coupling code has an exploratory SFINCS–MODFLOW 6 notebook. In the same USGS repository the sewer model is SWMM, but it is coupled to D-Flow FM and MODFLOW, never to SFINCS. A SFINCS–SWMM methods paper would therefore appear to be the first of its kind. Confidence that no such coupling exists: medium-high.

### Cited Findings
- **No SFINCS–SWMM hit anywhere searched.** GitHub-wide code search for "sfincs swmm" (Python) returned only unrelated repos and one USGS repo in which SWMM is coupled to MODFLOW/D-Flow FM, not to SFINCS. A global GitHub issue search for "SFINCS SWMM sewer coupling" returned nothing relevant. Searches of the Deltares/SFINCS and Deltares/hydromt_sfincs issues for "sewer", "SWMM", "urban drainage", "1D", "piped drainage" returned nothing relevant (only issue #112 "Drainage becomes NaN when culvert extract from dry cell" and #35 on weirs). — [GitHub Deltares/SFINCS issues](https://github.com/Deltares/SFINCS/issues/112); search performed 2026-10-20. Confidence: high (for GitHub); medium (for the literature as a whole, given access limits).
- **Web search also found no SFINCS–SWMM coupling.** It returned only couplings of SWMM with other 2D models. These are useful positioning references:
  - **LISFLOOD-FP 8.1 + EPA SWMM 5.1.015.** A two-way coupled urban flood model in a single executable, with manhole orifice exchange and an outfall boundary (v1.0.0; v1.2.0 adds coupled-storage and stability fixes). Its 2D solver uses the same local-inertial (Bates et al. 2010) equation family as SFINCS. — [FloodGroup/LISFLOOD-SWMM-Coupling](https://github.com/FloodGroup/LISFLOOD-SWMM-Coupling). Confidence: medium (repo description seen via search only; authors and paper not verified).
  - **Linking 2D overland flow models to SWMM 5.1 through its DLL** without modifying the SWMM source. — ["A methodology for linking 2D overland flow models with the sewer network model SWMM 5.1 based on dynamic link libraries", Water Science & Technology 73(12):3017 (2016)](https://iwaponline.com/wst/article/73/12/3017/20354/A-methodology-for-linking-2D-overland-flow-models). Confidence: medium (authors not confirmed in this session; commonly attributed to Leandro & Martins — verify).
  - **Inunda.** A GPU local-inertial PyTorch solver (Zhi Li). One search summary said it couples bidirectionally to SWMM: once per coupling interval it gathers the surface depth at junction cells and injects a signed exchange discharge as the node's lateral inflow. A second search found no mention of SWMM in the abstract snippets. — [arXiv:2607.09614](https://arxiv.org/abs/2607.09614). Confidence: low (the two sources conflict; verify in the full text).
- **USGS coupling of D-Flow FM, MODFLOW 6 and SWMM (not SFINCS).** An unpublished manuscript in a public repo (draft for Advances in Water Resources): Hughes J.D., Herdman L., Prigiobbe V., Russcher M.J., Bayraktar B., Jahn K.L. et al., "A shorter coupling interval is not a safer one: tidal aliasing in coupled coastal hydrodynamic, groundwater, and sewer simulations".
  - Three unmodified simulators run in one process: D-Flow FM kernel 1.2.184 via BMI, MODFLOW 6.7.0 via the MODFLOW API/XMI, and SWMM 5.2.4 via PySWMM 2.0.1, because "SWMM implements neither".
  - The site is Greenport, NY (combined sewer). Aquifer–sewer seepage is exchanged at junctions. SWMM outfall discharge goes to D-Flow FM as a tracer source every user time step. The coupling is fully explicit, with no iteration.
  - The manuscript states that returning sewer discharge to the hydrodynamic model "requires a transfer within a model time step that the Basic Model Interface does not define".
  - — [jdhughes-dev/nywsc_compound_flooding, docs/GP/Hughesetal_AWR_LISSCoupling.tex @8be755e (2026-10-19)](https://github.com/jdhughes-dev/nywsc_compound_flooding/blob/8be755e8f03703435a83e33f3fa7c1b837fc414f/docs/GP/Hughesetal_AWR_LISSCoupling.tex). Confidence: high that the draft and code exist; the content is not peer reviewed.
- **The same repo contains an exploratory SFINCS–MODFLOW 6 coupling notebook.**
  - It loads `libsfincs.so` through `xmipy.XmiWrapper`, gets pointers to `zs`, `zb` and `qext`, calls `coastal.update_until(to_time)`, and maps SFINCS water levels to MODFLOW GHB heads/conductance with area-weighted matrices.
  - MODFLOW GHB flows go back as `qext = ghb2qext · (ghb_flow / cell_area)`, i.e. as a rate in m/s (the pre-2026-09 SFINCS convention). Case: "test_north_fork" (Long Island).
  - SFINCS is not used in the manuscript's 46 simulations, which use D-Flow FM.
  - — [notebooks-sfincs/step2_run_sfincs-modflow_variable_dt.ipynb](https://github.com/jdhughes-dev/nywsc_compound_flooding/blob/8be755e8f03703435a83e33f3fa7c1b837fc414f/notebooks-sfincs/step2_run_sfincs-modflow_variable_dt.ipynb). Confidence: high (code read directly).
- **Companion MODFLOW–SWMM preprint.** Tajari M., Suresh A., Hughes J.D., Jahn K.L., Herdman L., Bayraktar B., Masterson K., Prigiobbe V. (2026), "Dynamic Coupling of MODFLOW and SWMM to Model Compound Flooding in Urban Areas with Aging Sewers", SSRN preprint, doi:10.2139/ssrn.6830778. — cited in [Hughesetal_AWR_LISSCoupling.bib](https://github.com/jdhughes-dev/nywsc_compound_flooding/blob/8be755e8f03703435a83e33f3fa7c1b837fc414f/docs/GP/Hughesetal_AWR_LISSCoupling.bib). Confidence: medium (seen only in that bib file).
- **A tightly coupled 1D–2D urban compound-flood model co-authored by a SFINCS developer uses Delft3D FM, not SFINCS.** Tang B., Nederhoff K., Gallien T.W. (2025), "Quantifying compound coastal flooding effects in urban regions using a tightly coupled 1D–2D model explicitly resolving flood defense infrastructure", Coastal Engineering 199:104728, doi:10.1016/j.coastaleng.2025.104728.
  - It resolves storm-drain pipes and seawalls at two Southern California harbour sites and is validated with storm-drain pressure sensors.
  - Resolving compound interactions gave flood extents about 50 % larger.
  - Per Hughes et al. (draft), it neglects pipe infiltration and leaves groundwater for later.
  - — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S037838392500033X); [SSRN preprint](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5021147). Confidence: medium-high.

### Inferences
- The most defensible novelty claim for the paper is: "first two-way coupling of SFINCS with a 1D sewer-network model (EPA SWMM), and first use of the SFINCS BMI/XMI `qext` source term for manhole/outfall exchange". Phrase it as "to our knowledge, as of October 2026". Deltares has publicly scoped a SFINCS–D-Hydro 1D BMI coupling (see Q5), so the paper should acknowledge it as planned or parallel work.
- The USGS manuscript is the closest methodological precedent. It concerns in-memory library coupling of a 2D coastal model with SWMM via PySWMM, and the explicit exchange-interval trade-off. It also gives the argument that BMI lacks a sub-time-step hook. SFINCS reads `qext` inside every `update_continuity` call, so a value set before `update_until` acts as a constant source over the whole interval. That is the same explicit, lagged scheme Hughes et al. analyse.
- LISFLOOD-FP–SWMM is the natural like-for-like comparator because it uses the same local-inertial equations.

### Gaps
- Could not open Google Scholar, ResearchGate, EGU/AGU abstract databases or the HIC proceedings directly. An EGU/AGU abstract on SFINCS + sewer that is not indexed by the web search engine cannot be ruled out.
- Could not confirm whether the USGS manuscript has been submitted or published, or whether a SFINCS variant is planned in it.
- Could not verify the authors of the WST 2016 paper or of the LISFLOOD-SWMM coupling paper, or whether Inunda's SWMM coupling exists.

## Q2. Which couplings of SFINCS (via BMI or otherwise) are documented?

### Takeaway
SFINCS has a C-bound BMI/XMI library interface (`sfincs_bmi.f90`). Its documented and code-evidenced in-memory uses are:
- HurryWave (wave-enhanced roughness)
- real-time control of weirs and pumps (`cht_sfincs`)
- MODFLOW 6 (USGS exploratory notebook)

All published compound-flood applications instead use offline one-way boundary or forcing chains: ADCIRC, GTSM, CaMa-Flood, Wflow, D-Flow FM, XBeach, a regional tide-surge-wave model. SnapWave is compiled into SFINCS rather than coupled externally. No peer-reviewed paper describing a BMI coupling of SFINCS was found.

### Cited Findings

**The SFINCS BMI/XMI interface itself (code read at db08c6a)**
- **Functions exposed:** `initialize`, `update`, `update_until`, `finalize`, `get_value_ptr`, `get_var_shape`, `get_var_type`, `get_var_rank`, `set_logical`, `get_start_time`, `get_end_time`, `get_time_step`, `get_current_time`, `update_zbuv`, `update_apparent_roughness`, `get_sfincs_cell_index`, `get_sfincs_cell_indices`, `get_sfincs_cell_area`, `get_last_bmi_error`.
- **Variables reachable by pointer:** only `z_xz`, `z_yz`, `zs`, `zb`, `subgrid_z_zmin`, `qext` and `uorb`, plus `z_index_z_n/m` for shape. There are no velocity or flux variables and no `set_value`; all writes go through pointers. — [sfincs_bmi.f90 @db08c6a](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/source/src/sfincs_bmi.f90). Confidence: high.
- **`qext` units changed.** It is now "external source/sink per cell in m3/s (positive = water added to the cell). It is added to qsrc in update_continuity. NOTE: before the qsrc restructuring qext was a rate in m/s; couplers that still provide m/s must now multiply by the cell area." `set_logical("qext", …)` switches it on or off. The change arrived with PR #355 "Qsrc array + urban drainage + drainage structure rewrite" (Maarten van Ormondt, merged 2026-09-23). — [sfincs_bmi.f90 lines 295–302](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/source/src/sfincs_bmi.f90); [commit d2dbd73](https://github.com/Deltares/SFINCS/commit/d2dbd7322254c449b00a73149e4b92305712e953). Confidence: high.
- **Comment naming groundwater coupling.** The comment "Allocating and initializing qext (used e.g. for BMI coupling with ground water model)" is in `sfincs_domain.f90` (line 2514). `sfincs_continuity.f90` lists "6. External source/sink qext (+/-) => added to qsrc here (BMI coupling)". The string is present in history at least since commit c8035ae (2025-03-19, v2.1.3 merge). — [sfincs_domain.f90 @db08c6a](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/source/src/sfincs_domain.f90). Confidence: high.
- **XMI status in the docs.** Known issue: the BMI "is up to date with XMI (BMI + extensions – Hughes et al. 2022), to be used with 'xmipy' … which is however not up to date with the latest CSDMS standard BMI implementation 2.0". The XMI upgrade is listed as alpha/beta in v2.2.0 col d'Eze (2025.01). "Upgraded BMI implementation exposing more variables to be altered" is alpha/beta in v2.3.0 mt Faber (2025.02). — [docs/developments.rst @db08c6a](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/developments.rst). Confidence: high.
- **XMI reference.** Hughes J.D., Russcher M.J., Langevin C.D., Morway E.D., McDonald R.R. (2022), "The MODFLOW Application Programming Interface for simulation control and software interoperability", Environmental Modelling & Software 148:105257, doi:10.1016/j.envsoft.2021.105257. — [bib entry in Hughes et al. draft](https://github.com/jdhughes-dev/nywsc_compound_flooding/blob/8be755e8f03703435a83e33f3fa7c1b837fc414f/docs/GP/Hughesetal_AWR_LISSCoupling.bib); the SFINCS docs cite "Hughes et al. 2022". Confidence: high for the DOI and title; the author list after Russcher is from memory, so verify it.
- **BMI 2.0 reference.** Hutton E., Piper M., Tucker G. (2020), "The Basic Model Interface 2.0: A standard interface for coupling numerical models in the geosciences", JOSS, doi:10.21105/joss.02109. Confidence: medium (DOI recalled, not seen in this session; verify).
- **No GitHub issue discusses BMI coupling.** Issue #48 "Update SFINCS BMI" (2023-10-25, closed) exists. Its body could not be read: the GitHub API was denied for this repo. — [Deltares/SFINCS#48](https://github.com/Deltares/SFINCS/issues/48). Confidence: high that it exists; content unknown.

**HurryWave (BMI)**
- Changelog: "Added wave enhanced roughness when bmi coupled with hurrywave" (alpha/beta, v2.3.0 mt Faber, 2025.02 release). It was implemented in PR #187 (2025-06-11), which added `uorb` and `update_apparent_roughness` to the BMI and the module `sfincs_wave_enhanced_roughness.f90`. — [developments.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/developments.rst); [commit 53ff1b0](https://github.com/Deltares/SFINCS/commit/53ff1b00aeed5943ed1ee521d4b0deba562fb320). Confidence: high.
- The Python side is in `cht_sfincs/xmi.py` (`SfincsXmi.update_apparent_roughness(uorb)`) and `cht_hurrywave/xmi.py` (Coastal Hazards Toolkit, Deltares-research). — [cht_sfincs xmi.py @8d29dcc (2026-06-18, M. van Ormondt)](https://github.com/Deltares-research/cht_sfincs/blob/8d29dcc7d4138e75001ecce1708137791cc3eb6f/cht_sfincs/xmi.py). Confidence: high.
- No paper on the SFINCS–HurryWave BMI coupling was found. The SFINCS publication list includes van Ormondt et al. (2023), "Wave effects in a rapid compound flood model", 17th International Workshop on Wave Hindcasting and Forecasting (no DOI). — [overview.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst). Confidence: medium.

**Real-time control through BMI (`cht_sfincs`)**
- `SfincsXmi` subclasses `xmipy.XmiWrapper`. `RTCCollection` / `RTC` compute weir and pump fluxes from SFINCS `zs` at source/target points (parameters `qpump`, `dzpump`, `zmin`, `t_relax`). Each step they reset `qext`, apply the fluxes, and relax them in time. In effect this is external structure control injected via `qext` — the same mechanism an SWMM coupler would use.
- `cht_sfincs` also references a `dzbext` (bed-change) pointer that is absent from `get_value_ptr` at db08c6a. This is a version mismatch, so the wrapper may target a branch.
- — [cht_sfincs/xmi.py](https://github.com/Deltares-research/cht_sfincs/blob/8d29dcc7d4138e75001ecce1708137791cc3eb6f/cht_sfincs/xmi.py); SFINCS commit "Rtc updates (#165)" 2025-05-16 [daf49f3](https://github.com/Deltares/SFINCS/commit/daf49f34eff5c20780bd774a4938a8db1339d141). Confidence: high.

**MODFLOW 6 (groundwater) via XMI**
- USGS NY Water Science Center code (J.D. Hughes), described in Q1. It is two-way and explicit: SFINCS `zs` drives MODFLOW GHB heads, and GHB flows return as `qext`. The case is North Fork/Greenport, Long Island. It is unpublished. — [nywsc_compound_flooding notebook](https://github.com/jdhughes-dev/nywsc_compound_flooding/blob/8be755e8f03703435a83e33f3fa7c1b837fc414f/notebooks-sfincs/step2_run_sfincs-modflow_variable_dt.ipynb). Confidence: high.
- The SFINCS project list includes "Modelling wave and groundwater-driven flooding across the Puget Sound, US West coast", with no citation and no coupling method stated. — [overview.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst). Confidence: medium.
- iMOD: no SFINCS coupling found.

**SnapWave (integrated, not BMI)**
- The stationary wave solver is compiled into SFINCS, with an infragravity balance since v2.1.1 Dollerup (2024). It follows Roelvink et al. (2025), egusphere-2025-492.
- Validation: Leijnse T. et al. (2025), "The importance of waves in large-scale coastal compound flooding: A case study of Hurricane Florence (2018)", Coastal Engineering, doi:10.1016/j.coastaleng.2025.104726.
- IG parametrisation: Leijnse et al. (2024), "Estimating nearshore infragravity wave conditions at large spatial scales", Frontiers in Marine Science, doi:10.3389/fmars.2024.1355095.
- — [developments.rst / overview.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst); [ScienceDirect S0378383925000316](https://www.sciencedirect.com/science/article/pii/S0378383925000316). Confidence: high.

**XBeach to SFINCS (offline)**
- On reef-lined coasts, SFINCS forced by XBeach-1D reproduced XBeach-2D flood extents with a 92 % hit rate. — ["Improved efficient physics-based computational modeling of regional wave-driven coastal flooding for reef-lined coastlines", Ocean Modelling (2024)](https://www.sciencedirect.com/science/article/pii/S1463500324000453); [USGS publication page](https://usgs.gov/index.php/publications/improved-efficient-physics-based-computational-modeling-regional-wave-driven-coastal). Confidence: medium (authors not retrieved).
- Majuro: Bertoncelj et al. (2021), EGU21-5418, doi:10.5194/egusphere-egu21-5418 (listed in the SFINCS docs). Confidence: medium.

**ADCIRC to SFINCS (offline, one-way)**
- Grimley L.E. et al. (2025), "Determining the Relative Contributions of Runoff, Coastal, and Compound Processes to Flood Exposure Across the Carolinas During Hurricane Florence", Water Resources Research, doi:10.1029/2023WR036727.
  - SFINCS is "one-way coupled" to ADCIRC at the coastal boundary, with ADCIRC water levels interpolated to the boundary cells.
  - USGS gauge discharge is applied upstream, below the reservoirs.
  - Tide-only ADCIRC runs are used for the runoff-only scenario.
  - — [NWS-hosted PDF](https://www.weather.gov/media/watercommunity/Webinar/2025Sep25/Water%20Resources%20Research%20-%202025%20-%20Grimley%20-%20Determining%20the%20Relative%20Contributions%20of%20Runoff%20%20Coastal%20%20and%20Compound.pdf). Confidence: medium-high.
- A follow-up: Grimley et al. (2026), "Emerging Importance of Compound Flooding in Future Tropical Cyclone Hazard Profiles", Earth's Future, doi:10.1029/2025EF007367. — [Wiley](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2025EF007367). Confidence: medium (the model chain was not verified).

**Global models (CaMa-Flood, GTSM) to SFINCS (offline)**
- Eilander D., Couasnon A., Leijnse T., Ikeuchi H., Yamazaki D., Muis S., Dullaart J., Haag A., Winsemius H.C., Ward P.J. (2023), "A globally applicable framework for compound flood hazard modeling", NHESS 23:823–846, doi:10.5194/nhess-23-823-2023.
  - SFINCS is set up automatically with HydroMT from global data and "coupled with a global hydrodynamic river routing model and a global surge and tide model".
  - Tested for cyclones Idai and Eloise in Sofala, Mozambique.
  - Compared with CaMa-Flood: CSI −0.01 to +0.09 and hit rate +0.11 to +0.22 better, false-alarm ratio 0.04–0.14 worse.
  - — [NHESS](https://nhess.copernicus.org/articles/23/823/2023/). Confidence: high for the citation; author list from memory, so verify.

**Wflow to SFINCS (offline)**
- The HydroMT case study repo "hydromt-wflow-sfincs" (D. Eilander) sets up an offline-coupled Wflow (v0.6.3) to SFINCS (v2.0.2) model. — [GitHub DirkEilander/hydromt-wflow-sfincs](https://github.com/DirkEilander/hydromt-wflow-sfincs). Confidence: medium-high.
- Vertegaal et al. (2026), NHESS 26:1417: in a local Sofala SFINCS model, Wflow discharge provides the fluvial input and D-Flow FM–SnapWave water levels provide the coastal input. — [NHESS supplement](https://nhess.copernicus.org/articles/26/1417/2026/nhess-26-1417-2026-supplement.pdf). Confidence: medium.
- The SFINCS docs mention "setup a offline coupled model together with the hydrological Wflow model that will provide boundary conditions as river discharge". — [example.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/example.rst). Confidence: high.
- A ResearchGate/conference item describes SFINCS receiving upstream river boundary conditions from Wflow and downstream water levels from Delft3D FM within one HydroMT workflow. — ["Creating large-scale compound flood models in an automated and reproducible way"](https://www.researchgate.net/publication/392224207_CREATING_LARGE-SCALE_COMPOUND_FLOOD_MODELS_IN_AN_AUTOMATED_AND_REPRODUCIBLE_WAY). Confidence: medium (authors and venue not retrieved).

**Delft3D FM / D-Flow FM to SFINCS (offline)**
- Tsunami offshore propagation in D-Flow FM, inundation in SFINCS: Röbke et al. (2021), JMSE 9(5):453, doi:10.3390/jmse9050453. — [overview.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst). Confidence: medium-high.
- Khan M.J.U., Durand F., Afroosa M., Coulet P., Bertin X., Mueller V., Krien Y., Wainwright C. (2025), "Tropical cyclone induced compound flooding in Madagascar: a coupled modeling approach", Natural Hazards 121(9), doi:10.1007/s11069-025-07209-z.
  - A 30 m compound flood model is nested in a regional tide-surge-wave model.
  - TC Batsirai (2022): hit ratio 0.83.
  - The SFINCS docs list this paper as a SFINCS application, but the abstract does not name the flood solver.
  - — [Springer](https://link.springer.com/article/10.1007/s11069-025-07209-z). Confidence: medium (SFINCS use not confirmed from the abstract).

**Forecasting and decision-support frameworks around SFINCS**
- **TC-FF.** Nederhoff K., van Ormondt M., Veeramony J., van Dongeren A., Álvarez Antolínez J.A., Leijnse T., Roelvink D. (2024), "Accounting for uncertainties in forecasting tropical-cyclone-induced compound flooding", GMD 17:1789–1811, doi:10.5194/gmd-17-1789-2024. An ensemble Monte Carlo of TC tracks drives SFINCS (tide, surge, rain). — [GMD](https://gmd.copernicus.org/articles/17/1789/2024/). Confidence: high.
- **Operational use in Delft-FEWS.** De Kleermaeker et al. (2022), Australia ([Informit](https://search.informit.org/doi/abs/10.3316/informit.916755150845355)). Also "Large-scale compound flooding in Australia in a Delft-FEWS early warning system" in the SFINCS project list. Confidence: medium.
- **FloodAdapt (Deltares-research)** wraps SFINCS (hazard) and Delft-FIAT (impact). In the SFINCS adapter:
  - a `Pump` measure becomes a SFINCS drainage structure (`stype="pump"`);
  - green infrastructure becomes SFINCS storage volume (`volfile`, from area × "infiltration depth" via a lookup table);
  - rainfall scenarios can be scaled by `rainfall_multiplier`;
  - there is no sewer or drainage-network measure.
  - — [FloodAdapt sfincs_adapter.py @b457941 (2026-07-03)](https://github.com/Deltares-research/FloodAdapt/blob/b4579417d55a1c2425e53cfd7ba1d530a98b6de0/flood_adapt/adapter/sfincs_adapter.py); [FloodAdapt docs](https://deltares-research.github.io/FloodAdapt/). Confidence: high.
- **CoSMoS.** Van Dongeren et al. (2023), "Forecasting hurricane impacts on coasts using Coastal Storm Modeling System (CoSMoS)", Coastal Engineering Proceedings / ICCE 2022, doi:10.1142/9789811275135_0242. — [overview.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst). Confidence: medium (exact chain not verified).
- **Typology.** Radfar et al. (2026), "Towards a typology for hybrid compound flood modeling", HESS 30:1397–1420. It classifies hybrid physics-statistical approaches (sequential/feedback/ensemble) and cites SFINCS-trained surrogates (treed Gaussian processes from 10,000 synthetic SFINCS events). It is not a coupling paper. — [HESS](https://hess.copernicus.org/articles/30/1397/2026/). Confidence: medium.
- **CSDMS model page:** [Model:SFINCS](https://csdms.colorado.edu/wiki/Model:SFINCS). SFINCS's BMI is not CSDMS BMI 2.0 compliant per the Deltares docs (see above). Confidence: medium.

### Inferences
- Every published SFINCS "coupling" in the peer-reviewed literature is one-way and offline. Upstream models supply boundary conditions or discharge, and SFINCS never feeds back. Two-way in-memory coupling through BMI/XMI exists only in code (HurryWave roughness, RTC, MODFLOW). The SFINCS–SWMM paper would therefore also be among the first peer-reviewed two-way BMI couplings of SFINCS of any kind.
- The SFINCS BMI is minimal: no fluxes or velocities, pointer access only, no sub-step hooks, and a `qext` unit change in September 2026. The paper should document:
  - the exact SFINCS commit;
  - `qext` in m³/s;
  - its use of `get_sfincs_cell_index` and `get_sfincs_cell_area`;
  - the `subgrid_z_zmin` vs `zb` bed reference, which `cht_sfincs` handles explicitly.
- The `cht_sfincs` RTC class is a direct precedent for "external controller writes `qext` from `zs`". It is worth citing as prior Deltares practice.

### Gaps
- No paper or report was found that describes the SFINCS–HurryWave BMI coupling, the RTC framework, or the BMI design.
- The full text of Khan et al. (2025) was not accessible, so it is unconfirmed whether SFINCS was the flood model.
- No documented SFINCS coupling with iMOD, Delft3D FM via BMI, or ADCIRC via BMI was found. "CoastalFloodModel" as a named framework was not found. Delft Dashboard / CoSMoS internals were not verified.

## Q3. How does SFINCS represent urban drainage, and how do existing urban/pluvial SFINCS studies represent drainage capacity?

### Takeaway
SFINCS has no pipe network. Drainage is represented only by:
- point-to-point drainage structures (pump, culvert, gate);
- infiltration-type losses (constant-rate, curve number, Green-Ampt, Horton, and from Hautacam a bucket model and a runoff coefficient);
- storage volume (green infrastructure);
- since the September 2026 code, a conceptual "Urban Drainage" zone module (piped_drainage / injection_well).

Published urban/pluvial SFINCS studies use calibrated infiltration as a drainage proxy, or they acknowledge drainage is missing.

### Cited Findings

**SFINCS-native options (docs and code at db08c6a)**
- **Urban Drainage module (`urbfile`, TOML).** It is "a simple bulk sink/source model". `piped_drainage` drains zone cells to one outfall cell, bidirectionally, with an optional check valve. `injection_well` removes water at a fixed rate until a capacity is reached. The docs stress that "urban drainage does not represent physical pipes or wells. It is a mass-balance abstraction", with "no pipe network, no hydraulic routing, no pressure head other than the difference between cell water level and outfall water level".
  - Capacity is per cell, `qmax = design_precip · A / 3.6e6`. Suggested values are "10–20 mm/hr for suburban residential, 20–40 mm/hr for dense city centre", or alternatively `max_outfall_rate` in m³/s.
  - Backflow follows `Q_back = qmax/√max(zb−zb_out, dh_design_min) · √(zs_out − zs)`.
  - Optional linear ramp `h_threshold` (typically 0.02–0.05 m), a whole-grid option, and outputs `urban_drainage_discharge` and `urban_drainage_cumulative_depth`.
  - Status: "Prototype … field-tested, but is still being improved iteratively", "Available from SFINCS v2026.02 Hautacam release onwards".
  - — [docs/input_urban_drainage.rst @db08c6a](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/input_urban_drainage.rst); [docs/parameters.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/parameters.rst). Confidence: high.
- **Release status.** The module came in with PR #355 (merged 2026-09-23). As of 2026-10-20 the latest tagged releases are `v2.4.0_Galibier_release` (2026-06-15) and `v2.4.1` (2026-08-18). There is no Hautacam tag yet. developments.rst describes the "v2.5.0 Hautacam 2026.02 release" with a status overview "at November 2026". So the Urban Drainage module, the new culvert and gate rules, the bucket and runoff-coefficient infiltration, and the m³/s `qext` exist only on `main`, not in a release. — [SFINCS releases](https://github.com/Deltares/SFINCS/releases); [developments.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/developments.rst). Confidence: high.
- **Drainage structures (`drnfile`, TOML from Hautacam).** They "move water between two grid cells without resolving the flow through a physical momentum equation". Types:
  - `pump` (legacy type 1);
  - `culvert_simple` (legacy 2, and check valve legacy 3);
  - `culvert` (rectangular or circular barrel, inlet/outlet control; new in Hautacam);
  - `gate` (inertial Bates-type update; generalises legacy types 4/5; rule-based open/close on observed water levels).
  - Earlier history: "Improved culvert and drainage pipe formulations" (v2.0.3 Cauberg, 2023); bugfix so structures cannot fall dry to NaN (v2.2.0; issue #112).
  - — [docs/input_structures.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/input_structures.rst); [issue #112](https://github.com/Deltares/SFINCS/issues/112). Confidence: high.
- **Shared source term.** "River discharges, drainage structures and urban drainage zones all add their discharge to the same source term in each grid cell". BMI `qext` is also added to that same `qsrc` in `update_continuity`. — [docs/input_forcing.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/input_forcing.rst); [sfincs_continuity.f90](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/source/src/sfincs_continuity.f90). Confidence: high.
- **Infiltration options (`inftype`).**
  - `c2d`: constant in time, mm/h.
  - `cna`/`cnb`: SCS curve number, with/without recovery.
  - `gai`: Green-Ampt. `hor`: Horton. Both since v2.0.3 (2023); recovery constants are computed "similar to SWMM".
  - Hautacam prototypes: `bkt` (bucket linear reservoir) and `r2d` (runoff coefficient, `qinf = (1 − runoff/100)·P`).
  - Infiltration acts only when rainfall is forced, and methods cannot be stacked.
  - — [docs/input.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/input.rst). Confidence: high.
- **Storage volume (`volfile`, from v2.3.0 mt Faber, 2025.02).** "Storage volume for green infrastructure … maximum storage volume of water per grid cell in m³", filled before runoff occurs. Subgrid mode only. — [docs/input.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/input.rst). Confidence: high.
- **Status diagram.** Its draw.io source contains boxes "Urban drainage coupling" and "Urban Drainage Concepts" as development items. The status category (GA/Stable/Prototype/Concept) could not be read from the XML. — [docs/figures/Overview_status_SFINCS.drawio](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/figures/Overview_status_SFINCS.drawio). Confidence: medium.

**Published studies**
- **Hoboken (and Jersey City), NJ: "High resolution simulation of urban compound flooding under climate impacts"**, Urban Climate (2026). DOI given by a secondary source as 10.1016/j.uclim.2026.102771 (unverified).
  - Street-scale SFINCS at 1.5 m, storm tide plus rainfall, validated on post-tropical cyclone Ida with crowdsourced reports. A secondary blog quotes 84.8 % agreement (unverified).
  - The stormwater system "(including underground pipes, manholes, catch basins, and pump stations) is not explicitly represented … the aggregate drainage capacity … is implicitly captured through calibrated infiltration parameters applied to paved surfaces. The calibrated infiltration rate thus represents the net effective drainage capacity".
  - The limitations section notes the missing pipes, combined sewer and pump stations.
  - — [ScienceDirect S2212095526000027](https://www.sciencedirect.com/science/article/pii/S2212095526000027); [NHERI SimCenter 2025 poster list (E. Amini)](https://simcenter.designsafe-ci.org/nheri-computational-symposium/2025/agenda/poster-presentations/water-hazards/). Confidence: medium (quotes from search snippets; author list not verified).
- **Eilander et al. (2023), NHESS (Sofala/Beira).** The authors note that SFINCS "drainage capacity … is likely underestimated due to the absence of small (subgrid-scale) streams in the model topography", leading to overestimated pluvial flooding. — [egusphere-2022-149 preprint PDF](https://egusphere.copernicus.org/preprints/2022/egusphere-2022-149/egusphere-2022-149.pdf); [NHESS 23:823](https://nhess.copernicus.org/articles/23/823/2023/). Confidence: medium (snippet-level; one search engine misattributed it to the Hoboken paper).
- **Sebastian A., Bader D.J., Nederhoff C.M., Leijnse T.W.B., Bricker J.D., Aarninkhof S.G.J. (2021)**, "Hindcast of pluvial, fluvial, and coastal flood damage in Houston, Texas during Hurricane Harvey (2017) using SFINCS", Natural Hazards 109:2343–2362, doi:10.1007/s11069-021-04922-3. Validated at 21 USGS gauges and 115 high-water marks; ≈ USD 8.3 bn uninsured residential loss. — [IDEAS/RePEc](https://ideas.repec.org/a/spr/nathaz/v109y2021i3d10.1007_s11069-021-04922-3.html). Confidence: high (citation); how drainage was represented was NOT verified.
- **Grimley et al. (2025), WRR (Hurricane Florence).** Explicitly validates SFINCS for pluvial, fluvial and coastal flooding over the Carolinas. Runoff-only, coastal-only and compound attribution, with a 0.05 m threshold. Abstract precursor: Grimley et al., "Flooding at the Fringe…", AGU Fall Meeting 2022 NH36A-03. — [WRR PDF](https://www.weather.gov/media/watercommunity/Webinar/2025Sep25/Water%20Resources%20Research%20-%202025%20-%20Grimley%20-%20Determining%20the%20Relative%20Contributions%20of%20Runoff%20%20Coastal%20%20and%20Compound.pdf); [ADS](https://ui.adsabs.harvard.edu/abs/2022AGUFMNH36A..03G/abstract). Confidence: medium-high; drainage/infiltration treatment not verified.
- **Leijnse et al. (2021).** SFINCS "includes spatially-varying infiltration and bed roughness terms". The Jacksonville/Hurricane Irma (2017) case combines fluvial, pluvial, tidal and wind-driven flooding. Infiltration is the only subsurface or drainage process. — [ScienceDirect abstract](https://www.sciencedirect.com/science/article/abs/pii/S0378383920304828). Confidence: medium-high.
- **Undocumented urban applications in the SFINCS project list:** "Modelling urban flooding in 100 global cities", "Modelling flash-floods in Turkey", "Modelling of urban flooding and adaptation measures in Ireland" and in the USA (Deltares 2022 special), "Modelling the 2023 dambreak in Libya (AXA Climate)". These are listed without publications. — [overview.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst). Confidence: medium (Deltares self-report).

**Non-SFINCS analogues (for positioning drainage proxies)**
- **Post-tropical cyclone Ida, NYC (COAWST, not SFINCS).** Soil infiltration and stormwater conveyance are parameterised as a single drainage rate; best fit 13 mm/h against high-water marks; RMSE 20 cm. — ["Pluvial and potential compound flooding in a coupled coastal modeling framework: New York City during post-tropical Cyclone Ida (2021)", HESS 29:2043 (2025)](https://hess.copernicus.org/articles/29/2043/2025/). Confidence: medium.
- **Review of sewer-drainage approximations in 2D models.** Rainfall reduction vs constant infiltration of 5–20 mm/h (citing Wang et al. 2018). Constant infiltration gives better flood recession; uniform-capacity assumptions lack physical basis. — [Frontiers in Environmental Science 2023, 10.3389/fenvs.2023.1134985](https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2023.1134985/full); ["Recent advances and future challenges in urban pluvial flood modelling", Urban Water Journal (2025)](https://www.tandfonline.com/doi/full/10.1080/1573062X.2024.2446528). Confidence: medium.

### Inferences
- The published SFINCS urban/pluvial literature represents drainage by spatially uniform or land-use-based "effective infiltration" calibrated against observations, or ignores it. The new Urban Drainage module formalises this as design-rate sinks with a lumped outfall, but it still has no network hydraulics, surcharge, or manhole-specific exchange. A SWMM coupling can be positioned as the physically based alternative to these proxies. The `piped_drainage` mode (design_precip in mm/h) is a natural baseline to compare against.
- The SFINCS docs explicitly call the Green-Ampt and Horton recovery "similar to SWMM", a small hook for the paper.
- Since all drainage sinks share `qsrc`, a coupler writing `qext` must not double-count capacity that is also represented by `urbfile`, `drnfile` or infiltration in the same cells.

### Gaps
- Not verified: how Sebastian et al. (2021), Grimley et al. (2025), Nederhoff et al. (2024, Salish Sea and SE Atlantic) or Barnard et al. (2025) represent storm-sewer capacity (e.g. curve number, constant infiltration, none). Full texts were inaccessible.
- No published application of the new Urban Drainage module was found. The docs' claim that it is "field-tested" has no citation.
- The Hoboken paper's authors, final DOI and calibrated infiltration value were not retrieved.

## Q4. Key SFINCS reference papers and validation for pluvial/flash floods

### Takeaway
The canonical citations are Leijnse et al. (2021, Coastal Engineering) for the model and van Ormondt et al. (2025, GMD) for subgrid. No dedicated quadtree paper was found. Pluvial validation exists only within hurricane compound-flood hindcasts (Harvey/Houston, Florence/Carolinas, Ida/Hoboken). There is a global riverine validation (HESS 2026). No dedicated flash-flood or urban-sewer validation paper was found.

### Cited Findings
- **Introduction paper.** Leijnse T., van Ormondt M., Nederhoff K., van Dongeren A. (2021), "Modeling compound flooding in coastal systems using a computationally efficient reduced-physics solver: Including fluvial, pluvial, tidal, wind- and wave-driven processes", Coastal Engineering 163:103796, doi:10.1016/j.coastaleng.2020.103796.
  - Simplified (local-inertial) shallow-water equations after Bates et al. (2010).
  - SFINCS "trunk revision 141" was the pre-open-source version.
  - — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0378383920304828); [SFINCS docs](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst). Confidence: high.
- **Subgrid paper.** van Ormondt M., Leijnse T., de Goede R., Nederhoff K., van Dongeren A. (2025), "Subgrid corrections for the linear inertial equations of a compound flood model – a case study using SFINCS 2.1.1 Dollerup release", Geoscientific Model Development 18:843, doi:10.5194/gmd-18-843-2025. Published 13 Feb 2025. — [GMD](https://gmd.copernicus.org/articles/18/843/2025/). Confidence: high for title and DOI; medium for the author list (verify).
- **No peer-reviewed quadtree paper.** Quadtree functionality appears only in release notes: quadtree netCDF output readable in QGIS (v2.4.0), `regular_output_on_mesh` (v2.1.1). The SFINCS docs' publication list has no quadtree paper. — [developments.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/developments.rst). Confidence: medium-high (absence).
- **Open-source release history.**
  - v2.0.0 Alpe d'Huez open-source release: 2022-11-16.
  - v2.4.0 Galibier: 2026-06-15.
  - v2.4.1: 2026-08-18.
  - Hautacam (v2.5.0, "2026.02"): not yet tagged on 2026-10-20.
  - The code is GPL-3.0, and executables are released under the "Deltares freeware license".
  - — [developments.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/developments.rst); [releases](https://github.com/Deltares/SFINCS/releases). Confidence: high.
- **Global riverine validation.** Sadana et al. (2026), "Validation of the open-source hydrodynamic model SFINCS on historical river floods at the global scale", HESS 30:5491 (preprint egusphere-2025-4387).
  - 499 events against satellite flood extents.
  - Mean CSI 0.42 for basins >1000 km² vs 0.29 for <50 km².
  - Observed discharge raised CSI from 0.39 to 0.67; a ~1 m DEM raised it from 0.37 to 0.57.
  - Dataset: zenodo 10.5281/zenodo.16759100.
  - — [HESS](https://hess.copernicus.org/articles/30/5491/2026/); [preprint](https://egusphere.copernicus.org/preprints/2025/egusphere-2025-4387/). Confidence: medium-high. It is riverine, not pluvial.
- **Pluvial components validated within compound-flood hindcasts:**
  - Sebastian et al. 2021 (Harvey, Houston);
  - Grimley et al. 2025 (Florence, Carolinas). Reported peak error 0.11 m; RMSE 0.92 m was reported by one search summary — treat as unverified. Depth >1 m at 96 % of insured-damage locations (preprint);
  - the Hoboken Ida study (Urban Climate 2026);
  - Leijnse et al. 2023, "Rapid modeling of compound flooding across broad coastal regions and the necessity to include rainfall driven processes: a case study of Hurricane Florence (2018)", ICCE 2022, doi:10.1142/9789811275135_0235.
  - — sources as in Q3; [USGS pub page](https://www.usgs.gov/index.php/publications/rapid-modeling-compound-flooding-across-broad-coastal-regions-and-necessity-include). Confidence: medium.
- **Other SFINCS references useful for context:**
  - Nederhoff et al. (2024), "Tropical or extratropical cyclones: what drives the compound flood hazard, impact, and risk for the United States Southeast Atlantic coast?", Natural Hazards 120:8779–8825, doi:10.1007/s11069-024-06552-x.
  - Barnard et al. (2025), "Projections of multiple climate-related coastal hazards for the US Southeast Atlantic", Nature Climate Change, doi:10.1038/s41558-024-02180-2.
  - Terlinden-Ruhl et al. (2025), NHESS 25:1353, doi:10.5194/nhess-25-1353-2025.
  - Lee et al. (2025), "Probabilistic storm surge and flood-inundation modeling of the Texas gulf coast using SFINCS", Coastal Engineering, doi:10.1016/j.coastaleng.2025.104721.
  - Goulart et al. (2024), NHESS 24:29–45, doi:10.5194/nhess-24-29-2024 (Sandy/NYC storylines).
  - Benito et al. (2025), NHESS, doi:10.5194/nhess-25-2287-2025.
  - — [overview.rst publication list](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/overview.rst). Confidence: medium-high (DOIs as listed by Deltares; not individually resolved).

### Inferences
- For the methods paper, cite Leijnse et al. (2021) for the solver and van Ormondt et al. (2025) for subgrid. For quadtree, cite the code version or commit and the docs. Cite Hughes et al. (2022) for XMI/xmipy.
- The absence of a pluvial-urban validation with sewer data for SFINCS is itself a gap the paper can name. Tang et al. (2025) shows such validation using storm-drain pressure sensors, but with Delft3D FM.

### Gaps
- Could not open full texts to confirm author lists for van Ormondt et al. (2025), Sadana et al. (2026), Grimley et al. (2025) and Radfar et al. (2026).
- No dedicated SFINCS flash-flood validation paper was found (Turkey and Libya appear only as unpublished projects). No pluvial benchmarking against UK EA 2D benchmark tests was found.

## Q5. Statements by Deltares about planned sewer/1D coupling for SFINCS

### Takeaway
A Deltares public-wiki project page (DEL194, "TKI SFINCS – DROMOS") states that SFINCS "is not able to compute the effect of storm drains and sewer systems". It plans to test two routes:
1. an internal drainage formulation;
2. a modular BMI coupling with an open-source 1D urban model such as D-Hydro 1D, tested on UK EA benchmarks and validated in Zwolle (NL) and Jacksonville (FL).

The first route appears to have materialised as the September 2026 Urban Drainage module. No public evidence of the D-Hydro 1D BMI coupling was found.

### Cited Findings
- **DROMOS project scope.** "At the moment the model is not able to compute the effect of storm drains and sewer systems". Detailed tools exist but are "computationally very expensive". The project will test "incorporating a drainage formulation in SFINCS" or "a modular framework that combines SFINCS with a coupled open-source 1D urban model like D-Hydro 1D", coupled "through a BMI". It will test on a simple hypothetical case and "UK Environment Agency benchmark" cases, and "validate it for a number of urban areas in the Netherlands and abroad such as Zwolle, Jacksonville (Florida, USA)". — [Deltares Public Wiki, "DEL194 – TKI SFINCS – DROMOS"](https://publicwiki.deltares.nl/spaces/TKIP/pages/343966166/DEL194+-+TKI+SFINCS+-+DROMOS). Confidence: medium. The page could not be opened (proxy 403); quotes come from two independent search-engine summaries. One summary dated the page about 14 months old (≈ mid-2025), which is unverified. Project dates, partners and deliverables were not retrieved.
- **D-HYDRO Suite 1D2D** is Deltares' successor to SOBEK-Urban for sewerage and urban drainage. — [Deltares product page](https://www.deltares.nl/en/software-and-data/products/sobek-and-delft3d-fm-suite-1d2d). Confidence: medium.
- **Urban Drainage module.** Implemented in SFINCS `main` via PR #355 (M. van Ormondt, 2026-09-23). It is documented as "Prototype" and is explicitly not a pipe network. The development-status diagram includes "Urban drainage coupling" and "Urban Drainage Concepts" items. — [input_urban_drainage.rst](https://github.com/Deltares/SFINCS/blob/db08c6a37a956e1a9b14b6f3c65c05834b2b80ce/docs/input_urban_drainage.rst); [commit d2dbd73](https://github.com/Deltares/SFINCS/commit/d2dbd7322254c449b00a73149e4b92305712e953). Confidence: high.
- **SFINCS issue tracker.** No GitHub issue or discussion in Deltares/SFINCS or hydromt_sfincs mentions sewer, SWMM or 1D coupling (searched 2026-10-20). — [Deltares/SFINCS issues](https://github.com/Deltares/SFINCS/issues). Confidence: medium-high.
- **USGS precedent outside Deltares.** USGS uses D-Flow FM rather than SFINCS for its coastal–groundwater–sewer coupling. Its draft paper cites Leijnse et al. (2021) only as an example of surface-only compound flood modelling. — [Hughes et al. draft](https://github.com/jdhughes-dev/nywsc_compound_flooding/blob/8be755e8f03703435a83e33f3fa7c1b837fc414f/docs/GP/Hughesetal_AWR_LISSCoupling.tex). Confidence: high (draft content).

### Inferences
- Deltares has publicly framed sewer representation as a recognised SFINCS limitation, and BMI-based 1D coupling as a candidate solution. A SFINCS–SWMM paper fits this agenda but uses an open, non-Deltares sewer model (SWMM via PySWMM/toolkit), unlike the D-Hydro 1D plan. The paper should cite the DROMOS page as "planned work" (with access date). It should present its own coupling as complementary to the conceptual Urban Drainage module, i.e. network-resolving vs lumped.
- The `qext` refactor (m³/s, shared `qsrc`) shipped together with the Urban Drainage module in PR #355. This suggests Deltares is preparing the source-term infrastructure that any 1D coupling, including SWMM, would use. This is an inference, not stated in the docs.

### Gaps
- Could not retrieve the DROMOS page itself: date, duration, partners (e.g. Zwolle municipality, Jacksonville/USGS), status or results.
- No Deltares conference abstract (EGU/AGU/HIC/ICCE 2025–2026) on SFINCS sewer coupling was found. It could exist but was not indexed by the search tool.
- Unknown whether the Hautacam release (planned for about November 2026 per the docs) will include any external-coupling documentation for drainage.
