# Methods for coupling EPA SWMM (and 1D sewer models in general) with 2D overland-flow models in dual-drainage (1D/2D) urban flood modelling. Status as of October 2026

Research notes for the methods section of a paper that couples SFINCS (2D, adaptive time step) with SWMM 5 (via pyswmm) using an explicit, volume-conserving weir/orifice exchange, SWMM's SLOT surcharge method and under-relaxation of the exchange discharge.

**How these notes were produced, and their limits.** The research environment had restricted network access. Publisher sites (ScienceDirect, ASCE, IWA, MDPI, T&F, Wiley, EPA, ResearchGate, readthedocs) could not be fetched directly. Evidence comes from three kinds of source:

- **[CODE]: verified directly in source code.** These are shallow clones made on 2026-10-20 of:
  - USEPA/Stormwater-Management-Model, branch `develop`, SWMM 5.2.4 (`VERSION 52004`), last commit 2025-02-23;
  - ItziModel/itzi (main) and ItziModel/itzi-core 0.8.0, last commit 2026-09-30;
  - pyswmm 2.2.0, released 2026-10-01;
  - Deltares/SFINCS (main), last commit 2026-10-19;
  - FloodGroup/LISFLOOD-SWMM-Coupling v1.2.0, released 2026-10-16.

  These findings carry **high** confidence for what the code does.
- **[SEARCH]: abstracts and snippets returned by web search.** The full text was not read. These findings are rated medium or low.
- **[MEMORY]: bibliographic details recalled rather than seen.** Each one is flagged and marked "verify".

Confidence ratings appear in brackets after each finding.

---

## Q1. Exchange formulations at inlets and manholes: equations, regimes, and discharge coefficients with their origin

### Takeaway
The dominant formulation since SIPSON (Djordjević et al. 2005) and Chen et al. (2007) is a regime-switching set of equations at each linked node:

- **Free weir:** surface to sewer, when the sewer head is below the crest.
- **Submerged weir or orifice:** surface to sewer, when the crest is drowned.
- **Orifice:** sewer to surface, during surcharge.

The only coefficient set that was experimentally calibrated for a manhole in both steady and unsteady conditions is Rubinato et al. (2017). Its values are free weir ≈ 0.54, submerged weir ≈ 0.056 and orifice ≈ 0.167, and Itzï uses them as defaults. These values are tied to that paper's reference area (manhole plan area) and reference length (manhole perimeter). They are not comparable with textbook Cd ≈ 0.6 values, and grated-inlet studies report very different ranges.

### Cited Findings

**Canonical lineage**
- SIPSON (Djordjević, Prodanović, Maksimović, Ivetić & Savić 2005) handles the surface–sewer interaction through "equivalent inlet" boundary conditions with three cases:
  - free inflow, with the inlet acting as a weir;
  - submerged inflow, with the inlet acting as an orifice;
  - outflow.

  The sewer side solves the full Saint-Venant equations with a Preissmann scheme and a conjugate-gradient solver. Citation: Djordjević S., Prodanović D., Maksimović Č., Ivetić M., Savić D. (2005) "SIPSON – simulation of interaction between pipe flow and surface overland flow in networks", *Water Science & Technology* 52(5):275–283, doi:10.2166/wst.2005.0143 — [Semantic Scholar](https://www.semanticscholar.org/paper/SIPSON--simulation-of-interaction-between-pipe-flow-Djordjevi%C4%87-Prodanovi%C4%87/3e9d5fb7132b153fe41e1e694169a348702b872f); [ResearchGate](https://www.researchgate.net/publication/7518895_SIPSON_-_Simulation_of_Interaction_between_Pipe_flow_and_Surface_Overland_flow_in_Networks). [SEARCH; medium. The three-case structure is consistently reported; the coefficient values were not retrieved.]
- A secondary description says the SIPSON-type weir length equals the manhole perimeter and the head equals the incoming surface depth. Velocity head is usually neglected, and the real exchange is deflected under high-velocity street flow — [ResearchGate figure page](https://www.researchgate.net/figure/Hydraulic-grade-lines-along-street-dashed-lines-combined-sewer-solid-lines-and_fig4_7518895). [SEARCH; low-medium]
- Chen A.S., Djordjević S., Leandro J., Savić D. (2007) "The urban inundated model with bidirectional flow interaction between 2D overland surface and 1D sewer networks", NOVATECH 2007, Lyon, GRAIE, Vol. 1, pp. 465–472. This is the origin of the bidirectional 1D/2D (SIPSON + 2D) weir/orifice linkage. A secondary source says the manhole is treated as fully submerged, and the orifice equation applies, once the upstream depth above the crest passes a threshold — [ResearchGate](https://www.researchgate.net/publication/279638194_The_urban_inundation_model_with_bidirectional_flow_interaction_between_2D_overland_surface_and_1D_sewer_networks). [SEARCH; medium for the citation, low for details. No coefficient values were retrieved.]
- Leandro J., Chen A.S., Djordjević S., Savić D.A. (2009) "Comparison of 1D/1D and 1D/2D coupled (sewer/surface) hydraulic models for urban flood simulation", *Journal of Hydraulic Engineering* 135(6):495–504, doi:10.1061/(ASCE)HY.1943-7900.0000037. The minor and major systems are linked at manholes with weir/orifice equations. The paper concludes that 1D/2D needs fewer assumptions than 1D/1D — [ASCE](https://ascelibrary.org/doi/abs/10.1061/(ASCE)HY.1943-7900.0000037). [SEARCH; high for the citation, medium for content. Coefficient values were not retrieved.]
- A 2024 WST paper classifying manhole drainage states reports two things about the Leandro et al. (2010) method. It matches measurements well in the pure free-weir and pure orifice states. It deviates significantly in the intermediate (transition) states — [IWA WST 89(1):146](https://iwaponline.com/wst/article/89/1/146/99221/Classification-and-description-of-the-drainage). [SEARCH; medium. Relevant to regime-switching discontinuities.]

**Rubinato et al. 2017: the calibrated manhole set used by Itzï**
- Citation: Rubinato M., Martins R., Kesserwani G., Leandro J., Djordjević S., Shucksmith J. (2017) "Experimental calibration and validation of sewer/surface flow exchange equations in steady and unsteady flow conditions", *Journal of Hydrology* 552:421–432, doi:10.1016/j.jhydrol.2017.06.024 — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0022169417304286); [White Rose](https://eprints.whiterose.ac.uk/id/eprint/121383/). The author list is [MEMORY]; verify it.
- In steady state the paper found that weir/orifice formulae describe the exchange in the physical model, and it provides new calibrated coefficients per regime. For unsteady tests the instantaneous exchange discharge could not be measured, so the equations were tested by numerical simulation — [Aston PDF record](https://publications.aston.ac.uk/id/eprint/47123/). [SEARCH; medium-high]
- Reported calibrated ranges, which reflect experimental error:
  - free weir C_w ≈ 0.493–0.587;
  - submerged weir ≈ 0.054–0.057;
  - orifice ≈ 0.159–0.174 for one test series (S3) and 0.159–0.161 for another (S4). The S3/S4 labels were not defined in the snippet.

  The orifice calibration used pressure head at a sensor in the upstream pipe — [ResearchGate](https://www.researchgate.net/publication/317690858_Experimental_calibration_and_validation_of_sewersurface_flow_exchange_equations_in_steady_and_unsteady_flow_conditions). [SEARCH; medium. Check the paper's coefficient table before quoting the ranges.]
- **[CODE] Itzï / itzi-core** implements the Rubinato 2017 set, citing it in `const.py` ("coefficients taken from Rubinato et al. (2017)") and in `drainage.py` — [itzi-core drainage.py](https://github.com/ItziModel/itzi-core/blob/main/src/itzi_core/drainage.py); [const.py](https://github.com/ItziModel/itzi-core/blob/main/src/itzi_core/const.py). [CODE; high]
  - Defaults: `ORIFICE_COEFF = 0.167`, `FREE_WEIR_COEFF = 0.54`, `SUBMERGED_WEIR_COEFF = 0.056`.
  - Notation: H_1D = SWMM node head; H_2D = surface water-surface elevation (z + h) of the linked cell; Z_c = crest elevation. In Itzï the crest defaults to the DEM elevation of the cell.
  - A = node "surface area". It is taken from SWMM's global `MIN_SURFAREA` option, one value for all nodes.
  - P = weir width = 2√(πA), the circumference of a circle of area A.
  - Regime selection:
    - **orifice** if H_1D > H_2D (sewer → surface), or if H_1D < H_2D with H_1D > Z_c and (H_2D − Z_c) > A/P;
    - **free weir** if H_1D < H_2D and H_1D < Z_c;
    - **submerged weir** if H_1D < H_2D, H_1D > Z_c and (H_2D − Z_c) < A/P;
    - otherwise no flow.
  - Equations, with h_up = max(H_2D, H_1D) − Z_c:
    - orifice: Q = C_o · A · √(2g·|H_1D − H_2D|);
    - free weir: Q = (2/3) · C_w · P · h_up^{3/2} · √(2g);
    - submerged weir: Q = C_sw · P · h_up · √(2g·h_up).

    The sign follows H_1D − H_2D.
- The Itzï release notes give the version history [CODE; high] — [RELEASE.rst](https://github.com/ItziModel/itzi/blob/main/RELEASE.rst):
  - v17.8 (2017-08-08): outflow from the drainage network always uses the orifice equation, "following Rubinato et al. 2017".
  - v17.11: coefficients became configurable.
  - v18.2 (2018-02-19): regime choice among orifice, free weir and submerged weir based on the relative water levels and the crest elevation.

**Other experimental coefficient sources**
- Bazin P.-H., Nakagawa H., Kawaike K., Paquier A., Mignot E. (2014) "Modeling flow exchanges between a street and an underground drainage pipe during urban floods", *Journal of Hydraulic Engineering* 140(10):04014051, doi:10.1061/(ASCE)HY.1943-7900.0000917. A physical model of a street, inlet and pipe validated an analytical exchange model, with 1D/2D Rubar3/Rubar20 simulations. The global behaviour was reproduced; local street-flow perturbations were not — [ResearchGate](https://www.researchgate.net/publication/273405135_Modeling_Flow_Exchanges_between_a_Street_and_an_Underground_Drainage_Pipe_during_Urban_Floods). [SEARCH; high for the citation, medium for content]
- Secondary sources cite Bazin et al. (2014) for weir coefficients of 0.53 < C_w < 0.67 (non-grated rectangular inlets, subcritical flow), and "Sabtu" for 0.4–0.6 (grated rectangular inlets) — [MDPI Hydrology 8(4):162](https://www.mdpi.com/2306-5338/8/4/162). [SEARCH; low-medium, secondary]
- Rubinato M., Lee S., Martins R., Shucksmith J.D. (2018) "Surface to sewer flow exchange through circular inlets during urban flood conditions", *Journal of Hydroinformatics* 20(3):564–576 — [IWA](https://iwaponline.com/jh/article/20/3/564/37915/Surface-to-sewer-flow-exchange-through-circular). It reports calibrated weir coefficients of 0.115–0.372 and orifice coefficients of 0.349–2.038 for grated circular inlets. [SEARCH; medium. The author list and the DOI 10.2166/hydro.2017.184 are MEMORY; verify. Orifice coefficients > 1 show that the coefficient absorbs the choice of reference area.]
- Rubinato M., Martins R., Kesserwani G., Leandro J., Djordjević S., Shucksmith J. (2018) "Quantification of energy losses at a surcharging manhole", *Urban Water Journal*, doi:10.1080/1573062X.2018.1424217 — [T&F PDF link](https://www.tandfonline.com/doi/pdf/10.1080/1573062X.2018.1424217?needAccess=true); [ResearchGate](https://www.researchgate.net/publication/322991724_Quantification_of_energy_losses_at_a_surcharging_manhole). A review quoted from this line of work gives about 0.53–0.6 (weir) and 0.4–0.46 (orifice) for rectangular inlets in subcritical flow. [SEARCH; low-medium. Volume, pages and the author list were not verified.]
- Kitsikoudis V., Erpicum S., Rubinato M., Shucksmith J.D., Archambeau P., Pirotton M., Dewals B. (2021) "Exchange between drainage systems and surface flows during urban flooding: quasi-steady and dynamic modelling in unsteady flow conditions", *Journal of Hydrology* 602:126628, doi:10.1016/j.jhydrol.2021.126628 — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0022169421006764); [Aston](https://publications.aston.ac.uk/id/eprint/46748/). [SEARCH; high for the citation, medium for content; coefficient values not retrieved]
  - Weir/orifice exchange "has not been well validated in unsteady flow" because of uncertain discharge coefficients and head losses.
  - Discharge coefficients calibrated in steady subcritical flow were constant over the tested range.
  - The quasi-steady and dynamic models, which include local head losses explicitly, performed well in unsteady flow.
- Moodi et al. (2024, *J. Flood Risk Management*, doi:10.1111/jfr3.12953) criticise the weir/orifice line of work for relying on empirical energy-loss coefficients that are hard to set without site-specific calibration — [Wiley](https://onlinelibrary.wiley.com/doi/10.1111/jfr3.12953). [SEARCH; medium]
- Noh S.J., Lee S., An H., Kawaike K., Nakagawa H. (2016) "Ensemble urban flood simulation in comparison with laboratory-scale experiments: Impact of interaction models for manhole, sewer pipe, and surface flow", *Advances in Water Resources* (November 2016) — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0309170816303876). [SEARCH; medium. Vol. 97, pp. 25–37 and doi:10.1016/j.advwatres.2016.08.015 are MEMORY; verify.]
  - Monte Carlo ensembles of weir/orifice interaction models reproduced the experiments with high accuracy.
  - Sewer–manhole parameters were less uncertain than sewer–surface parameters.
  - Unsteady data were more informative than steady data.
  - Optimal parameters varied with flow condition, but only marginally.
- Leandro J., Lopes P., Carvalho R., Páscoa P., Martins R., Romagnoli M. (2014) "Numerical and experimental characterization of the 2D vertical average-velocity plane at the center-profile and qualitative air entrainment inside a gully for drainage and reverse flow", *Computers & Fluids* 102:52–61, doi:10.1016/j.compfluid.2014.05.032. This is gully (inlet) hydraulics for drainage and reverse flow. Follow-up work (Lopes et al. 2015) found that gully discharge coefficients differ across three outlet surcharge levels — [Sheffield PDF](https://sheffield.ac.uk/media/7438/download?attachment=); [ResearchGate](https://www.researchgate.net/publication/264834160_Numerical_and_experimental_investigation_of_a_gully_under_surcharge_conditions). [SEARCH; medium for the citation. No coefficient values were retrieved.]
- Martins R., Leandro J., Chen A.S., Djordjević S. (2017) "A comparison of three dual drainage models: shallow water vs local inertial vs diffusive wave", *Journal of Hydroinformatics* 19(3):331–348, doi:10.2166/hydro.2017.075 — [IWA](https://iwaponline.com/jh/article/19/3/331/3536/A-comparison-of-three-dual-drainage-models-shallow); [White Rose accepted MS](https://eprints.whiterose.ac.uk/id/eprint/115324/3/JHI.acceptedwimages.pdf). Three 2D surface models were each coupled to the same SIPSON sewer model and compared through the sewer–surface exchange volume and through head and discharge at linked manholes. Simplified surface models gave results comparable to the full dynamic SWE at lower cost. [SEARCH; high for the citation, medium for content]

**Inlet representation matters as much as the coefficients**
- Jang J.-H., Chang T.-H., Chen W.-B. (2018) "Effect of inlet modelling on surface drainage in coupled urban flood simulation", *Journal of Hydrology* 562:168–180, doi:10.1016/j.jhydrol.2018.05.010 — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0022169418303391). [SEARCH; high for the citation, medium for content]
  - It compared three approaches: manhole-only, inlet→manhole, and inlet→own sewer node. The test was a 2015 storm in Taipei.
  - Including street inlets reproduced maximum flood extent much better.
  - Manhole-only drainage of surface water was inefficient over time.
  - The inlet-node approach was the most efficient.
- Chang T.-J., Wang C.-H., Chen A.S. (2015) "A novel approach to model dynamic flow interactions between storm sewer system and overland surface for different land covers in urban areas", *Journal of Hydrology* 524:662–679, doi:10.1016/j.jhydrol.2015.03.014. The coupling technique depends on land cover: rain falls on the 2D model for paved areas and reaches the sewer through inlets; roof drainage and gully inlets are represented — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0022169415001857). [SEARCH; medium. Whether the 1D engine is SWMM was not confirmed.]
- CityCAT 1D/2D explicitly simulates every storm-drain inlet. Each inlet connects to its nearest manhole, and exchange uses a "single linking element" approach based on the Bernoulli and energy-loss equations — [MDPI Water 9(12):925 (2017), "Urban Flood Simulation Using Synthetic Storm Drain Networks"](https://www.mdpi.com/2073-4441/9/12/925). [SEARCH; medium. The authors (Bertsch, Glenis, Kilsby) are MEMORY; verify.]

**Alternative exchange law used by a 2026 open-source coupler**
- FloodGroup LISFLOOD-SWMM v1.2.0 (GitHub, released 2026-10-16) [CODE (documentation in the repo); high for what the code documents. It is **not peer-reviewed**.] — [coupling_methodology.md](https://github.com/FloodGroup/LISFLOOD-SWMM-Coupling/blob/main/docs/coupling_methodology.md)
  - Branch tolerance: ε = 10⁻³ m.
  - (a) Surcharge, sewer → surface, when H_1D − Z > ε and H_1D − H_2D > ε: Q = min(C_0·A_0·√(2g(H_1D − H_2D)), Q_out,max, (V_stored + V_pending)/dt).
  - (b) Free inflow, when H_1D ≤ Z + ε and H_2D − Z > ε: Q = C_w·w·(H_2D − Z)·√(2g(H_2D − Z)).
  - (c) Submerged inflow, when H_1D ≥ Z − ε and H_2D − H_1D > ε: Q = C_1·A_1·√(2g(H_2D − H_1D)).
  - Z = max(z_rim, z_DEM).
  - Coefficients are set per node in a user table. No defaults are tied to the literature.

**SWMM's own (1D/1D) inlet capability**
- SWMM 5.2.x contains Street/Channel inlet functions (`inlet.c`). They compute the capture efficiency of grate, curb, combination, slotted, drop and custom inlets with FHWA HEC-22 methods (Brown et al. 2013, FHWA-NHI-10-009). This is the native 1D/1D dual-drainage alternative to 1D/2D coupling — [inlet.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/inlet.c). [CODE; high]

### Inferences
- The Rubinato 2017 coefficients are "lumped" coefficients. They are referenced to manhole plan area (orifice) and perimeter (weir) and absorb local head losses, which is why the submerged weir (0.056) and orifice (0.167) values are about an order of magnitude below a textbook Cd ≈ 0.6. A SFINCS–SWMM paper adopting them must also adopt the same reference geometry (A = manhole area, P = perimeter); otherwise the coefficients are not transferable.
- Itzï's A/P switching threshold equals D/4 for a circular manhole. It decides between the submerged-weir and orifice equations for drowned inflow. The literature notes discontinuities in the transition states (WST 2024). Both points argue for an explicit statement of how continuity of Q across regime boundaries is handled.
- Coefficient ranges from grated inlets (0.115–0.372 weir; 0.349–2.038 orifice) and from Bazin (0.53–0.67) are not interchangeable with manhole values. Sensitivity analysis over a coefficient range is the defensible choice.

### Gaps
- Exact coefficient values and equation forms in Djordjević et al. (2005), Chen et al. (2007) and Leandro et al. (2009) were not retrieved. The full texts were inaccessible. The 0.5-type defaults often quoted for SIPSON were **not** verified and must not be cited without checking.
- Rubinato et al. (2017): the exact published equation forms (in particular whether the submerged weir uses the head difference or the upstream depth), the S3/S4 definitions and the manhole and pipe dimensions were not seen. Only Itzï's implementation was seen.
- The "Martins et al. 2018" works (e.g., the *Water Resources Research* 2018 paper on velocity fields near manhole grates) and Kitsikoudis et al. (2021) coefficient values were not retrieved.

---

## Q2. Coupling architectures and existing SWMM–2D (and other 1D–2D) couplings: linking mechanism, time-step synchronisation, explicit vs implicit exchange

### Takeaway
Almost all SWMM–2D couplings are **online, loosely coupled and explicit**: the two engines solve their own equations, and an exchange discharge, computed from the previous state, is held constant over a synchronisation interval. They are linked through the SWMM shared library: the C DLL/API (`swmm_step`, `swmm_setValue`), pyswmm, or a modified SWMM source. The usual clock is SWMM's routing step: the CFL-limited 2D model sub-steps and clips its last step to land on the SWMM time (Iber-SWMM, Itzï, IberSWMM+). Fixed synchronisation intervals are the alternative (HC-SURF, Buttinger-Kreuzhuber et al., LISFLOOD-SWMM interval mode). Truly implicit or single-matrix 1D–2D solutions exist only where both domains sit in one solver, such as PCSWMM 2D (2D mesh as SWMM links and nodes) or own-code models (Fan et al. 2017).

### Cited Findings

**DLL / API linking of SWMM 5.1+**
- Leandro J., Martins R. (2016) "A methodology for linking 2D overland flow models with the sewer network model SWMM 5.1 based on dynamic link libraries", *Water Science & Technology* 73(12):3017–3026 — [Semantic Scholar](https://www.semanticscholar.org/paper/A-methodology-for-linking-2D-overland-flow-models-Leandro-Martins/6d6de23fea4bc5db029d340b430a66e5d98ee000); [ResearchGate](https://www.researchgate.net/publication/301275866_A_methodology_for_linking_2D_overland_flow_models_with_the_sewer_network_model_SWMM_51_based_on_dynamic_link_libraries). [SEARCH; high for the citation, medium for details. The DOI 10.2166/wst.2016.171 is MEMORY; verify.]
  - The coupling functions are written inside the same SWMM DLL, giving two-way exchange during the run **without editing SWMM's original code**.
  - The method is applicable to any 2D overland model.
  - It was validated on a real case with an existing coupled model.
  - Citing papers describe the surface model as a 2D diffusive wave model with an explicit scheme, with SWMM providing the surcharge hydrographs.
- **pyswmm** (Python wrapper of the SWMM toolkit). Citation: McDonnell B.E., Ratliff K., Tryby M.E., Wu J.J.X., Mullapudi A. (2020) "PySWMM: The Python Interface to Stormwater Management Model (SWMM)", *Journal of Open Source Software* 5(52):2292, doi:10.21105/joss.02292 — [CITATION.cff](https://github.com/pyswmm/pyswmm/blob/main/CITATION.cff). [CODE; high. The volume and issue "5(52)" are MEMORY.]
  - Current release 2.2.0 (2026-10-01); its default dependency is `swmm-toolkit<1.0.0`.
  - Optional extras pin older engines: `swmm5.2.4` → `swmm-toolkit<0.18.0`, `swmm5.1.15` → `<=0.10.0` — [pyproject.toml](https://github.com/pyswmm/pyswmm/blob/main/pyproject.toml).
  - `Node.generated_inflow(q)` calls `setNodeInflow`. The docstring says the value "is held constant in the model until it is redefined" — [nodes.py](https://github.com/pyswmm/pyswmm/blob/main/pyswmm/nodes.py).
  - `Simulation.step_advance(s)` "advances the model by X number of seconds instead of intervening at every routing step. This does not change the routing step" — [simulation.py](https://github.com/pyswmm/pyswmm/blob/main/pyswmm/simulation.py).
- **[CODE] SWMM 5.2.4 toolkit semantics:**
  - `swmm_setValue(swmm_NODE_LATFLOW, …)` sets `Node.apiExtInflow`.
  - In `addExternalInflows()` (routing.c) the value is added to the node's lateral inflow.
  - A **negative** value is accepted and booked as a system outflow in the mass balance (`massbal_addOutflowFlow`).
  - Node depth is clipped at zero (`if (yNew < 0) yNew = 0.0` in dynwave.c), so withdrawing more than a node stores creates a SWMM continuity error.

  Sources: [routing.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/routing.c); [swmm5.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/swmm5.c); [dynwave.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/dynwave.c). [CODE; high]

**Itzï (GRASS GIS + SWMM)**
- Courty L.G., Pedrozo-Acuña A., Bates P.D. (2017) "Itzï (version 17.1): an open-source, distributed GIS model for dynamic flood simulation", *Geoscientific Model Development* 10(4):1835–1847, doi:10.5194/gmd-10-1835-2017 — [GitHub README](https://github.com/ItziModel/itzi). [CODE/README; high. Note that the GMD paper describes v17.1, which **predates** the bidirectional SWMM coupling. That coupling was introduced in v17.7 (2017-07-31) per RELEASE.rst.]
- Linking mechanism over time:
  - The SWMM codebase was originally embedded.
  - Since **v25.4 (2025-04-21)** Itzï "relies on pyswmm instead of an embedded SWMM codebase" and requires GRASS ≥ 8.4.
  - From v26.10 (unreleased) the computation moves to `itzi-core`.
  - The documentation still calls the SWMM coupling experimental.

  Sources: [RELEASE.rst](https://github.com/ItziModel/itzi/blob/main/RELEASE.rst); [conf_file.rst](https://github.com/ItziModel/itzi/blob/main/docs/conf_file.rst). [CODE; high]
- Time-step synchronisation in itzi-core [CODE; high] — [simulation.py](https://github.com/ItziModel/itzi-core/blob/main/src/itzi_core/simulation.py); [simulation_schedule.py](https://github.com/ItziModel/itzi-core/blob/main/src/itzi_core/simulation_schedule.py):
  1. SWMM is advanced with `swmm_step()`, one native routing step.
  2. The elapsed SWMM step becomes the drainage "deadline".
  3. The exchange flows are computed with the SWMM head after that step and the current surface state, then injected with `generated_inflow(-Q)`.
  4. The 2D step end is chosen as the earliest of the CFL step and all scheduled deadlines (`select_step_end`), so surface steps land exactly on SWMM step boundaries.
  5. The 2D sink/source is held constant (as Q/cell area) until the next SWMM step.
  - The exchange is therefore explicit and lagged by one SWMM step.
  - Surface defaults: CFL 0.7, `dtmax` 5 s, inertia weighting θ 0.9.

**Iber-SWMM and IberSWMM+**
- Sañudo E., Cea L., Puertas J. (2020) "Modelling pluvial flooding in urban areas coupling the models Iber and SWMM", *Water* 12(9):2647, doi:10.3390/w12092647 — [MDPI](https://www.mdpi.com/2073-4441/12/9/2647); [ResearchGate](https://www.researchgate.net/publication/345401077_Modelling_Pluvial_Flooding_in_Urban_Areas_Coupling_the_Models_Iber_and_SWMM). [SEARCH; high for the citation, medium for details]
  - Iber calls SWMM step by step through the DLL.
  - Each model solves its own equations.
  - Exchange happens only through inlets and manholes, every time the models are synchronised, "assuming a constant water discharge during the whole time step".
  - The Iber time step is the minimum of its Courant limit and the time remaining to the next SWMM time.
  - The cumulative exchanged volume is evaluated over the Iber sub-steps that make up one SWMM step.
  - Inlet water goes instantly to the associated manhole.
  - Free weir, submerged weir and orifice equations "from previous studies" were implemented.
  - When a manhole floods, SWMM's node flood discharge is transferred to Iber as a source.
- Sañudo E., García-Feal O., Montalvo C., Alvarado-Vicencio R., Hofmann J. (2025) "IberSWMM+: a high-performance computing solver for 2D-1D pluvial flood modelling in urban environments", *Journal of Hydrology* 651:132603, doi:10.1016/j.jhydrol.2024.132603 (online December 2024) — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0022169424019991); [ADS](https://ui.adsabs.harvard.edu/abs/2025JHyd..65132603S/abstract). [SEARCH; high for the citation, medium for details. The volume is from ADS; the author list is from Semantic Scholar/ADS snippets.]
  - It is the GPU/parallel version.
  - Each model computes its time step independently via Courant; elapsed-time synchronisation uses the SWMM time as the master clock.
  - Exchange happens only at synchronisation steps.
  - CPU↔GPU memory transfers are a significant bottleneck, and SWMM itself can become the bottleneck.
  - A city case of about 6 million cells with about 3000 nodes and 3000 links went from 72 h to 20 min.
  - Parallel and sequential versions gave consistent results.

**SWMM–MOHID Land (offline)**
- "Development of a 1D/2D Urban Flood Model Using the Open-Source Models SWMM and MOHID Land", *Sustainability* 15(1):707 (2023), doi:10.3390/su15010707 — [MDPI](https://dx.doi.org/10.3390/su15010707); [ResearchGate](https://www.researchgate.net/publication/366803457_Development_of_a_1D2D_Urban_Flood_Model_Using_the_Open-Source_Models_SWMM_and_MOHID_Land). [SEARCH; medium. The authors were not retrieved.]
  - **Offline**, file-based cycles: a MOHID Land run, then a SWMM run, exchanging time-series files.
  - MOHID provides the inlet-captured flow per manhole and the surface level per manhole.
  - SWMM uses the captured flow as nodal inflow and the surface level as the boundary condition for overflowing manholes.
  - A new MOHID module was added; SWMM was left unmodified.
  - MOHID Land uses an explicit variable time step.
  - Tested on a synthetic street and on Albufeira, Portugal.

**LISFLOOD-FP–SWMM**
- A coupled SWMM + LISFLOOD-FP 1D/2D model for Shiqiao Creek District, Dongguan, with two historical events. *Journal of Hydrology* (2017), "Scenario-based projections of future urban inundation within a coupled hydrodynamic model framework: A case study in Dongguan City, China" — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0022169417300987). [SEARCH; medium for existence and content. The author list (Wu X., Wang Z., Guo S. et al.), volume 547:428–442 and doi:10.1016/j.jhydrol.2017.02.020 are MEMORY; verify. A review attributes it to "Zeng and Wu".]
- FloodGroup LISFLOOD-SWMM v1.2.0 (2026): LISFLOOD-FP 8.1 (ACC and FV1 solvers, CPU/OpenMP and CUDA) plus a **modified** EPA SWMM 5.1.015 in a single executable. It adds a custom SWMM API (`swmm_advanceCoupled(T)`, `swmm_getNodeAvailableCoupledVolume`, …) and a new `COUPLED` outfall type with volume-based continuity — [GitHub](https://github.com/FloodGroup/LISFLOOD-SWMM-Coupling). [CODE/docs; high for the description; not peer-reviewed]

**Cellular-automata surface models**
- Guidolin M., Chen A.S., Ghimire B., Keedwell E.C., Djordjević S., Savić D.A. (2016) "A weighted cellular automata 2D inundation model for rapid flood analysis", *Environmental Modelling & Software* 84:378–394 — [ResearchGate](https://www.researchgate.net/publication/305812554_A_weighted_cellular_automata_2D_inundation_model_for_rapid_flood_analysis). WCA2D belongs to the CADDIES ("Cellular Automata Dual-DraInagE Simulation") framework — [Exeter CADDIES](https://www.exeter.ac.uk/research/centres/cws/resources/caddies/). [SEARCH; medium. Volume and pages are MEMORY.]
- Chang et al. (2021, *Journal of Hydrology*), "Overland-gully-sewer (2D-1D-1D) urban inundation modeling based on cellular automata framework": WCA2D (with spatial roughness) for overland flow, and SWMM for the gully and sewer flow — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0022169421010519). Zeng et al. (2022) coupled SWMM and WCA2D **unidirectionally** and compared it with LISFLOOD-FP + SWMM — [IJDRS](https://journal.hep.com.cn/ijodrs/EN/10.1007/s13753-022-00416-3). [SEARCH; medium. Exchange details not retrieved.]

**GPU couplings**
- RiverFlow2D-GPU UD + SWMM: "An Efficient GPU Implementation of a Coupled Overland-Sewer Hydraulic Model with Pollutant Transport", *Hydrology* 8(4):146 (2021) — [MDPI](https://www.mdpi.com/2306-5338/8/4/146). [SEARCH; medium. The authors were not retrieved.]
  - Time steps must be "homogenised".
  - SWMM routing is treated as having no time-step restriction, so the explicit surface solver "governs the temporal advance".
  - At every time step an algorithm compares surface depth, pipe pressure head and the surface–invert distance to estimate the manhole exchange.
  - Validated on a UK Environment Agency test case.
- Buttinger-Kreuzhuber A., Konev A., Horváth Z., Cornel D., Schwerdorf I., Blöschl G., Waser J. (2022) "An integrated GPU-accelerated modeling framework for high-resolution simulations of rural and urban flash floods", *Environmental Modelling & Software* 156:105480 — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1364815222001839); [VRVis](https://www.vrvis.at/en/publications/PB-VRVis-2022-027). [SEARCH; medium. The DOI was not verified.]
  - Full-SWE GPU runoff model coupled with SWMM.
  - The sewer model is interleaved with an a-priori coupling time step ΔT_C, which is also the upper limit of both simulators' steps. "If not stated otherwise, it is set to 1 s."
  - The two run **in parallel**, each with the other's state frozen over ΔT_C.
- GAST-GCSE + SWMM: coupled by calling the SWMM DLL with added external functions, using the **same time step** in both models. [SEARCH; low. Only a snippet was seen; the citation was not retrieved.]
- **HiPIMS-SWMM:** no source describing a HiPIMS–SWMM coupling was found.

**Other SWMM–2D pairings**
- Seyoum S.D., Vojinovic Z., Price R.K., Weesakul S. (2012) "Coupled 1D and noninertia 2D flood inundation model for simulation of urban flooding", *Journal of Hydraulic Engineering* 138(1):23–34, doi:10.1061/(ASCE)HY.1943-7900.0000485. SWMM5 is coupled to a new 2D non-inertia ADI model. The coupling is two-way, with exchange computed from water-level differences. The 2D time step is controlled by iteration — [Semantic Scholar](https://www.semanticscholar.org/paper/Coupled-1D-and-Noninertia-2D-Flood-Inundation-Model-Seyoum-Vojinovic/aad7e06ed42fb195a5a0906723eb06f4ac9b1b9d). [SEARCH; high for the citation, medium for details]
- Fan Y., Ao T., Yu H., Huang G., Li X. (2017) "A coupled 1D-2D hydrodynamic model for urban flood inundation", *Advances in Meteorology* 2017:2819308, doi:10.1155/2017/2819308 — [Wiley](https://onlinelibrary.wiley.com/doi/10.1155/2017/2819308). [SEARCH; high for the citation, medium for content]
  - This is an **own-code** model, not SWMM: 1D finite-difference Saint-Venant plus a 2D finite-volume model with **implicit dual time-stepping**.
  - An overflow equation handles drainage-to-ground exchange.
  - Its 1D results were nearly identical to SWMM for Changsha.
  - The explicit 1D–2D approach is "tightly bound by its Courant number", while dual time stepping is unconditionally stable.
- Yang, Ma, Zhang (2022) "Urban pluvial flood modeling by coupling raster-based two-dimensional hydrodynamic model and SWMM", *Water* 14(11):1760, doi:10.3390/w14111760 — [MDPI](https://doi.org/10.3390/w14111760). [SEARCH; medium. Authors per the search snippet.]
  - A raster 2D model (simple inertial formulation) with an adaptive CFL time step is coupled to SWMM.
  - Manhole exchange enters as point sources.
  - "The flow rate of the point source needs to be limited" by a dedicated equation.
  - This is the closest published analogue to a raster/quadtree SFINCS–SWMM design.
- An SWMM–TELEMAC-2D "tight coupling" (*Sustainable Cities and Society*, 2024) — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S2210670724006188). [SEARCH; low. Details not retrieved.]
- HC-SURF (SWMM-based 1D + 2D surface) with **fixed-time synchronisation**: Sim & Kim (2024), "An urban flood model development coupling the 1D and 2D model with fixed-time synchronization", *Water* 16(19):2726, doi:10.3390/w16192726 — [MDPI](https://www.mdpi.com/2073-4441/16/19/2726). A follow-up compares HC-SURF with PCSWMM and InfoWorks ICM, exchanging level and flow between each manhole or inlet and its surface cell at each synchronisation point — [MDPI Water 17(24):3575](https://www.mdpi.com/2073-4441/17/24/3575). [SEARCH; medium. The authors' full names were not verified.]

**Commercial and industry tools**
- **TUFLOW:** from the 2023-03 releases, EPA SWMM is available as a 1D solver alongside ESTRY. The sources disagree on the exact build (2023-03-AD vs AE vs AF). [SEARCH; medium]
  - SWMM pits/inlets link to the 2D domain with SX (flow) connections.
  - Culverts use an HX (head) link upstream because of SWMM limitations.
  - Inlets surcharge into the 2D domain when the 1D head exceeds the 2D water level.
  - On-sag/on-grade treatment is decided dynamically.

  Sources: [TUFLOW 2023-03 release notes, SWMM](https://docs.tuflow.com/classic-hpc/release/2023-03-AE/SWMM-TUFLOW-1.html); [manual: 1D Network Domains, EPA SWMM](https://docs.tuflow.com/classic-hpc/manual/2023-03/OneD-SWMM-1.html); [TUFLOW wiki](https://wiki.tuflow.com/EPA_SWMM_to_TUFLOW).
- **PCSWMM 2D:** the 2D surface is a mesh of cells represented as SWMM junctions joined by open conduits and solved by the SWMM5 dynamic-wave engine. 1D and 2D are therefore solved in **one** engine with one time step. Catch basins are linked to 2D cells with orifices — [ICWMM 2012](https://www.icwmm.org/Archive/2012-C021-29/swmm5-pcswmm-2d-application-for-urban-dual-drainage-modeling); [ICWMM 2014](https://www.icwmm.org/Archive/2014-C023-07/floodplain-and-dual-drainage-analysis-using-an-integrated-1d-2d-swmm-model-simi-valley-california); [CHI journal C454](https://www.chijournal.org/C454). [SEARCH; medium. Vendor and conference sources.]
- **HEC-RAS:**
  - Externally coupled SWMM–HEC-RAS-2D: the node flooding rate from SWMM is fed to HEC-RAS 2D (Karaj, Iran, *J. Environmental Management* 2024) — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0301479724038362). [SEARCH; medium]
  - Native storm-pipe networks are reported from HEC-RAS 6.6, with a claim that HEC-RAS 6.7 pipe networks match SWMM — [rashms blog](https://rashms.com/blog/comparing-hec-ras-pipe-networks-function-with-swmm/). [SEARCH; low, vendor blog]
- **MIKE (DHI):** the user chooses the 1D–2D inlet equation (orifice, weir or exponential) — [CEST 2017 paper](https://cest2017.gnest.org/sites/default/files/presentation_file_list/cest2017_00708_oral_paper.pdf). [SEARCH; low-medium]

**SFINCS-side facts relevant to the target coupling [CODE; high; Deltares/SFINCS main, 2026-10-19]**
- The SFINCS BMI (`sfincs_bmi.f90`) exposes `update_until`, `get_time_step`, and pointers to `zs`, `zb`, `subgrid_z_zmin` and **`qext`**. The source comment says `qext` is an "external source/sink per cell in m3/s (positive = water added to the cell) … added to qsrc in update_continuity. NOTE: before the qsrc restructuring qext was a rate in m/s; couplers that still provide m/s must now multiply by the cell area." — [sfincs_bmi.f90](https://github.com/Deltares/SFINCS/blob/main/source/src/sfincs_bmi.f90)
- In the regular-grid continuity update, sources and sinks are applied as `zs = max(zs + qsrc·dt/A, zb)`. A sink larger than the available volume is silently clipped at the bed — [sfincs_continuity.f90](https://github.com/Deltares/SFINCS/blob/main/source/src/sfincs_continuity.f90)
- SFINCS now contains a conceptual urban-drainage sink/source module (`sfincs_urban_drainage.f90`) with polygon zones of type `piped_drainage` or `injection_well`. [CODE; high] — [sfincs_urban_drainage.f90](https://github.com/Deltares/SFINCS/blob/main/source/src/sfincs_urban_drainage.f90)
  - Per-cell drain rate: q = min(ramp·q_max, h·A/dt), with ramp = min(h/h_threshold, 1).
  - Backflow: −c_b·√(−Δzs), suppressible by a check valve.
  - It is **not** a pipe-network model.
- No published SFINCS–SWMM coupling was found by search. [SEARCH; medium confidence in absence]

### Inferences
- A SFINCS–pyswmm design maps naturally onto the Itzï/Iber pattern:
  1. SWMM step, or a fixed interval via `step_advance`.
  2. Compute the exchange from the SWMM node head and the SFINCS `zs`.
  3. Write `qext` (m³/s) for SFINCS and `generated_inflow` for SWMM.
  4. Call SFINCS `update_until(t_SWMM)`.

  The paper should state explicitly whether the exchange is evaluated before or after the SWMM step (Itzï: after; LISFLOOD-SWMM: before, from accumulated 2D volumes) and which model is the master clock.
- The Itzï precedent (orifice area and weir perimeter from SWMM's single global `MIN_SURFAREA`) is a simplification. Per-node manhole or inlet geometry is preferable and should be reported.
- The `qext` unit change is a reproducibility hazard. The paper should state the SFINCS version or commit and that `qext` is in m³/s.

### Gaps
- No primary information was found on HiPIMS–SWMM, OpenFOAM–SWMM or FastFlood–sewer couplings. If they exist they are not prominent. Citing them requires further search.
- No independent documentation of PCSWMM's internal 2D-cell/junction mapping or of MIKE FLOOD's stabilisation parameters (e.g., limits on flow per unit head) was retrieved.
- Inunda (arXiv:2607.09614, 2026; GPU local-inertial differentiable solver): one search summary said it exchanges with SWMM5 once per coupling interval via signed nodal lateral inflow; another found no SWMM details in the abstract. The sources conflict; treat as unverified — [arXiv](https://arxiv.org/abs/2607.09614).
- Glenis V., Kutija V., Kilsby C.G. (2018) "A fully hydrodynamic urban flood modelling system representing buildings, green space and interventions", *Environmental Modelling & Software* 109:272–292 is the standard CityCAT citation. It is MEMORY and was not verified by search.

---

## Q3. Numerical stability: oscillations in explicit 1D–2D exchange, SWMM surcharge (EXTRAN vs SLOT), stabilisation techniques and mass-balance treatment

### Takeaway
- **SLOT exists.** The SLOT (Preissmann slot) surcharge option was introduced in SWMM **5.1.013**, confirmed in the code's update history. EXTRAN remains the default.
- **What SLOT changes.** It removes the switch to the EXTRAN surcharge algorithm, which applies no under-relaxation and reports nodal depth only up to the crest. SWMM's slot is wide (about 1% of conduit width at large depth), so pressure-wave celerity is low. That is benign for flood studies, but Pachaly et al. show it misrepresents fast closed-pipe transients.
- **Exchange stabilisers in use.** Explicit-exchange stabilisers found in working codes are:
  - under-relaxation of the exchange flow (Itzï, factor 0.8);
  - damping by 0.5 when the flow reverses direction (Itzï; v18.2 forced a zero-flow step instead);
  - head-difference tolerances that stop regime chattering (LISFLOOD-SWMM, 1 mm);
  - available-volume limiters on both donors (h·A/dt for the 2D cell; stored plus pending volume for the SWMM node);
  - linear ramps near zero depth (SFINCS urban drainage).
- **Mass balance.** Mass conservation is achieved most robustly by exchanging volumes accumulated over the interval rather than instantaneous rates (LISFLOOD-SWMM, Iber-SWMM).

### Cited Findings

**SWMM surcharge handling (verified in source, SWMM 5.2.4)** — [dynwave.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/dynwave.c); [dwflow.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/dwflow.c); [project.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/project.c). [CODE; high]
- **Update history (dynwave.c header), Build 5.1.013:**
  - "SurchargeMethod option used to decide how node surcharging is handled."
  - "Storage nodes allowed to pressurize if their surcharge depth > 0."
  - "Minimum flow needed to compute a Courant time step modified."
- **Default method:** `SurchargeMethod = EXTRAN` (project.c). The keyword options are `EXTRAN` and `SLOT` (enums.h: "original EXTRAN method", "Preissmann slot method").
- **Crown cutoffs:** `EXTRAN_CROWN_CUTOFF = 0.96` and `SLOT_CROWN_CUTOFF = 0.985257`.
- **Slot width** (`getSlotWidth`) applies only to closed conduits with y/y_full ≥ the crown cutoff:
  - w_slot = w_max · 0.5423 · exp(−(y/y_full)^2.4) (Sjöberg formula);
  - w_slot = 0.01·w_max for y/y_full > 1.78.

  These two branches meet at about 0.01·w_max. The formula was computed from the code.
- **Without SLOT,** conduit flow depths are capped at y_full.
- **Node depth update:** Picard iterations with `OMEGA = 0.5` under-relaxation, `DEFAULT_HEADTOL = 0.005 ft`, `DEFAULT_MAXTRIALS = 8` and `MINTIMESTEP = 0.001 s`. The default minimum nodal surface area is `DEFAULT_SURFAREA = 12.566 ft²` (about 1.17 m², a 4-ft-diameter manhole). The continuity volume change uses a trapezoidal average: dV = 0.5·(oldNetInflow + dQ)·dt.
- **EXTRAN surcharged nodes:** a node is surcharged when its depth exceeds the crown of its highest link. The depth change then comes from dQ/(Σ∂Q/∂H) **without under-relaxation**, with a 0.6 correction for upstream terminal nodes and an exp(−15f) blending with the last free-surface area near the crown. Under SLOT this branch is skipped and the free-surface/slot-area update is always used.
- **Flooding:** the maximum non-flooded depth is fullDepth + surDepth (if ponding is off) or fullDepth (if ponding is on). Above it:
  - ponding off: the excess becomes `overflow = dV/dt` (lost unless a coupler returns it) and depth is held at y_max;
  - ponding on: the volume is stored above the node.
- **Practitioner guidance:** a SWMM model "will behave differently" after switching to SLOT, "though sometimes the Slot option helps improve the model stability". Default slot width per the OpenSWMM forum is about 1% of conduit width — [swmm5.org](https://swmm5.org/2019/03/01/new-engine-and-gui-features-in-infoswmm-14-7-which-is-based-on-epa-swmm-5-1-013/); [OpenSWMM forum](https://www.openswmm.org/Topic/19390/preissmann-slot-method). [SEARCH; low-medium, practitioner sources]

**Pachaly et al. on SWMM SLOT**
- Pachaly R.L., Vasconcelos J.G., Allasia D.G., Tassi R., Bocchi J.P.P. (2020) "Comparing SWMM 5.1 calculation alternatives to represent unsteady stormwater sewer flows", *Journal of Hydraulic Engineering* 146(7):04020046 — [ResearchGate](https://www.researchgate.net/publication/337914550_Comparing_SWMM_51_Calculation_Alternatives_to_Represent_Unsteady_Stormwater_Sewer_Flows). [SEARCH; medium. The DOI 10.1061/(ASCE)HY.1943-7900.0001762 and the author list are MEMORY; verify.]
  - Citing papers report that SLOT gives more numerically stable results for rapid pipe filling.
  - They also report SLOT as more accurate for fully pressurised unsteady flow when time steps are small.
  - Spatial discretisation is a key accuracy factor.
- Pachaly R.L., Vasconcelos J.G., Allasia D.G. (2021) "Evaluating SWMM capabilities to simulate closed pipe transients", *Journal of Hydraulic Research* — [ResearchGate](https://www.researchgate.net/publication/350439632_Evaluating_SWMM_capabilities_to_simulate_closed_pipe_transients). [SEARCH; medium. Volume and pages conflict between sources (60(1):74–81 vs 1–8); verify.]
  - The original Preissmann slot in SWMM 5.1.013 cannot represent fast closed-pipe transients: "the slot adopted is too wide, creating unrealistic transient", and acoustic celerity is too low.
  - Modified slots based on predefined celerity, plus artificial spatial discretisation and CFL-based routing steps, give satisfactory transients.
  - Known Preissmann slot deficiencies: it cannot sustain negative pressures, and it produces spurious oscillations when flow becomes pressurised.
  - A narrower variant gave a celerity of about 250 m/s ("C250", "C250S").
- Pachaly, Vasconcelos, Allasia (2021) "Surge predictions in a large stormwater tunnel system using SWMM", *Urban Water Journal*: a narrower slot improved deep-tunnel simulations — [Auburn dissertation](http://auetd.auburn.edu/bitstream/handle/10415/7991/Pachaly_Dissertation_Final.pdf?sequence=2&isAllowed=y). [SEARCH; medium]
- A later paper notes that SWMM (as of v5.2.4) uses a slot width of 1% of the conduit diameter, which overstates storage and understates friction losses. Narrower slots require smaller time steps — [ResearchGate (Improved SWMM modeling for rapid pipe filling, JHE)](https://www.researchgate.net/publication/369094638_Improved_SWMM_Modeling_for_Rapid_Pipe_Filling_Incorporating_Air_Behavior_in_Intermittent_Water_Supply_Systems). The fixed SWMM slot "can produce shocks and numerical instabilities at free-surface/pressurized transitions" — "Generalized, Dynamic, and Transient-Storage Form of the Preissmann Slot", *J. Hydraulic Engineering*, doi:10.1061/JHEND8.HYENG-13609. [SEARCH; low-medium]

**Stabilisation of the explicit exchange in working couplers**
- **Itzï / itzi-core (current code)** [CODE; high] — [drainage.py](https://github.com/ItziModel/itzi-core/blob/main/src/itzi_core/drainage.py):
  1. **Relaxation:** Q_new ← 0.8·Q_new + 0.2·Q_old (`RELAXATION_FACTOR = 0.8`).
  2. **Flow limiter:** flow leaving the 2D cell is capped at h·A_cell/Δt_drainage, where Δt_drainage is the SWMM step just completed.
  3. **Reversal damping:** if the sign flips relative to the previous step, Q_new is multiplied by 0.5 (`DAMPING_FACTOR = 0.5`).

  The constants are commented "coefficients for drainage coupling stability".
- **Itzï v18.2 (2018) rule:** "the coupling flow cannot reverse direction within one time step. It must spend one time step at zero first … meant to reduce oscillations when surface and drainage water elevations are similar." It also limited inflow "to prevent negative depth in the surface model" — [RELEASE.rst](https://github.com/ItziModel/itzi/blob/main/RELEASE.rst). [CODE; high]
- **Itzï mass-balance guard:** the simulation raises `MassBalanceError` if the "created volume ratio" exceeds a threshold (`MAX_ERROR = 0.05`). [CODE; high]
- **LISFLOOD-SWMM (2026)** [CODE/docs; high for content; not peer-reviewed] — [coupling_methodology.md](https://github.com/FloodGroup/LISFLOOD-SWMM-Coupling/blob/main/docs/coupling_methodology.md):
  - A regime-switch tolerance ε = 10⁻³ m "keeps the regime from switching on round-off".
  - Surcharge outflow is capped by (V_stored + V_pending)/dt at the node.
  - Inflow is capped by h·Δx·Δy/(n·dt), shared among the n manholes in a cell, and by Q_in,max.
  - Rainfall and infiltration are applied **before** the exchange so the two sinks cannot remove the same water.
  - "Exchange volumes, not instantaneous rates": 2D steps accumulate V_i += Q_i·dt; SWMM receives V/T as a constant rate and is advanced exactly T.
  - Returned outfall and node-flood volumes are applied as point sources.
  - A combined water-balance residual is audited, including pending exchange.
  - Inside SWMM, components with `COUPLED` outfalls use a backward-Euler volume update with donor-flow scaling (up to eight passes) and a relative tolerance of about 1e-8. The run stops rather than continuing with a mass error.
- **Iber-SWMM (2020):** constant discharge over each synchronisation step, with cumulative volume over the Iber sub-steps — [MDPI Water 12(9):2647](https://www.mdpi.com/2073-4441/12/9/2647). [SEARCH; medium]
- **SFINCS urban drainage:** dt-capped drain q = min(ramp·q_max, h·A/dt) with a linear ramp below `h_threshold`. This regularises the rate near zero depth — [sfincs_urban_drainage.f90](https://github.com/Deltares/SFINCS/blob/main/source/src/sfincs_urban_drainage.f90). [CODE; high]
- **Oscillations reported in the literature:** in Martins et al. (2017), "oscillations are seen in GWM [gravity-wave/local-inertial] and SWE after 3 h" in the coupled runs — [White Rose accepted MS](https://eprints.whiterose.ac.uk/id/eprint/115324/3/JHI.acceptedwimages.pdf). [SEARCH; low-medium. Snippet only; the mechanism was not stated.]
- **Explicit vs implicit:** Fan et al. (2017) state that explicit 1D–2D coupling is tightly limited by the Courant number, while implicit dual time-stepping is unconditionally stable — [Wiley](https://onlinelibrary.wiley.com/doi/10.1155/2017/2819308). A Martins et al. (2017) excerpt notes that SIPSON (an implicit Preissmann-scheme sewer model) was chosen because it is unconditionally stable and cheaper than explicit 1D models — [ResearchGate](https://www.researchgate.net/publication/312876687_A_comparison_of_three_dual_drainage_models_Shallow_water_vs_local_inertial_vs_diffusive_wave). [SEARCH; medium]

**Mass-balance pitfalls verified in code**
- **SWMM** books a negative API lateral inflow as system outflow and clips node depth at 0. Withdrawing more than the node stores produces a continuity error. [CODE; high]
- **SWMM** integrates net node inflow trapezoidally (dV = 0.5·(Q_old + Q_new)·dt). LISFLOOD-SWMM explicitly "holds this rate constant at both ends of SWMM's trapezoidal lateral-inflow integration, so the volume SWMM receives equals the volume removed from the surface" — [dynwave.c](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/dynwave.c); [coupling_methodology.md](https://github.com/FloodGroup/LISFLOOD-SWMM-Coupling/blob/main/docs/coupling_methodology.md). [CODE; high]
- **SFINCS** clips `zs` at the bed for sinks. An exchange sink larger than h·A/dt_SFINCS is silently truncated, so water is effectively created. [CODE; high]

### Inferences
- **Why explicit exchange oscillates.** Weir and orifice laws have dQ/dΔH ∝ ΔH^{−1/2}, which is unbounded as ΔH → 0. Combined with the small storage of a manhole node (a SWMM default of about 1.17 m² when ponding is off) and an explicit, lagged exchange, this makes the coupling stiff exactly when the surface level and the manhole head converge. That is when Itzï reports oscillations. The remedies documented above all target this: relaxation, reversal damping, tolerance bands, ramps and linearisation of Q(ΔH) below a small ΔH.
- **SFINCS sub-steps.** SFINCS has an adaptive step, and several SFINCS steps are taken per exchange interval. A rate-based limiter computed with the interval length T does not protect individual SFINCS sub-steps from overshoot when h drops during the interval. Two approaches are mass-safe:
  - (a) exchange volumes: accumulate the 2D→1D volume actually removed per SFINCS step and pass V/T to SWMM, as LISFLOOD-SWMM does;
  - (b) cap Q at h·A/T at the start of the interval, so the cell cannot be over-drained even with constant Q over T.

  In both cases the SWMM→2D outflow should be capped by the node's available volume. With SLOT, a SWMM node does not hold head above the rim beyond the surcharge depth unless ponding or surDepth allow it. This affects the orifice head H_1D used for outflow.
- **Head reported to the coupler.** Under EXTRAN, nodal depth is limited by fullDepth + surDepth, and any excess becomes "overflow". A coupler that computes outflow only from H_1D via an orifice (the Itzï approach) must either set a large surcharge depth so H_1D can exceed the ground, or also transfer SWMM's `overflow` (the Iber-SWMM and LISFLOOD-SWMM approach). Otherwise water may be lost from both models.
- **Under-relaxation in the literature.** Relaxation factors are not reported as calibrated constants. Itzï's 0.8 and 0.5 are code defaults without published justification. The paper should present its relaxation factor as a numerical parameter and test sensitivity to it.

### Gaps
- No peer-reviewed study was found that quantifies oscillation amplitude in an explicit SWMM–2D exchange as a function of relaxation factor or exchange interval.
- The exact release date of SWMM 5.1.013 was not seen in a primary EPA document; secondary sources indicate 2018. EPA's update-history PDF could not be fetched; the build number was verified in code.
- Pachaly 2020: the numerical results (e.g., recommended routing steps for SLOT vs EXTRAN) were not retrieved.
- No source was found on how MIKE FLOOD or InfoWorks ICM linearise the exchange near zero head. Any statement about commercial-code stabilisation would be unverified.

---

## Q4. Exchange (synchronisation) interval: guidance and effect on results

### Takeaway
There is no universal recommended value. Published practice falls into three groups:

- **SWMM's routing step as the exchange interval,** with the 2D model sub-stepping (Iber-SWMM, IberSWMM+, Itzï; Itzï's surface `dtmax` is 5 s).
- **A fixed coupling step of about 1 s** that also caps both models' steps (Buttinger-Kreuzhuber et al. 2022).
- **User-chosen fixed intervals** (HC-SURF; LISFLOOD-SWMM `coupleint T`).

The only systematic test found (Sim & Kim 2024) reports that errors in surcharge and discharge grow with the synchronisation interval and peaks are underestimated, while total volume and peak timing are little affected. The authors call the errors overall "minimal".

### Cited Findings
- **Sim & Kim (2024), HC-SURF** — [MDPI Water 16(19):2726](https://www.mdpi.com/2073-4441/16/19/2726). [SEARCH; medium. The tested interval values were not retrieved.]
  - Laboratory validation, then real urban watersheds with various synchronisation times.
  - "As the synchronization time increased, the errors in surcharge and discharge also increased, though overall they remained minimal."
  - Peak discharge tended to be underestimated as the interval grew; total discharge volume and peak timing stayed similar.
  - Motivation: "The time step for 1D–2D flow exchange is generally much smaller than that for 1D models, which significantly reduces model efficiency."
- **Buttinger-Kreuzhuber et al. (2022)** — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1364815222001839). [SEARCH; medium]
  - The coupling step ΔT_C is set a priori, default 1 s.
  - It is also the upper limit for each simulator's step.
  - The models run in parallel with frozen partner states over ΔT_C.
- **Iber-SWMM / IberSWMM+:** SWMM's step is the synchronisation time because it is typically larger than Iber's CFL step. The Iber step is clipped to the SWMM time, and exchange occurs only at synchronisation — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0022169424019991); [MDPI](https://www.mdpi.com/2073-4441/12/9/2647). [SEARCH; medium]
- **Itzï:** the exchange interval equals SWMM's own routing step (`swmm_step()`), and surface steps are clipped to land on it — [simulation.py](https://github.com/ItziModel/itzi-core/blob/main/src/itzi_core/simulation.py). [CODE; high]
- **LISFLOOD-SWMM (2026):** `coupleint step` exchanges every 2D step (T = dt); `coupleint T` accumulates over T s. Per the documentation, "A shorter interval couples the two models more tightly. A longer interval reduces the number of SWMM calls and, on the GPU, the number of host–device transfers." — [coupling_methodology.md](https://github.com/FloodGroup/LISFLOOD-SWMM-Coupling/blob/main/docs/coupling_methodology.md). [CODE/docs; high for content; not peer-reviewed]
- **pyswmm** provides `step_advance(seconds)` to set a coupling interval independent of SWMM's routing step, and `generated_inflow` holds a rate constant until redefined. These are the primitives for a fixed-interval exchange — [simulation.py](https://github.com/pyswmm/pyswmm/blob/main/pyswmm/simulation.py). [CODE; high]
- **Other reported values:** a GPU SWMM coupling reportedly tested fixed synchronisation steps from 5 s to 300 s (*Water Resources Management* 2022, s11269-022-03158-5), but no source confirmed this. A hyper-resolution 1D–2D study required time steps ≤ 0.05 s — [NOAA repository PDF](https://repository.library.noaa.gov/view/noaa/49525/noaa_49525_DS1.pdf). [SEARCH; low. The citations and the context of the values were not verified.]

### Inferences
- For SFINCS (adaptive CFL step, typically seconds) coupled with SWMM (dynamic-wave routing step, typically 1–5 s or less under surcharge), the defensible choices are:
  - (i) exchange at every SWMM routing step, with SFINCS clipped via `update_until`, following the Itzï and Iber pattern; or
  - (ii) a fixed interval T of the order of 1–10 s with volume accumulation, plus a sensitivity test over T (for example 1, 5, 15, 60 s) reporting peak flood depth, nodal surcharge and exchanged volume.

  Sim & Kim's finding of peak underestimation with larger T supports reporting peak metrics specifically.
- With under-relaxation, the effective response time of the exchange is about T/α for a relaxation weight α on the new value. The relaxation factor and the interval interact, so the paper should report both.

### Gaps
- No peer-reviewed quantitative guideline was found that relates exchange interval to manhole storage, cell size or CFL number (for example, a stability bound).
- The tested interval values and error magnitudes in Sim & Kim (2024) and in the 5–300 s GPU study were not retrieved.
- No SWMM-specific guidance was found on the SWMM routing step to use with SLOT in coupled 1D–2D flood runs. Pachaly's work concerns transients, not flood coupling.
