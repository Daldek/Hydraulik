"""The argparse parser, generated from the command catalog (AGI-3.1).

Option flags are the kebab-case forms of the catalog option names. Values are
converted from text only as far as the JSON type needs; every range, enum and
exclusion check is the one of :func:`hydraulik.catalog.validate.validate_options`, so
the CLI and the library report the same errors (AGI-1.2).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any, NoReturn

from hydraulik import __version__
from hydraulik.catalog.commands import COMMANDS
from hydraulik.catalog.spec import CommandSpec, OptionSpec
from hydraulik.exceptions import InvalidInputError

__all__ = ["build_parser", "options_from"]


class _Parser(argparse.ArgumentParser):
    """An argument parser whose usage errors are ``validation_error``."""

    def error(self, message: str) -> NoReturn:
        raise InvalidInputError(
            f"{self.prog}: {message}",
            details={"prog": self.prog},
            hint="Run the command with --help, or `hydraulik commands list`.",
            reason="usage",
        )


def _common() -> _Parser:
    """Return the parent parser of the options every command accepts (AGI-3.4)."""
    common = _Parser(add_help=False)
    group = common.add_argument_group("global options")
    group.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print exactly one JSON document (hydraulik-result/1) on stdout",
    )
    group.add_argument(
        "--lang",
        choices=("pl", "en"),
        default=argparse.SUPPRESS,
        help="language of human-readable output: pl or en (machine output is English)",
    )
    group.add_argument(
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="log debug messages on stderr",
    )
    group.add_argument(
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="log errors only on stderr",
    )
    return common


def _split(item_type: str | None) -> Any:
    """Return the converter of one comma-separated CLI value to a list."""

    def convert(text: str) -> list[Any]:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        try:
            if item_type == "integer":
                return [int(part, 10) for part in parts]
            if item_type == "number":
                return [float(part) for part in parts]
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"expected comma-separated {item_type} values, got {text!r}"
            ) from None
        return parts

    return convert


def _number(kind: str) -> Any:
    def convert(text: str) -> int | float:
        try:
            return int(text, 10) if kind == "integer" else float(text)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"expected a {'whole number' if kind == 'integer' else 'number'}, "
                f"got {text!r}"
            ) from None

    return convert


def _help(option: OptionSpec) -> str:
    parts = [option.description]
    if option.unit:
        parts.append(f"[{option.unit}]")
    if option.enum:
        parts.append(
            "Values: "
            + "; ".join(f"{value} = {meaning}" for value, meaning in option.enum)
        )
    if option.type == "array":
        parts.append("Comma-separated.")
    if option.required:
        parts.append("Required.")
    if option.default is not None and option.type != "boolean":
        default = option.default
        if not isinstance(default, type(None)) and repr(default) != "NO_DEFAULT":
            parts.append(f"Default: {default}.")
    return " ".join(parts).replace("%", "%%")


def _add_option(parser: argparse.ArgumentParser, option: OptionSpec) -> None:
    flags = [option.flag] + ([option.short] if option.short else [])
    kwargs: dict[str, Any] = {
        "dest": option.name,
        "default": None,
        "help": _help(option),
    }
    if option.type == "boolean":
        kwargs["action"] = "store_true"
        kwargs["default"] = None
    elif option.type == "array":
        kwargs["type"] = _split(option.items)
        kwargs["action"] = "extend"
    elif option.type in ("integer", "number"):
        kwargs["type"] = _number(option.type)
    parser.add_argument(*flags, **kwargs)


def _examples(spec: CommandSpec) -> str:
    return "examples:\n" + "\n".join(f"  {example.call}" for example in spec.examples)


def build_parser() -> argparse.ArgumentParser:
    """Build the parser of ``hydraulik <group> <verb> [options]`` from the catalog.

    Returns
    -------
    argparse.ArgumentParser
        A parser whose errors raise :class:`~hydraulik.exceptions.InvalidInputError`.
    """
    common = _common()
    root = _Parser(
        prog="hydraulik",
        description=(
            "Build SFINCS flood models, run the external engines and couple them "
            "with a SWMM sewer network."
        ),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Start with: hydraulik commands list",
    )
    root.add_argument("--version", action="version", version=f"hydraulik {__version__}")
    groups = root.add_subparsers(dest="group", metavar="<group>", parser_class=_Parser)
    seen: dict[str, Any] = {}
    for spec in COMMANDS:
        if spec.group not in seen:
            group_parser = groups.add_parser(
                spec.group, help=f"{spec.group} commands", parents=[common]
            )
            seen[spec.group] = group_parser.add_subparsers(
                dest="verb", metavar="<verb>", parser_class=_Parser
            )
        verb_parser = seen[spec.group].add_parser(
            spec.verb,
            help=spec.summary,
            description=f"{spec.summary}\n\n{spec.description}",
            epilog=_examples(spec),
            parents=[common],
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        for option in spec.options:
            _add_option(verb_parser, option)
    return root


def options_from(namespace: argparse.Namespace, spec: CommandSpec) -> dict[str, Any]:
    """Return the options of ``spec`` that were given on the command line.

    Parameters
    ----------
    namespace : argparse.Namespace
        The parsed command line.
    spec : CommandSpec
        The command that was parsed.

    Returns
    -------
    dict
        Option name to value, only for options that were given.
    """
    given: dict[str, Any] = {}
    for option in spec.options:
        value = getattr(namespace, option.name, None)
        if value is not None:
            given[option.name] = value
    return given


def known_groups() -> Sequence[str]:
    """Return the command groups in catalog order."""
    return list(dict.fromkeys(spec.group for spec in COMMANDS))
