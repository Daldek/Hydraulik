"""Validation of command options against the catalog (AGI-2.1, DEV-11.3)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

from hydraulik.catalog.spec import NO_DEFAULT, CommandSpec, OptionSpec
from hydraulik.exceptions import InvalidInputError

__all__ = ["validate_options"]


def _fail(
    option: OptionSpec,
    value: object,
    why: str,
    reason: str,
    *,
    allowed: object = None,
) -> InvalidInputError:
    details: dict[str, object] = {"option": option.name, "value": _shown(value)}
    if allowed is not None:
        details["allowed"] = allowed
    return InvalidInputError(
        f"{option.flag}: {why}",
        details=details,
        hint=f"Correct {option.flag}: {option.description}",
        reason=reason,
    )


def _shown(value: object) -> object:
    """Return ``value`` in a form that is safe to put into an error document."""
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return str(value)


def _check_scalar(option: OptionSpec, kind: str, value: Any) -> Any:
    """Return ``value`` checked as the JSON type ``kind`` or raise."""
    if kind == "string":
        if isinstance(value, os.PathLike):
            value = os.fspath(value)
        if not isinstance(value, str):
            raise _fail(option, value, "expected text", "wrong_type")
        return value
    if kind == "boolean":
        if not isinstance(value, bool):
            raise _fail(option, value, "expected true or false", "wrong_type")
        return value
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _fail(option, value, "expected a whole number", "wrong_type")
        return value
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _fail(option, value, "expected a number", "wrong_type")
        return value
    raise AssertionError(f"unknown option type {kind}")  # pragma: no cover


def _check_value(option: OptionSpec, value: Any) -> Any:
    """Return ``value`` checked against the type, bounds, enum and pattern."""
    if option.type == "array":
        if isinstance(value, str) or not isinstance(value, list | tuple):
            raise _fail(option, value, "expected a list", "wrong_type")
        kind = option.items or "string"
        items = [_check_scalar(option, kind, item) for item in value]
        allowed = [entry[0] for entry in option.enum]
        for item in items:
            if allowed and item not in allowed:
                raise _fail(
                    option,
                    item,
                    f"must be one of {', '.join(str(a) for a in allowed)}",
                    "not_allowed",
                    allowed=allowed,
                )
        return items
    if option.type == "object":
        if not isinstance(value, Mapping):
            raise _fail(option, value, "expected an object", "wrong_type")
        return dict(value)
    checked = _check_scalar(option, option.type, value)
    if option.enum:
        allowed = [entry[0] for entry in option.enum]
        if checked not in allowed:
            raise _fail(
                option,
                checked,
                f"must be one of {', '.join(str(a) for a in allowed)}",
                "not_allowed",
                allowed=allowed,
            )
    if option.min is not None and checked < option.min:
        raise _fail(option, checked, f"must be at least {option.min}", "out_of_range")
    if option.max is not None and checked > option.max:
        raise _fail(option, checked, f"must be at most {option.max}", "out_of_range")
    if option.pattern and not re.fullmatch(option.pattern, checked):
        raise _fail(option, checked, f"must match {option.pattern}", "pattern_mismatch")
    return checked


def validate_options(spec: CommandSpec, options: Mapping[str, Any]) -> dict[str, Any]:
    """Check ``options`` against the declaration of a command.

    Parameters
    ----------
    spec : CommandSpec
        The command.
    options : Mapping[str, Any]
        Option values by name; ``None`` counts as not given.

    Returns
    -------
    dict
        The options with the defaults filled in, in the order of the declaration.

    Raises
    ------
    InvalidInputError
        On an unknown option, a missing required option, a wrong type, a value out
        of range or not allowed, or two options of one exclusion group. The error
        names the option and the allowed values.

    Examples
    --------
    >>> from hydraulik.catalog.commands import COMMANDS
    >>> spec = next(c for c in COMMANDS if c.name == "commands guide")
    >>> validate_options(spec, {})["format"]
    'agents'
    """
    known = {option.name: option for option in spec.options}
    for name in options:
        if name not in known:
            raise InvalidInputError(
                f"Unknown option {name!r} for '{spec.name}'",
                details={"option": name, "allowed": sorted(known)},
                hint=f"See `hydraulik commands schema --command '{spec.name}'`.",
                reason="unknown_option",
            )
    result: dict[str, Any] = {}
    for option in spec.options:
        value = options.get(option.name)
        if value is None:
            if option.required:
                raise InvalidInputError(
                    f"{option.flag} is required by '{spec.name}'",
                    details={"option": option.name},
                    hint=f"Give {option.flag}: {option.description}",
                    reason="missing_option",
                )
            if option.default is not NO_DEFAULT and option.default is not None:
                result[option.name] = option.default
            continue
        result[option.name] = _check_value(option, value)
    groups: dict[str, list[str]] = {}
    for option in spec.options:
        if option.one_of and option.name in result:
            groups.setdefault(option.one_of, []).append(option.name)
    for group, names in groups.items():
        if len(names) > 1:
            raise InvalidInputError(
                f"Options {', '.join(names)} exclude each other (group {group})",
                details={"option": names[0], "options": names, "group": group},
                hint=f"Give only one of: {', '.join(names)}.",
                reason="exclusive_options",
            )
    return result
