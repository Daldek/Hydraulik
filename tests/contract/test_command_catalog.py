"""The catalog against the vendored Nogat schema and its own rules (AGI §2, AGI-4.1)."""

import re
from importlib import import_module

import pytest

import hydraulik
from hydraulik import _errors, list_commands
from hydraulik.catalog.commands import COMMAND_PATTERN, COMMANDS
from hydraulik.catalog.spec import CommandSpec
from hydraulik.cli.parser import build_parser

from . import _nogat

DOCUMENT = list_commands().to_dict()


def test_catalog_document_validates_against_the_vendored_schema() -> None:
    _nogat.validator("commands-1").validate(DOCUMENT)


def test_names_and_operation_ids_are_unique_and_follow_the_rules() -> None:
    names = [c.name for c in COMMANDS]
    ids = [c.operation_id for c in COMMANDS]

    assert len(set(names)) == len(names)
    assert len(set(ids)) == len(ids)
    for command in COMMANDS:
        assert re.fullmatch(COMMAND_PATTERN, command.name)
        assert command.operation_id == "hydraulik_" + command.name.replace(
            " ", "_"
        ).replace("-", "_")
        assert len(command.operation_id) <= 48


def test_summaries_fit_the_100_character_budget_and_start_with_a_verb() -> None:
    for command in COMMANDS:
        assert len(command.summary) <= 100
        assert command.summary[0].isupper()
        assert command.summary.endswith(".")


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_function_of_a_command_is_public_api(command: CommandSpec) -> None:
    module, _, name = command.function.rpartition(".")

    assert module == "hydraulik"
    assert name in hydraulik.__all__
    assert callable(getattr(import_module(module), name))


def test_errors_of_every_command_are_codes_of_the_registry() -> None:
    registry = {c.code for c in _errors.CODES}

    for command in COMMANDS:
        assert set(command.errors) <= registry
        assert "internal_error" in command.errors


def test_read_only_commands_have_no_writes_and_no_plan() -> None:
    for command in COMMANDS:
        if command.effects.read_only:
            assert command.effects.writes == "none"
            assert command.check is None
        else:
            assert command.check == command.name  # a writing command plans itself


def test_every_writing_command_has_a_check_option_and_a_path_role() -> None:
    for command in COMMANDS:
        if not command.effects.read_only:
            assert command.option("check") is not None
            assert any(o.path_role == "output" for o in command.options)


def test_polish_texts_exist_for_every_translatable_field() -> None:
    for command in COMMANDS:
        pl = command.i18n_pl
        assert pl["summary"] and pl["description"]
        assert len(pl["rules"]) == len(command.rules)


def test_every_example_call_names_its_command_and_passes_the_parser() -> None:
    parser = build_parser()
    for command in COMMANDS:
        assert command.examples
        for example in command.examples:
            words = example.call.split()
            assert words[0] == "hydraulik"
            import shlex

            args = shlex.split(example.call)[1:]
            namespace = parser.parse_args(args)
            assert f"{namespace.group} {namespace.verb}" == command.name


def test_option_names_are_snake_case_and_the_shared_names_are_used_as_agreed() -> None:
    for command in COMMANDS:
        for option in command.options:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", option.name)
            if option.name == "output_dir":
                assert option.short == "-o" and option.path_role == "output"
            if option.name == "output":
                assert option.short is None and option.path_role == "output"
            if option.name in ("root", "store", "path"):
                pytest.fail(f"{option.name} is not a write target of Hydraulik")
