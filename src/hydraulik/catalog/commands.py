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

COMMANDS: tuple[CommandSpec, ...] = (
    _COMMANDS_LIST,
    _COMMANDS_SCHEMA,
    _COMMANDS_GUIDE,
    _CONFIG_SHOW,
)
"""Every command of Hydraulik, in the order of ``commands list``."""
