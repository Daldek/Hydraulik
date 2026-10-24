"""The five functions that drive any command generically (AGI-2.1)."""

from __future__ import annotations

import importlib
from typing import Any

from hydraulik.catalog.commands import COMMANDS
from hydraulik.catalog.spec import TOOL, CommandSpec, catalog_document
from hydraulik.catalog.validate import validate_options
from hydraulik.documents import CommandsDocument, Document
from hydraulik.exceptions import InvalidInputError

__all__ = [
    "check_command",
    "command_schema",
    "find_command",
    "list_commands",
    "run_command",
    "validate_command",
]


def find_command(command: str) -> CommandSpec:
    """Return the declaration of ``command``.

    Parameters
    ----------
    command : str
        Catalog name, ``<group> <verb>``.

    Returns
    -------
    CommandSpec
        The declaration.

    Raises
    ------
    InvalidInputError
        If no command has that name; the error lists the known ones.
    """
    for spec in COMMANDS:
        if spec.name == command:
            return spec
    raise InvalidInputError(
        f"Unknown command {command!r}",
        details={
            "option": "command",
            "value": command,
            "allowed": [spec.name for spec in COMMANDS],
        },
        hint="Run `hydraulik commands list` to see the commands.",
        reason="unknown_command",
    )


def _document(commands: tuple[CommandSpec, ...]) -> CommandsDocument:
    body = catalog_document(commands)
    return CommandsDocument(
        tool=body["tool"], version=body["version"], commands=body["commands"]
    )


def list_commands() -> CommandsDocument:
    """Return the command catalog ``hydraulik-commands/1`` (AGI-2.1, AGI-2.4).

    Returns
    -------
    CommandsDocument
        Every command with its options, result, effects, errors and examples.

    Examples
    --------
    >>> document = list_commands()
    >>> document.to_dict()["tool"], document.to_dict()["schema"]
    ('hydraulik', 'hydraulik-commands/1')
    """
    return _document(COMMANDS)


def command_schema(command: str) -> CommandsDocument:
    """Return the catalog entry of one command (AGI-2.1).

    Parameters
    ----------
    command : str
        Catalog name, ``<group> <verb>``.

    Returns
    -------
    CommandsDocument
        A catalog with the single command.

    Raises
    ------
    InvalidInputError
        If the command is unknown.

    Examples
    --------
    >>> command_schema("config show").to_dict()["commands"][0]["name"]
    'config show'
    """
    return _document((find_command(command),))


def validate_command(command: str, /, **options: Any) -> dict[str, Any]:
    """Check options against the schema of a command, without effects (AGI-2.1).

    Parameters
    ----------
    command : str
        Catalog name, ``<group> <verb>`` (positional only, so that an option may
        itself be called ``command``).
    **options
        Option values by name (``output_dir``, ``force``, ...).

    Returns
    -------
    dict
        The options with the defaults filled in.

    Raises
    ------
    InvalidInputError
        If the command is unknown or an option is missing, unknown, mistyped or out
        of range.

    Examples
    --------
    >>> validate_command("commands guide")["format"]
    'agents'
    """
    return validate_options(find_command(command), options)


def _call(spec: CommandSpec, values: dict[str, Any]) -> Document:
    function = getattr(importlib.import_module(TOOL), spec.python_name)
    result: Document = function(**values)
    return result


def check_command(command: str, /, **options: Any) -> Document:
    """Return the plan of ``--check`` for a writing command (AGI-2.1).

    Parameters
    ----------
    command : str
        Catalog name of a command that has a ``check`` option.
    **options
        Option values; ``check`` is set to true.

    Returns
    -------
    Document
        The plan (``hydraulik-plan/1`` for the commands that write plain files).

    Raises
    ------
    InvalidInputError
        If the command is read-only (it has no plan: run it) or the options are
        invalid.

    Examples
    --------
    >>> check_command("config show")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.InvalidInputError: 'config show' is read-only and has no plan
    """
    spec = find_command(command)
    if spec.check is None:
        raise InvalidInputError(
            f"'{spec.name}' is read-only and has no plan",
            details={"option": "command", "value": command},
            hint="Run the command itself; it changes nothing.",
            reason="no_check_mode",
        )
    values = validate_options(spec, {**options, "check": True})
    return _call(spec, values)


def run_command(command: str, /, **options: Any) -> Document:
    """Validate the options and run a command (AGI-2.1).

    Parameters
    ----------
    command : str
        Catalog name, ``<group> <verb>``.
    **options
        Option values by name.

    Returns
    -------
    Document
        The domain document of the command.

    Raises
    ------
    InvalidInputError
        If the command is unknown or the options are invalid.
    HydraulikError
        Whatever the command raises, with a registry code.

    Examples
    --------
    >>> run_command("config show").to_dict()["schema"]
    'hydraulik-config/1'
    """
    spec = find_command(command)
    return _call(spec, validate_options(spec, options))
