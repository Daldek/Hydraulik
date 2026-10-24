"""The commands of Hydraulik, declared once (AGI-1.1).

Each entry is a :class:`~hydraulik.catalog.spec.CommandSpec`. The CLI, the public
functions, ``AGENTS.md`` and ``llms.txt`` follow this list; a contract test checks
that they do.
"""

from __future__ import annotations

from hydraulik.catalog.spec import CommandSpec, Effects, Example, OptionSpec

__all__ = ["COMMANDS", "COMMAND_PATTERN"]

COMMAND_PATTERN = r"[a-z][a-z0-9-]* [a-z][a-z0-9-]*"
"""Pattern of a command name: ``<group> <verb>`` (AGI-2.2)."""

_COMMANDS_LIST = CommandSpec(
    name="commands list",
    operation_id="hydraulik_commands_list",
    function="hydraulik.list_commands",
    summary="List every command of Hydraulik with its options, effects and errors.",
    description=(
        "Returns the command catalog hydraulik-commands/1: for each command the "
        "options with types, bounds and defaults, the result schema, the effects, "
        "the errors and examples. Use it first, without network or credentials, to "
        "learn what Hydraulik can do. Do not use it to run a command: use the "
        "command itself. The output is complete; ask for one command with "
        "`commands schema`."
    ),
    options=(),
    result_schema="hydraulik-commands/1",
    effects=Effects(),
    check=None,
    rules=("Read the catalog before the first call; it needs no engine.",),
    examples=(
        Example(
            call="hydraulik commands list --json",
            result={"schema": "hydraulik-commands/1", "tool": "hydraulik"},
        ),
    ),
    errors=("internal_error",),
    i18n_pl={
        "summary": (
            "Wypisuje wszystkie polecenia Hydraulika z opcjami, skutkami i błędami."
        ),
        "description": (
            "Zwraca katalog poleceń hydraulik-commands/1: dla każdego polecenia opcje "
            "z typami, zakresami i wartościami domyślnymi, schemat wyniku, skutki, "
            "błędy i przykłady. Użyj go najpierw, bez sieci i bez danych "
            "uwierzytelniających, aby poznać możliwości Hydraulika. Nie służy do "
            "uruchamiania poleceń: użyj samego polecenia. Wynik jest pełny; jedno "
            "polecenie opisuje `commands schema`."
        ),
        "rules": ["Przeczytaj katalog przed pierwszym wywołaniem; nie wymaga silnika."],
    },
)

_COMMANDS_SCHEMA = CommandSpec(
    name="commands schema",
    operation_id="hydraulik_commands_schema",
    function="hydraulik.command_schema",
    summary="Describe one command of Hydraulik: options, result, effects and errors.",
    description=(
        "Returns the catalog entry of one command as hydraulik-commands/1 with a "
        "single command. Use it to fill the options of a call correctly: types, "
        "units, bounds, allowed values, exclusion groups, paths and examples. Do "
        "not use it to list all commands (use `commands list`). An unknown name is "
        "a validation_error that lists the known commands."
    ),
    options=(
        OptionSpec(
            name="command",
            type="string",
            required=True,
            pattern=COMMAND_PATTERN,
            examples=("model build",),
            description="Name of the command, `<group> <verb>`, as in `commands list`.",
        ),
    ),
    result_schema="hydraulik-commands/1",
    effects=Effects(),
    check=None,
    rules=("Quote the name with a space: --command 'model build'.",),
    examples=(
        Example(
            call="hydraulik commands schema --command 'config show' --json",
            result={"schema": "hydraulik-commands/1", "tool": "hydraulik"},
        ),
    ),
    errors=("validation_error", "internal_error"),
    i18n_pl={
        "summary": "Opisuje jedno polecenie Hydraulika: opcje, wynik, skutki i błędy.",
        "description": (
            "Zwraca wpis katalogu jednego polecenia jako hydraulik-commands/1 z jednym "
            "poleceniem. Użyj go, aby poprawnie wypełnić opcje wywołania: typy, "
            "jednostki, zakresy, dozwolone wartości, grupy wykluczania, ścieżki i "
            "przykłady. Nie służy do wypisania wszystkich poleceń (`commands list`). "
            "Nieznana nazwa to validation_error z listą znanych poleceń."
        ),
        "rules": ["Nazwę podaj w cudzysłowie ze spacją: --command 'model build'."],
    },
)

_COMMANDS_GUIDE = CommandSpec(
    name="commands guide",
    operation_id="hydraulik_commands_guide",
    function="hydraulik.render_guide",
    summary=(
        "Render AGENTS.md, llms.txt or the block for another repository's AGENTS.md."
    ),
    description=(
        "Renders the agent guides from the command catalog: `agents` is AGENTS.md, "
        "`llms` is llms.txt, `agents-md-block` is the compact block that another "
        "repository keeps in its AGENTS.md between <!-- BEGIN hydraulik --> and "
        "<!-- END hydraulik -->. With --inject PATH the block replaces the one in "
        "that file, or is appended, and the file is rewritten. Use it to refresh the "
        "committed guides after the catalog changed. Do not edit AGENTS.md or "
        "llms.txt by hand."
    ),
    options=(
        OptionSpec(
            name="format",
            type="string",
            default="agents",
            enum=(
                ("agents", "AGENTS.md for this repository"),
                ("llms", "llms.txt with links to the raw documents"),
                ("agents-md-block", "compact block for the AGENTS.md of a consumer"),
            ),
            description="Which guide to render.",
        ),
        OptionSpec(
            name="inject",
            type="string",
            path_role="output",
            description=(
                "AGENTS.md of a consumer repository whose hydraulik block is replaced "
                "(format agents-md-block only)."
            ),
        ),
        OptionSpec(
            name="check",
            type="boolean",
            default=False,
            description="Plan the injection without changing the file.",
        ),
    ),
    result_schema="hydraulik-guide/1",
    effects=Effects(read_only=False, writes="replace", idempotent=True),
    check="commands guide",
    rules=("--inject changes the named file in place; keep it under version control.",),
    examples=(
        Example(
            call="hydraulik commands guide --format agents-md-block --json",
            result={"schema": "hydraulik-guide/1", "format": "agents-md-block"},
        ),
    ),
    errors=("validation_error", "not_found", "io_error", "internal_error"),
    i18n_pl={
        "summary": (
            "Generuje AGENTS.md, llms.txt lub blok do AGENTS.md innego repozytorium."
        ),
        "description": (
            "Generuje przewodniki dla agentów z katalogu poleceń: `agents` to "
            "AGENTS.md, `llms` to llms.txt, `agents-md-block` to zwarty blok, który "
            "inne repozytorium trzyma w swoim AGENTS.md między <!-- BEGIN hydraulik "
            "--> a <!-- END hydraulik -->. Z --inject PATH blok zastępuje blok w tym "
            "pliku albo jest dopisywany, a plik jest zapisywany. Użyj po zmianie "
            "katalogu, aby odświeżyć zatwierdzone przewodniki. Nie edytuj AGENTS.md "
            "ani llms.txt ręcznie."
        ),
        "rules": [
            "--inject zmienia wskazany plik w miejscu; trzymaj go pod kontrolą wersji."
        ],
    },
)

_CONFIG_SHOW = CommandSpec(
    name="config show",
    operation_id="hydraulik_config_show",
    function="hydraulik.show_config",
    summary=(
        "Show every setting of Hydraulik with its value and where the value came from."
    ),
    description=(
        "Lists each setting (language, log level, engine locations, timeouts) with "
        "its value, its source (option, environment variable, nogat.toml or default) "
        "and the environment variables that set it, plus the settings file that was "
        "looked for. Hydraulik has no credentials and no store, so both are empty. "
        "Use it to see why an engine is not found. Do not use it to check that an "
        "engine works: use `engines check`."
    ),
    options=(),
    result_schema="hydraulik-config/1",
    effects=Effects(),
    check=None,
    rules=("Set a value in nogat.toml or in HYDRAULIK_<KEY>; never in a command.",),
    examples=(
        Example(
            call="hydraulik config show --json",
            result={"schema": "hydraulik-config/1", "credentials": [], "store": None},
        ),
    ),
    errors=("validation_error", "not_found", "data_error", "internal_error"),
    i18n_pl={
        "summary": (
            "Pokazuje wszystkie ustawienia Hydraulika z wartością i jej źródłem."
        ),
        "description": (
            "Wypisuje każde ustawienie (język, poziom logów, lokalizacje silników, "
            "limity czasu) z wartością, źródłem (opcja, zmienna środowiskowa, "
            "nogat.toml lub wartość domyślna) i zmiennymi, które je ustawiają, oraz "
            "szukany plik ustawień. Hydraulik nie ma danych uwierzytelniających ani "
            "magazynu, więc obie listy są puste. Użyj, aby zobaczyć, czemu silnik nie "
            "jest znaleziony. Nie służy do sprawdzenia, że silnik działa: użyj "
            "`engines check`."
        ),
        "rules": [
            "Wartość ustaw w nogat.toml lub w HYDRAULIK_<KLUCZ>, nie w poleceniu."
        ],
    },
)

_FEATURE_COMMANDS = (
    ("terrain download", "Kartograf is found"),
    ("rainfall build", "Hydrolog is installed"),
    ("model build", "the rasters and vectors stack is installed"),
    ("model run", "SFINCS and NetCDF reading are available"),
    ("results read", "NetCDF reading is available"),
    ("results export", "NetCDF and raster writing are available"),
    ("swmm run", "SWMM (pyswmm) is installed"),
    ("model couple", "the SFINCS library, pyswmm and NetCDF reading are available"),
)

_ENGINES_CHECK = CommandSpec(
    name="engines check",
    operation_id="hydraulik_engines_check",
    function="hydraulik.check_engines",
    summary="Report the engines and packages Hydraulik can use on this machine.",
    description=(
        "Looks for SFINCS (the setting, then `sfincs` on PATH, then a Docker image "
        "that is already present), the SFINCS library of the coupling, SWMM "
        "(pyswmm) and Kartograf, and lists the Python packages of the extras. For "
        "each command that needs more than the core package it says whether it can "
        "run here and what is missing. Nothing is installed, pulled or written; "
        "SFINCS is started only in an empty directory to read its banner. With "
        "--require the call fails with missing_dependency (6) when a command cannot "
        "run, which suits a script. Use `config show` to see why an engine is not "
        "found."
    ),
    options=(
        OptionSpec(
            name="require",
            type="array",
            items="string",
            enum=_FEATURE_COMMANDS,
            examples=(["model run"],),
            description=(
                "Commands that must be able to run here; the call fails with "
                "missing_dependency when one cannot."
            ),
        ),
    ),
    result_schema="hydraulik-engines/1",
    effects=Effects(),
    check=None,
    rules=(
        "Run it on a new machine before a long command; do not install an engine "
        "from a script, install it and set its location in the settings.",
    ),
    examples=(
        Example(
            call="hydraulik engines check --json",
            result={"schema": "hydraulik-engines/1"},
        ),
        Example(
            call="hydraulik engines check --require 'model run' --json",
            result={"schema": "hydraulik-engines/1"},
        ),
    ),
    errors=(
        "validation_error",
        "not_found",
        "data_error",
        "missing_dependency",
        "internal_error",
    ),
    i18n_pl={
        "summary": "Podaje silniki i pakiety, z których Hydraulik może tu korzystać.",
        "description": (
            "Szuka SFINCS (ustawienie, potem `sfincs` w PATH, potem obraz Dockera, "
            "który już jest), biblioteki SFINCS do sprzężenia, SWMM (pyswmm) i "
            "Kartografa oraz wypisuje pakiety Pythona z dodatków. Dla każdego "
            "polecenia, które wymaga czegoś więcej niż pakietu podstawowego, mówi, czy "
            "można je tu uruchomić i czego brakuje. Niczego nie instaluje, nie pobiera "
            "ani nie zapisuje; SFINCS jest uruchamiany tylko w pustym katalogu, aby "
            "odczytać jego nagłówek. Z --require wywołanie kończy się błędem "
            "missing_dependency (6), gdy polecenie nie może działać, co ułatwia "
            "skrypty. Aby zobaczyć, czemu silnik nie jest znaleziony, użyj `config "
            "show`."
        ),
        "rules": [
            "Uruchom na nowym komputerze przed długim poleceniem; nie instaluj "
            "silnika ze skryptu, zainstaluj go i wskaż jego położenie w ustawieniach."
        ],
    },
)

_MODEL_RUN = CommandSpec(
    name="model run",
    operation_id="hydraulik_model_run",
    function="hydraulik.run_model",
    summary="Run SFINCS on a model directory and read its maxima and water balance.",
    description=(
        "Copies the model directory (`model build`) to a staging directory, runs "
        "the external SFINCS there (the executable of the settings, `sfincs` on "
        "PATH, or a Docker image that is already present), reads the map, and only "
        "when the run succeeded writes sfincs_map.nc, sfincs_his.nc (when the "
        "model has observation points) and sfincs.log into --output-dir. The "
        "result has the maxima, the flooded areas and the water balance (rain - "
        "infiltration - stored = residual): a closed model must close it, with "
        "outflow cells the residual is the water that left. Use it for one model; "
        "it does not build a model (`model build`) and does not couple a sewer "
        "network (`model couple`). The run is stopped after sfincs.timeout_s."
    ),
    options=(
        OptionSpec(
            name="model",
            type="string",
            required=True,
            path_role="input",
            examples=("./model",),
            description="Model directory with sfincs.inp, written by `model build`.",
        ),
        OptionSpec(
            name="output_dir",
            type="string",
            required=True,
            path_role="output",
            short="-o",
            examples=("./run",),
            description=(
                "Directory for the results (plain files, created when missing); it "
                "may be the model directory."
            ),
        ),
        OptionSpec(
            name="force",
            type="boolean",
            default=False,
            description="Replace result files that already exist.",
        ),
        OptionSpec(
            name="check",
            type="boolean",
            default=False,
            description=(
                "Plan without effects: the files, the engine that would run and "
                "whatever would stop the run."
            ),
        ),
    ),
    result_schema="hydraulik-run/1",
    effects=Effects(read_only=False, writes="replace", idempotent=True),
    check="model run",
    rules=(
        "Read the notices: a flagged balance means the result is not to be trusted.",
        "The output may be the model directory itself; the inputs are copied.",
    ),
    examples=(
        Example(
            call="hydraulik model run --model ./model --output-dir ./run --json",
            result={"schema": "hydraulik-run/1"},
        ),
        Example(
            call=(
                "hydraulik model run --model ./model --output-dir ./run --check --json"
            ),
            result={"schema": "hydraulik-plan/1"},
        ),
    ),
    errors=(
        "validation_error",
        "not_found",
        "conflict",
        "unsupported",
        "data_error",
        "io_error",
        "missing_dependency",
        "calculation_error",
        "terminated",
        "cancelled",
        "internal_error",
    ),
    i18n_pl={
        "summary": (
            "Uruchamia SFINCS na katalogu modelu i odczytuje maksima oraz bilans wody."
        ),
        "description": (
            "Kopiuje katalog modelu (`model build`) do katalogu tymczasowego, "
            "uruchamia w nim zewnętrzny SFINCS (plik wykonywalny z ustawień, "
            "`sfincs` w PATH albo obraz Dockera, który już jest), odczytuje mapę i "
            "dopiero po udanym przebiegu zapisuje sfincs_map.nc, sfincs_his.nc (gdy "
            "model ma punkty obserwacyjne) i sfincs.log w --output-dir. Wynik ma "
            "maksima, powierzchnie zalane i bilans wody (opad - infiltracja - "
            "zmagazynowana = reszta): model zamknięty musi go zamykać, przy "
            "komórkach odpływu reszta to woda, która odpłynęła. Użyj dla jednego "
            "modelu; nie buduje modelu (`model build`) i nie sprzęga sieci "
            "kanalizacyjnej (`model couple`). Przebieg jest zatrzymywany po "
            "sfincs.timeout_s."
        ),
        "rules": [
            "Przeczytaj uwagi: oflagowany bilans to wynik, któremu nie wolno ufać.",
            "Wyjściem może być sam katalog modelu; wejścia są kopiowane.",
        ],
    },
)

_RESULTS_READ = CommandSpec(
    name="results read",
    operation_id="hydraulik_results_read",
    function="hydraulik.read_results",
    summary="Read the maxima, flooded areas and water balance of a SFINCS run.",
    description=(
        "Reads sfincs_map.nc (and sfincs_his.nc) of a run: the grid, the largest "
        "depth and velocity, the area flooded deeper than each threshold, the "
        "maximum at each station and the water balance with its flags. Use it on "
        "a run that `model run` wrote, or on any regular-grid SFINCS output. It "
        "changes nothing. Depths under the wet/dry threshold (huthresh) are not in "
        "the map, so a threshold below it is refused."
    ),
    options=(
        OptionSpec(
            name="run",
            type="string",
            required=True,
            path_role="input",
            examples=("./run",),
            description="Directory of a run, or its sfincs_map.nc.",
        ),
        OptionSpec(
            name="thresholds_m",
            type="array",
            items="number",
            unit="m",
            examples=([0.1, 0.3],),
            description=(
                "Depths for which the flooded area is reported (default 0.1 and 0.3)."
            ),
        ),
        OptionSpec(
            name="expected_rain_mm",
            type="number",
            unit="mm",
            min=0.0,
            description=(
                "Depth of the precipitation file, to check the rain SFINCS applied."
            ),
        ),
    ),
    result_schema="hydraulik-results/1",
    effects=Effects(),
    check=None,
    rules=("A flag of the balance is a warning, not an error: read the notices.",),
    examples=(
        Example(
            call="hydraulik results read --run ./run --json",
            result={"schema": "hydraulik-results/1"},
        ),
    ),
    errors=(
        "validation_error",
        "not_found",
        "data_error",
        "unsupported",
        "missing_dependency",
        "internal_error",
    ),
    i18n_pl={
        "summary": "Czyta maksima, powierzchnie zalane i bilans wody przebiegu SFINCS.",
        "description": (
            "Czyta sfincs_map.nc (i sfincs_his.nc) przebiegu: siatkę, największą "
            "głębokość i prędkość, powierzchnię zalaną głębiej niż każdy próg, "
            "maksimum na każdej stacji i bilans wody z jego flagami. Użyj dla "
            "przebiegu zapisanego przez `model run` albo dowolnego wyniku SFINCS na "
            "siatce regularnej. Niczego nie zmienia. Głębokości poniżej progu "
            "suchy/mokry (huthresh) nie ma w mapie, więc niższy próg jest odrzucany."
        ),
        "rules": ["Flaga bilansu to ostrzeżenie, nie błąd: przeczytaj uwagi."],
    },
)

_RESULTS_EXPORT = CommandSpec(
    name="results export",
    operation_id="hydraulik_results_export",
    function="hydraulik.export_results",
    summary="Write a map of a run as a GeoTIFF, or the station series as a CSV table.",
    description=(
        "Writes to --output one map of a run as a GeoTIFF in the CRS of the model "
        "(max_depth, max_velocity, final_depth, infiltration) or the series of the "
        "stations as a CSV table (stations). Use it to open the result in QGIS or "
        "to hand a flood map on. It computes nothing new; for the numbers use "
        "`results read`. With --check it plans and writes nothing."
    ),
    options=(
        OptionSpec(
            name="run",
            type="string",
            required=True,
            path_role="input",
            examples=("./run",),
            description="Directory of a run, or its sfincs_map.nc.",
        ),
        OptionSpec(
            name="variable",
            type="string",
            required=True,
            enum=(
                ("max_depth", "maximum water depth [m] (GeoTIFF)"),
                ("max_velocity", "maximum flow velocity [m/s] (GeoTIFF)"),
                ("final_depth", "water depth at the last output time [m] (GeoTIFF)"),
                ("infiltration", "infiltration accumulated to the end [m] (GeoTIFF)"),
                ("stations", "level and depth at the stations in time (CSV)"),
            ),
            description="What to export.",
        ),
        OptionSpec(
            name="output",
            type="string",
            required=True,
            path_role="output",
            examples=("./hmax.tif",),
            description="The file to write (exactly one file).",
        ),
        OptionSpec(
            name="force",
            type="boolean",
            default=False,
            description="Replace the file when it exists.",
        ),
        OptionSpec(
            name="check",
            type="boolean",
            default=False,
            description="Plan without effects.",
        ),
    ),
    result_schema="hydraulik-export/1",
    effects=Effects(read_only=False, writes="replace", idempotent=True),
    check="results export",
    rules=("max_depth has no data where the water stayed under huthresh.",),
    examples=(
        Example(
            call=(
                "hydraulik results export --run ./run --variable max_depth "
                "--output ./hmax.tif --json"
            ),
            result={"schema": "hydraulik-export/1", "format": "geotiff"},
        ),
    ),
    errors=(
        "validation_error",
        "not_found",
        "conflict",
        "data_error",
        "unsupported",
        "io_error",
        "missing_dependency",
        "internal_error",
    ),
    i18n_pl={
        "summary": (
            "Zapisuje mapę przebiegu jako GeoTIFF albo przebiegi na stacjach jako CSV."
        ),
        "description": (
            "Zapisuje do --output jedną mapę przebiegu jako GeoTIFF w układzie "
            "modelu (max_depth, max_velocity, final_depth, infiltration) albo "
            "przebiegi na stacjach jako tabelę CSV (stations). Użyj, aby otworzyć "
            "wynik w QGIS lub przekazać mapę zalewu dalej. Niczego nie przelicza; "
            "liczby daje `results read`. Z --check tylko planuje i nic nie zapisuje."
        ),
        "rules": ["max_depth nie ma danych tam, gdzie woda nie przekroczyła huthresh."],
    },
)

_SWMM_RUN = CommandSpec(
    name="swmm run",
    operation_id="hydraulik_swmm_run",
    function="hydraulik.run_network",
    summary="Run a SWMM sewer network with an inflow hydrograph and read its peaks.",
    description=(
        "Runs EPA SWMM through pyswmm on a network table (--network, one row per "
        "node) or on your own SWMM input in SI units (--inp, FLOW_UNITS CMS), with "
        "an optional inflow hydrograph at one node (--inflow, --inflow-node; the "
        "table of `time_min,discharge_m3s` that Hydrolog gives). Only when SWMM "
        "finished it writes network.inp and network.rpt into --output-dir. The "
        "result has the water balance of SWMM (inflow, outflow, flooding, storage, "
        "its own continuity error) and the peaks of every node and conduit. Use it "
        "for a sewer network on its own; it does not couple the network with the "
        "surface (`model couple`) and does not read GIS sewer layers. pyswmm runs "
        "one simulation per process."
    ),
    options=(
        OptionSpec(
            name="network",
            type="string",
            path_role="input",
            one_of="source",
            examples=("./network.csv",),
            description=(
                "Network table (CSV): name, x_m, y_m, rim_m, depth_m, to, diameter_m "
                "per node, upstream first, one row with an empty `to` for the "
                "outfall. Exactly one of --network and --inp."
            ),
        ),
        OptionSpec(
            name="inp",
            type="string",
            path_role="input",
            one_of="source",
            examples=("./sewer.inp",),
            description=(
                "Your own SWMM input file with FLOW_UNITS CMS; it runs where it is "
                "and is copied to network.inp. Exactly one of --network and --inp."
            ),
        ),
        OptionSpec(
            name="inflow",
            type="string",
            path_role="input",
            examples=("./inflow.csv",),
            description=(
                "Hydrograph table (CSV: time_min, discharge_m3s) applied as the "
                "lateral inflow of --inflow-node. Required with --network."
            ),
        ),
        OptionSpec(
            name="inflow_node",
            type="string",
            examples=("J1",),
            description="Node that receives the inflow. Required with --inflow.",
        ),
        OptionSpec(
            name="recession_min",
            type="number",
            unit="min",
            min=0.0,
            description=(
                "Network table only: minutes the run lasts after the last time of "
                "the hydrograph (default 10)."
            ),
        ),
        OptionSpec(
            name="routing_step_s",
            type="number",
            unit="s",
            min=0.01,
            description="Network table only: SWMM's fixed routing step (default 0.5).",
        ),
        OptionSpec(
            name="surcharge_method",
            type="string",
            enum=(
                ("EXTRAN", "exact in pressurised flow (default)"),
                (
                    "SLOT",
                    "Preissmann slot; loses 2 to 17 % of the water when pressurised",
                ),
            ),
            description="Network table only: how SWMM treats pressurised flow.",
        ),
        OptionSpec(
            name="output_dir",
            type="string",
            required=True,
            path_role="output",
            short="-o",
            examples=("./swmm",),
            description=(
                "Directory for network.inp and network.rpt (plain files, created "
                "when missing)."
            ),
        ),
        OptionSpec(
            name="force",
            type="boolean",
            default=False,
            description="Replace files that already exist.",
        ),
        OptionSpec(
            name="check",
            type="boolean",
            default=False,
            description="Plan without effects: the files, the steps, what is missing.",
        ),
    ),
    result_schema="hydraulik-swmm/1",
    effects=Effects(read_only=False, writes="replace", idempotent=True),
    check="swmm run",
    rules=(
        "Give exactly one of --network and --inp.",
        "A network table has no inflow of its own: give --inflow and --inflow-node.",
        "Read the notices: a continuity error above 5 % means do not trust the result.",
    ),
    examples=(
        Example(
            call=(
                "hydraulik swmm run --network ./network.csv --inflow ./inflow.csv "
                "--inflow-node J1 --output-dir ./swmm --json"
            ),
            result={"schema": "hydraulik-swmm/1"},
        ),
        Example(
            call=("hydraulik swmm run --inp ./sewer.inp -o ./swmm --check --json"),
            result={"schema": "hydraulik-plan/1"},
        ),
    ),
    errors=(
        "validation_error",
        "not_found",
        "conflict",
        "data_error",
        "unsupported",
        "io_error",
        "missing_dependency",
        "terminated",
        "cancelled",
        "internal_error",
    ),
    i18n_pl={
        "summary": (
            "Uruchamia sieć kanalizacyjną w SWMM z hydrogramem dopływu i czyta jej "
            "szczyty."
        ),
        "description": (
            "Uruchamia EPA SWMM przez pyswmm na tabeli sieci (--network, jeden "
            "wiersz na węzeł) albo na własnym pliku SWMM w jednostkach SI (--inp, "
            "FLOW_UNITS CMS), z opcjonalnym hydrogramem dopływu w jednym węźle "
            "(--inflow, --inflow-node; tabela `time_min,discharge_m3s`, jaką daje "
            "Hydrolog). Dopiero po zakończeniu SWMM zapisuje network.inp i "
            "network.rpt w --output-dir. Wynik ma bilans wody SWMM (dopływ, odpływ, "
            "wylewy, zmagazynowana woda, jego własny błąd ciągłości) oraz szczyty "
            "każdego węzła i przewodu. Użyj dla samej sieci kanalizacyjnej; nie "
            "sprzęga sieci z powierzchnią (`model couple`) i nie czyta warstw GIS "
            "kanalizacji. pyswmm uruchamia jedną symulację na proces."
        ),
        "rules": [
            "Podaj dokładnie jedno z --network i --inp.",
            "Tabela sieci nie ma własnego dopływu: podaj --inflow i --inflow-node.",
            "Przeczytaj uwagi: błąd ciągłości powyżej 5 % oznacza wynik niewiarygodny.",
        ],
    },
)

_RAINFALL_BUILD = CommandSpec(
    name="rainfall build",
    operation_id="hydraulik_rainfall_build",
    function="hydraulik.build_rainfall",
    summary=(
        "Write a design rain as a rain table from a Hydrolog shape and a PMAXTP depth."
    ),
    description=(
        "Writes the rain table (`time_min,depth_mm`) that `model build` reads. "
        "Design: a Hydrolog hyetograph shape (--hietogram-type, the options of "
        "`hydrolog precip hietogram`) with a depth that you give (--total-mm) or "
        "the PMAXTP depth of IMGW-PIB for --duration-min and --probability-percent, "
        "taken from the document of `imgw pmaxtp fetch --json` (--pmaxtp, offline) "
        "or fetched for a point through IMGWTools (--latitude and --longitude, "
        "needs the network). Document: --hietogram converts the result of "
        "`hydrolog precip hietogram --json` as it is. With --check nothing is "
        "fetched. Use it for the design storm of one model; it computes no runoff "
        "(that is Hydrolog) and has no depth for durations that PMAXTP lacks."
    ),
    options=(
        OptionSpec(
            name="hietogram_type",
            type="string",
            one_of="shape",
            enum=(
                ("block", "uniform intensity over the whole duration"),
                ("triangular", "linear rise to the peak at peak_position, then fall"),
                ("beta", "shape of a Beta density with alpha and beta"),
                ("euler_ii", "DVWK Euler type II, the peak at about a third"),
            ),
            description=(
                "Temporal distribution of the rain, as in `hydrolog precip "
                "hietogram`. Exactly one of --hietogram-type and --hietogram."
            ),
        ),
        OptionSpec(
            name="hietogram",
            type="string",
            path_role="input",
            one_of="shape",
            examples=("./hietogram.json",),
            description=(
                "Document of `hydrolog precip hietogram --json` (the envelope or its "
                "result); it carries its depth, duration and step, so no design "
                "option may be given with it."
            ),
        ),
        OptionSpec(
            name="total_mm",
            type="number",
            unit="mm",
            min=0.0,
            one_of="depth",
            examples=(40.0,),
            description="Depth of the rain. One source of the depth only.",
        ),
        OptionSpec(
            name="pmaxtp",
            type="string",
            path_role="input",
            one_of="depth",
            examples=("./pmaxtp.json",),
            description=(
                "Document of `imgw pmaxtp fetch --json`: the depth is its quantile "
                "for --duration-min and --probability-percent. One source of the "
                "depth only."
            ),
        ),
        OptionSpec(
            name="latitude",
            type="number",
            unit="deg",
            min=-90.0,
            max=90.0,
            one_of="depth",
            examples=(52.23,),
            description=(
                "Latitude of a point in Poland; the PMAXTP depth is fetched from "
                "IMGW-PIB (network). Needs --longitude. One source of the depth only."
            ),
        ),
        OptionSpec(
            name="longitude",
            type="number",
            unit="deg",
            min=-180.0,
            max=180.0,
            examples=(21.01,),
            description="Longitude of the point of --latitude.",
        ),
        OptionSpec(
            name="method",
            type="string",
            enum=(
                ("POT", "peak over threshold (default, recommended)"),
                ("AMP", "annual maximum precipitation"),
            ),
            description="PMAXTP method for a point (--latitude); POT when not given.",
        ),
        OptionSpec(
            name="probability_percent",
            type="integer",
            unit="percent",
            min=1,
            max=99,
            examples=(10,),
            description=(
                "Probability of exceedance of the PMAXTP depth: 1, 2, 5, 10, 20 or "
                "50. Required with --pmaxtp and --latitude."
            ),
        ),
        OptionSpec(
            name="duration_min",
            type="number",
            unit="min",
            min=0.0,
            examples=(60.0,),
            description=(
                "Length of the rain. Required for a design; for PMAXTP one of 15, "
                "30, 45, 60, 90, 120 or 180."
            ),
        ),
        OptionSpec(
            name="timestep_min",
            type="number",
            unit="min",
            min=0.0,
            description="Length of a step of the table (default 5).",
        ),
        OptionSpec(
            name="alpha",
            type="number",
            min=0.0,
            description="Beta only: shape of the rising limb (Hydrolog default 2).",
        ),
        OptionSpec(
            name="beta",
            type="number",
            min=0.0,
            description="Beta only: shape of the falling limb (Hydrolog default 5).",
        ),
        OptionSpec(
            name="peak_position",
            type="number",
            min=0.0,
            max=1.0,
            description=(
                "Triangular and euler_ii only: position of the peak in the duration, "
                "between 0 and 1 (defaults 0.5 and 0.33)."
            ),
        ),
        OptionSpec(
            name="output",
            type="string",
            required=True,
            path_role="output",
            examples=("./rain.csv",),
            description="The rain table to write (exactly one file).",
        ),
        OptionSpec(
            name="force",
            type="boolean",
            default=False,
            description="Replace the file when it exists.",
        ),
        OptionSpec(
            name="check",
            type="boolean",
            default=False,
            description="Plan without effects and without fetching anything.",
        ),
    ),
    result_schema="hydraulik-rain/1",
    effects=Effects(read_only=False, writes="replace", idempotent=True, network=True),
    check="rainfall build",
    rules=(
        "Take the depth from one source: --total-mm, --pmaxtp or --latitude with "
        "--longitude.",
        "PMAXTP gives 15, 30, 45, 60, 90, 120 and 180 min at 1, 2, 5, 10, 20 and 50 %.",
        "Name IMGW-PIB as the source of a PMAXTP depth (a notice says so).",
    ),
    examples=(
        Example(
            call=(
                "hydraulik rainfall build --hietogram-type euler_ii --total-mm 40 "
                "--duration-min 120 --output ./rain.csv --json"
            ),
            result={"schema": "hydraulik-rain/1", "source": "design"},
        ),
        Example(
            call=(
                "hydraulik rainfall build --hietogram-type beta --latitude 52.23 "
                "--longitude 21.01 --probability-percent 10 --duration-min 60 "
                "--output ./rain.csv --check --json"
            ),
            result={"schema": "hydraulik-plan/1"},
        ),
    ),
    errors=(
        "validation_error",
        "not_found",
        "conflict",
        "source_unavailable",
        "missing_dependency",
        "data_error",
        "io_error",
        "calculation_error",
        "no_data",
        "terminated",
        "cancelled",
        "internal_error",
    ),
    i18n_pl={
        "summary": (
            "Zapisuje opad projektowy jako tabelę opadu z kształtu Hydrologa i "
            "wysokości PMAXTP."
        ),
        "description": (
            "Zapisuje tabelę opadu (`time_min,depth_mm`), którą czyta `model build`. "
            "Projekt: kształt hietogramu Hydrologa (--hietogram-type, opcje `hydrolog "
            "precip hietogram`) z wysokością podaną (--total-mm) albo wysokością "
            "PMAXTP z IMGW-PIB dla --duration-min i --probability-percent, z "
            "dokumentu `imgw pmaxtp fetch --json` (--pmaxtp, bez sieci) albo "
            "pobraną dla punktu przez IMGWTools (--latitude i --longitude, wymaga "
            "sieci). Dokument: --hietogram przelicza wynik `hydrolog precip "
            "hietogram --json` bez zmian. Z --check niczego nie pobiera. Użyj dla "
            "deszczu projektowego jednego modelu; nie liczy odpływu (to robi "
            "Hydrolog) i nie ma wysokości dla czasów trwania, których PMAXTP nie ma."
        ),
        "rules": [
            "Wysokość weź z jednego źródła: --total-mm, --pmaxtp albo --latitude z "
            "--longitude.",
            "PMAXTP daje 15, 30, 45, 60, 90, 120 i 180 min przy 1, 2, 5, 10, 20 i "
            "50 %.",
            "Podaj IMGW-PIB jako źródło wysokości PMAXTP (mówi o tym uwaga).",
        ],
    },
)

COMMANDS: tuple[CommandSpec, ...] = (
    _COMMANDS_LIST,
    _COMMANDS_SCHEMA,
    _COMMANDS_GUIDE,
    _CONFIG_SHOW,
    _ENGINES_CHECK,
    _RAINFALL_BUILD,
    _MODEL_RUN,
    _RESULTS_READ,
    _RESULTS_EXPORT,
    _SWMM_RUN,
)
"""Every command of Hydraulik, in the order of ``commands list``."""
