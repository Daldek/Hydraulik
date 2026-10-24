"""Command-line interface: ``hydraulik <group> <verb> [options]`` (AGI §3)."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Sequence
from typing import Any, Literal

from hydraulik.catalog.dispatch import find_command, run_command
from hydraulik.catalog.envelope import build_envelope, exit_code_of
from hydraulik.cli.parser import build_parser, options_from
from hydraulik.cli.render import render_envelope, render_error
from hydraulik.exceptions import InvalidInputError, error_document
from hydraulik.settings import load_settings

__all__ = ["main"]

_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}


def _utf8() -> None:
    """Make stdout and stderr UTF-8 whatever the console encoding is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _configure_logging(level_name: str, verbose: bool, quiet: bool) -> None:
    """Send logs to stderr; the library never configures handlers (DEV-12.1)."""
    level = (
        logging.DEBUG
        if verbose
        else logging.ERROR
        if quiet
        else _LEVELS.get(level_name, logging.ERROR)
    )
    logging.basicConfig(
        stream=sys.stderr, level=level, format="%(levelname)s %(name)s: %(message)s"
    )


def _fail(
    exc: BaseException, command: str | None, lang: Literal["pl", "en"], as_json: bool
) -> int:
    """Print the error (stdout stays empty) and return its exit code (AGI-3.3)."""
    document = error_document(exc, command=command, lang="en")
    if not as_json:
        sys.stderr.write(render_error(document, lang))
    if document["code"] == "internal_error":
        logging.getLogger(__name__).debug("unexpected exception", exc_info=exc)
    sys.stderr.write(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    sys.stderr.flush()
    return int(document["exit_code"])


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Parameters
    ----------
    argv : sequence of str or None, optional
        Arguments after the program name; ``sys.argv[1:]`` when ``None``.

    Returns
    -------
    int
        The exit code of the registry: 0, 10, 11 or 130 for an outcome (ERR §1), the
        code of the error otherwise (ERR §2). ``--help`` and ``--version`` give 0.
    """
    _utf8()
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    lang: Literal["pl", "en"] = "en"
    command: str | None = None
    try:
        namespace = build_parser().parse_args(args)
        group, verb = (
            getattr(namespace, "group", None),
            getattr(namespace, "verb", None),
        )
        if not group or not verb:
            raise InvalidInputError(
                "a command is required",
                hint="Run `hydraulik commands list` to see the commands.",
                reason="usage",
            )
        as_json = bool(getattr(namespace, "json", False))
        settings = load_settings({"lang": getattr(namespace, "lang", None)})
        lang = settings.value("lang")
        _configure_logging(
            settings.value("log_level"),
            bool(getattr(namespace, "verbose", False)),
            bool(getattr(namespace, "quiet", False)),
        )
        command = f"{group} {verb}"
        spec = find_command(command)
        options = options_from(namespace, spec)
        document = run_command(command, **options)
        envelope: dict[str, Any] = build_envelope(
            command, document, check=bool(options.get("check"))
        )
    except SystemExit as exc:  # --help and --version
        return int(exc.code) if isinstance(exc.code, int) else 0
    except BaseException as exc:  # noqa: BLE001 - every error becomes a document
        return _fail(exc, command, lang, as_json)
    if as_json:
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n")
    elif (
        envelope["command"] == "commands guide"
        and not envelope["result"]["injected_into"]
    ):
        sys.stdout.write(envelope["result"]["text"])  # raw, so it can be redirected
    else:
        sys.stdout.write(render_envelope(envelope, lang))
    sys.stdout.flush()
    return exit_code_of(envelope["status"])
