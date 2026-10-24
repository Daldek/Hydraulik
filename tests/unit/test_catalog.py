"""Validation and dispatch of the command catalog (AGI-2.1, DEV-11.3)."""

from dataclasses import replace
from typing import Any

import pytest

from hydraulik import (
    check_command,
    command_schema,
    list_commands,
    run_command,
    validate_command,
)
from hydraulik.catalog.commands import COMMANDS
from hydraulik.catalog.spec import CommandSpec, Effects, Example, OptionSpec
from hydraulik.catalog.validate import validate_options
from hydraulik.exceptions import InvalidInputError


def _spec(*options: OptionSpec) -> CommandSpec:
    return CommandSpec(
        name="demo run",
        operation_id="hydraulik_demo_run",
        function="hydraulik.demo_run",
        summary="Run a demo.",
        description="A demo command.",
        options=options,
        result_schema="hydraulik-demo/1",
        effects=Effects(),
        check=None,
        rules=("Be careful.",),
        examples=(Example("hydraulik demo run", {}),),
        errors=("validation_error",),
    )


def _error(spec: CommandSpec, options: dict[str, Any]) -> InvalidInputError:
    with pytest.raises(InvalidInputError) as caught:
        validate_options(spec, options)
    return caught.value


def test_defaults_are_filled_in_the_order_of_the_declaration() -> None:
    spec = _spec(
        OptionSpec("a", "integer", "A.", default=3),
        OptionSpec("b", "string", "B.", default="x"),
        OptionSpec("c", "string", "C."),
    )

    assert list(validate_options(spec, {})) == ["a", "b"]
    assert validate_options(spec, {"b": "y"}) == {"a": 3, "b": "y"}


def test_none_counts_as_not_given() -> None:
    spec = _spec(OptionSpec("a", "integer", "A.", default=3))

    assert validate_options(spec, {"a": None}) == {"a": 3}


def test_unknown_option_is_named_with_the_allowed_ones() -> None:
    error = _error(_spec(OptionSpec("a", "integer", "A.")), {"b": 1})

    assert error.details["reason"] == "unknown_option"
    assert error.details["option"] == "b"
    assert error.details["allowed"] == ["a"]


def test_missing_required_option_is_named() -> None:
    error = _error(_spec(OptionSpec("a", "integer", "A.", required=True)), {})

    assert error.details["reason"] == "missing_option"
    assert error.details["option"] == "a"


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("integer", True),
        ("integer", 1.5),
        ("integer", "3"),
        ("number", "3"),
        ("number", False),
        ("boolean", 1),
        ("string", 3),
        ("array", "a,b"),
        ("object", [1]),
    ],
)
def test_wrong_type_is_refused(kind: str, value: object) -> None:
    spec = _spec(OptionSpec("a", kind, "A."))  # type: ignore[arg-type]

    assert _error(spec, {"a": value}).details["reason"] == "wrong_type"


def test_enum_bounds_and_pattern_name_the_option() -> None:
    spec = _spec(
        OptionSpec("mode", "string", "Mode.", enum=(("x", "ex"), ("y", "why"))),
        OptionSpec("n", "number", "N.", min=0, max=10),
        OptionSpec("code", "string", "Code.", pattern=r"[a-z]+"),
    )

    assert _error(spec, {"mode": "z"}).details["allowed"] == ["x", "y"]
    assert _error(spec, {"n": -1}).details["reason"] == "out_of_range"
    assert _error(spec, {"n": 11}).details["reason"] == "out_of_range"
    assert _error(spec, {"code": "A1"}).details["reason"] == "pattern_mismatch"
    assert validate_options(spec, {"mode": "x", "n": 10, "code": "ab"}) == {
        "mode": "x",
        "n": 10,
        "code": "ab",
    }


def test_array_items_are_checked_against_their_type() -> None:
    spec = _spec(OptionSpec("bbox", "array", "Box.", items="number"))

    assert validate_options(spec, {"bbox": [1, 2.5]}) == {"bbox": [1, 2.5]}
    assert _error(spec, {"bbox": [1, "x"]}).details["reason"] == "wrong_type"


def test_options_of_one_exclusion_group_cannot_be_combined() -> None:
    spec = _spec(
        OptionSpec("a", "string", "A.", one_of="g"),
        OptionSpec("b", "string", "B.", one_of="g"),
    )

    error = _error(spec, {"a": "1", "b": "2"})

    assert error.details["reason"] == "exclusive_options"
    assert error.details["options"] == ["a", "b"]
    assert validate_options(spec, {"a": "1"}) == {"a": "1"}


def test_a_path_like_value_is_accepted_for_a_string_option() -> None:
    from pathlib import Path

    spec = _spec(OptionSpec("path", "string", "Path.", path_role="input"))

    assert validate_options(spec, {"path": Path("a") / "b"}) == {
        "path": str(Path("a") / "b")
    }


def test_validate_command_fills_defaults_without_effects() -> None:
    assert validate_command("commands guide") == {"format": "agents", "check": False}


def test_unknown_command_lists_the_known_ones() -> None:
    with pytest.raises(InvalidInputError) as caught:
        validate_command("model nothing")

    assert caught.value.details["reason"] == "unknown_command"
    assert "config show" in caught.value.details["allowed"]


def test_an_option_may_itself_be_called_command() -> None:
    document = run_command("commands schema", command="config show")

    assert document.to_dict()["commands"][0]["name"] == "config show"


def test_check_of_a_read_only_command_says_to_run_it() -> None:
    with pytest.raises(InvalidInputError) as caught:
        check_command("config show")

    assert caught.value.details["reason"] == "no_check_mode"


def test_run_command_returns_the_document_of_the_function() -> None:
    assert run_command("config show").to_dict()["schema"] == "hydraulik-config/1"


def test_command_schema_describes_exactly_one_command() -> None:
    document = command_schema("commands guide").to_dict()

    assert [c["name"] for c in document["commands"]] == ["commands guide"]
    assert document["tool"] == "hydraulik"


def test_list_commands_describes_every_declared_command() -> None:
    names = [c["name"] for c in list_commands().to_dict()["commands"]]

    assert names == [spec.name for spec in COMMANDS]


def test_option_flag_is_the_kebab_case_of_the_name() -> None:
    option = OptionSpec("output_dir", "string", "Dir.", short="-o")

    assert option.flag == "--output-dir"
    assert option.to_dict()["short"] == "-o"
    assert replace(option, default=None).to_dict()["default"] is None
