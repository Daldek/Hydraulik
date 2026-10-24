"""Declarations of the command catalog (AGI §2).

Every operation of Hydraulik is declared once as a :class:`CommandSpec`. The CLI,
the Python functions behind it, ``AGENTS.md``, ``llms.txt`` and the reference
documentation are generated from these declarations or tested against them
(AGI-1.1). :func:`catalog_document` serialises them as ``hydraulik-commands/1``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Literal

from hydraulik import __version__

__all__ = [
    "COMMANDS_SCHEMA",
    "NO_DEFAULT",
    "TOOL",
    "CommandSpec",
    "Effects",
    "Example",
    "OptionSpec",
    "catalog_document",
]

TOOL: Final = "hydraulik"
COMMANDS_SCHEMA: Final = "hydraulik-commands/1"


class _NoDefault:
    """Marker type of :data:`NO_DEFAULT`."""

    def __repr__(self) -> str:
        return "NO_DEFAULT"


NO_DEFAULT: Final = _NoDefault()
"""An option with no default: the key ``default`` is absent from its declaration."""

OptionType = Literal["string", "integer", "number", "boolean", "array", "object"]


@dataclass(frozen=True)
class OptionSpec:
    """Declaration of one option (AGI-2.3).

    Attributes
    ----------
    name : str
        snake_case name; the CLI flag is ``--`` plus the name with dashes.
    type : {"string", "integer", "number", "boolean", "array", "object"}
        JSON type of the value.
    description : str
        What the option means, in one or two sentences.
    required : bool
        Whether a call must give it.
    default : object
        Default value; :data:`NO_DEFAULT` when there is none.
    unit : str or None
        Unit of a physical quantity, in square brackets in prose (DEV-9.2).
    enum : tuple of (value, meaning)
        Allowed values, each with a one-line meaning.
    min, max : float or None
        Bounds of a number.
    pattern : str or None
        Regular expression a string must match completely.
    examples : tuple
        Example values.
    one_of : str or None
        Name of a mutual exclusion group: at most one member may be given.
    path_role : {"input", "output", "root"} or None
        Set when the value is a path (DEV-19.1 targets have ``output``).
    short : str or None
        Short CLI flag, for example ``-o``.
    items : str or None
        Type of the elements of an array option.
    """

    name: str
    type: OptionType
    description: str
    required: bool = False
    default: Any = NO_DEFAULT
    unit: str | None = None
    enum: tuple[tuple[Any, str], ...] = ()
    min: float | None = None
    max: float | None = None
    pattern: str | None = None
    examples: tuple[Any, ...] = ()
    one_of: str | None = None
    path_role: Literal["input", "output", "root"] | None = None
    short: str | None = None
    items: Literal["string", "integer", "number"] | None = None

    @property
    def flag(self) -> str:
        """str: the CLI flag, for example ``--output-dir``."""
        return "--" + self.name.replace("_", "-")

    def to_dict(self) -> dict[str, Any]:
        """Return the declaration as an ``option`` of ``hydraulik-commands/1``."""
        document: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.unit:
            document["unit"] = self.unit
        document["required"] = self.required
        if self.default is not NO_DEFAULT:
            document["default"] = self.default
        if self.enum:
            document["enum"] = [
                {"value": value, "meaning": meaning} for value, meaning in self.enum
            ]
        if self.min is not None:
            document["min"] = self.min
        if self.max is not None:
            document["max"] = self.max
        if self.pattern:
            document["pattern"] = self.pattern
        if self.examples:
            document["examples"] = list(self.examples)
        document["description"] = self.description
        if self.one_of:
            document["one_of"] = self.one_of
        if self.path_role:
            document["path_role"] = self.path_role
        document["flag"] = self.flag
        if self.short:
            document["short"] = self.short
        if self.items:
            document["items"] = self.items
        return document


@dataclass(frozen=True)
class Effects:
    """What a command does to the world (AGI-2.2).

    Attributes
    ----------
    read_only : bool
        True when the command changes nothing.
    writes : {"none", "add", "replace", "delete"}
        Kind of write; ``replace`` for commands that can replace files with
        ``--force``.
    idempotent : bool
        True when running it twice gives the same state.
    network : bool
        True when it talks to a remote service.
    destructive : bool
        True when it can destroy data.
    """

    read_only: bool = True
    writes: Literal["none", "add", "replace", "delete"] = "none"
    idempotent: bool = True
    network: bool = False
    destructive: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the ``effects`` object of the catalog."""
        return {
            "read_only": self.read_only,
            "writes": self.writes,
            "idempotent": self.idempotent,
            "network": self.network,
            "destructive": self.destructive,
        }


@dataclass(frozen=True)
class Example:
    """A complete CLI call and an excerpt of its result (AGI-2.2).

    Attributes
    ----------
    call : str
        The call as typed in a shell.
    result : object
        Excerpt of the ``result`` of the envelope (JSON-compatible).
    """

    call: str
    result: Any


@dataclass(frozen=True)
class CommandSpec:
    """Declaration of one command (AGI-2.2).

    Attributes
    ----------
    name : str
        ``<group> <verb>`` as typed in the CLI.
    operation_id : str
        ``hydraulik_<group>_<verb>``, at most 48 characters.
    function : str
        Public Python function that implements it (``hydraulik.<name>``).
    summary : str
        One sentence starting with a verb, at most 100 characters.
    description : str
        What it does, when to use it, when not to (and what instead), the main limit.
    options : tuple of OptionSpec
        The options.
    result_schema : str
        Schema id of the ``result`` document.
    cardinality : {"single", "bounded", "unbounded"}
        How many documents ``result`` holds.
    effects : Effects
        What the command changes.
    check : str or None
        Name of the command that plans this one without effects: itself for a
        writing command with ``--check``, ``None`` for a read-only one.
    rules : tuple of str
        Short imperative rules for agents.
    examples : tuple of Example
        At least one.
    errors : tuple of str
        Registry codes the command can raise.
    i18n_pl : dict
        Polish ``summary``, ``description`` and ``rules`` (AGI-9.1).
    """

    name: str
    operation_id: str
    function: str
    summary: str
    description: str
    options: tuple[OptionSpec, ...]
    result_schema: str
    effects: Effects
    check: str | None
    rules: tuple[str, ...]
    examples: tuple[Example, ...]
    errors: tuple[str, ...]
    i18n_pl: dict[str, Any] = field(default_factory=dict)
    cardinality: Literal["single", "bounded", "unbounded"] = "single"

    @property
    def group(self) -> str:
        """str: the first word of the name."""
        return self.name.split(" ", 1)[0]

    @property
    def verb(self) -> str:
        """str: the second word of the name."""
        return self.name.split(" ", 1)[1]

    @property
    def python_name(self) -> str:
        """str: name of the function inside the ``hydraulik`` package."""
        return self.function.rsplit(".", 1)[-1]

    def option(self, name: str) -> OptionSpec | None:
        """Return the option called ``name``, or ``None``."""
        return next((o for o in self.options if o.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        """Return the declaration as a ``command`` of ``hydraulik-commands/1``."""
        return {
            "name": self.name,
            "operation_id": self.operation_id,
            "function": self.function,
            "summary": self.summary,
            "description": self.description,
            "options": [option.to_dict() for option in self.options],
            "result": {"schema": self.result_schema, "cardinality": self.cardinality},
            "effects": self.effects.to_dict(),
            "check": self.check,
            "rules": list(self.rules),
            "examples": [
                {"call": example.call, "result": example.result}
                for example in self.examples
            ],
            "errors": list(self.errors),
            "i18n": {"pl": self.i18n_pl},
        }


def catalog_document(commands: tuple[CommandSpec, ...]) -> dict[str, Any]:
    """Return ``commands`` as a ``hydraulik-commands/1`` document.

    Parameters
    ----------
    commands : tuple of CommandSpec
        The commands to describe.

    Returns
    -------
    dict
        ``{"schema", "tool", "version", "commands"}``.
    """
    return {
        "schema": COMMANDS_SCHEMA,
        "tool": TOOL,
        "version": __version__,
        "commands": [command.to_dict() for command in commands],
    }
