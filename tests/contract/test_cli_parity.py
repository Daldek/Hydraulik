"""Library, CLI and catalog agree on option names (AGI-1.2, DEV-10.4)."""

import argparse
import inspect
from typing import Any, cast

import pytest

import hydraulik
from hydraulik.catalog.commands import COMMANDS
from hydraulik.catalog.spec import CommandSpec
from hydraulik.cli.parser import build_parser


def _verb_parser(command: CommandSpec) -> argparse.ArgumentParser:
    """Return the sub-parser of ``<group> <verb>`` of the generated CLI."""
    root = build_parser()
    group_action = next(a for a in root._actions if a.dest == "group")
    group_parser = cast(Any, group_action).choices[command.group]
    verb_action = next(a for a in group_parser._actions if a.dest == "verb")
    return cast(argparse.ArgumentParser, cast(Any, verb_action).choices[command.verb])


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_every_catalog_option_is_a_keyword_of_the_public_function(
    command: CommandSpec,
) -> None:
    function = getattr(hydraulik, command.python_name)
    parameters = inspect.signature(function).parameters

    for option in command.options:
        assert option.name in parameters, f"{command.python_name} lacks {option.name}"
        assert parameters[option.name].kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_every_catalog_option_is_a_flag_of_the_cli(command: CommandSpec) -> None:
    verb_parser = _verb_parser(command)
    flags = {flag for action in verb_parser._actions for flag in action.option_strings}

    for option in command.options:
        assert option.flag in flags
        if option.short:
            assert option.short in flags


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_public_function_requires_nothing_that_the_catalog_lacks(
    command: CommandSpec,
) -> None:
    function = getattr(hydraulik, command.python_name)
    names = {option.name for option in command.options}

    for parameter in inspect.signature(function).parameters.values():
        if parameter.default is inspect.Parameter.empty:
            assert parameter.name in names
