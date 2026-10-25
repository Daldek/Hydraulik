"""Kartograf as a program: its option schema, its plain-file mode and its results.

Hydraulik never imports Kartograf (ADR-0003, ADR-0006). ``terrain download`` starts the
``kartograf`` command with ``--output-dir``, which writes plain files into a directory
(DEV-19.1, ECO-051), and reads its ``kartograf-result/1`` envelope. Nothing is assumed
about the installed version:

* what Kartograf offers comes from ``kartograf commands schema --command "<group>
  <verb>" --json`` (:meth:`KartografCli.schema`), and an argument is built only from an
  option that schema declares (:meth:`KartografCli.run`);
* a Kartograf whose ``output_dir`` is not a plain target (``path_role: output``) is
  refused (:func:`plain_output_problem`): in a Kartograf without the data-output
  convention ``output_dir`` is the root of a versioned store, and ``--output-dir``
  would write a store into the directory of the user;
* the result is read as the convention says: ``files[]`` is ``{path, size_bytes, sha256,
  status}``, ``skipped[]`` is ``{id, reason, message}`` (DEV-19.4, DEV-19.19), an error
  is the last line of stderr as ``kartograf-error/1``, the exit code is 0, 10 or 11 for
  an outcome. The plan of ``--check`` has no fixed field names, so every entry of it
  that has an ``action`` (``write``, ``replace`` or ``conflict``) and a ``path`` is read
  as a target (:func:`plan_targets`).
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from hydraulik.exceptions import (
    CancelledError,
    HydraulikError,
    MissingDependencyError,
    SourceUnavailableError,
    rebuild_error,
)

__all__ = [
    "PRODUCTS",
    "RECIPES",
    "CommandInfo",
    "KartografCli",
    "KartografRun",
    "OptionInfo",
    "Recipe",
    "Source",
    "parse_command_info",
    "plain_output_problem",
    "plan_targets",
]

logger = logging.getLogger(__name__)

RESULT_SCHEMA: Final = "kartograf-result/1"
ERROR_SCHEMA: Final = "kartograf-error/1"
_OUTCOMES: Final = {0: "ok", 10: "partial", 11: "failed"}
_TAIL_LINES: Final = 40
_STOP_GRACE_S: Final = 5.0
_ACTIONS: Final = ("write", "replace", "conflict")

_INCOMPATIBLE_HINT: Final = (
    "Use a Kartograf that implements the data-output convention (Nogat DEV section "
    "19): "
    "`kartograf commands schema --command '<group> <verb>' --json` must list "
    "output_dir with path_role output."
)


@dataclass(frozen=True)
class Source:
    """Who publishes the data of a product and under what terms.

    Attributes
    ----------
    provider : str
        Short name of the organisation.
    licence : str
        Licence identifier, as Kartograf names it (``kartograf <group> list-sources``).
    attribution : str
        The text to print with the data.
    url : str
        Where the terms are.
    """

    provider: str
    licence: str
    attribution: str
    url: str


_GUGIK = Source(
    "GUGiK",
    "PL-PGiK-40a",
    "Dane: Główny Urząd Geodezji i Kartografii (www.geoportal.gov.pl), "
    "art. 40a ust. 2 pkt 1 ustawy Prawo geodezyjne i kartograficzne",
    "https://www.geoportal.gov.pl",
)
_ISRIC = Source(
    "ISRIC",
    "CC-BY-4.0",
    "SoilGrids - ISRIC World Soil Information, CC BY 4.0",
    "https://www.isric.org/explore/soilgrids",
)


@dataclass(frozen=True)
class Recipe:
    """The Kartograf call that fetches one product of ``terrain download``.

    Attributes
    ----------
    product : str
        Name in Hydraulik: ``elevation``, ``landcover`` or ``soil``.
    command : str
        Kartograf command, ``<group> <verb>``.
    options : dict
        Options of that command that the product fixes (never the area, never the
        output).
    summary : str
        What the call fetches, for the plan.
    source : Source
        Provider and terms of the data.
    """

    product: str
    command: str
    options: Mapping[str, Any]
    summary: str
    source: Source


RECIPES: Final[dict[str, Recipe]] = {
    "elevation": Recipe(
        "elevation",
        "elevation download",
        {
            "product": "nmt",
            "country": "pl",
            "cutout": True,
            "horizontal_crs": "EPSG:2180",
            "vertical_crs": "EVRF2007",
        },
        "the 1 m terrain model (NMT) as one GeoTIFF in EPSG:2180",
        _GUGIK,
    ),
    "landcover": Recipe(
        "landcover",
        "landcover download",
        {"product": "bdot10k"},
        "the BDOT10k GeoPackage of the county or counties of the area",
        _GUGIK,
    ),
    "soil": Recipe(
        "soil",
        "soil hsg",
        {"depth": "0-5cm"},
        "the hydrologic soil groups of SoilGrids (uint8: 1 A to 4 D, 0 no data) "
        "as one GeoTIFF",
        _ISRIC,
    ),
}
"""What ``terrain download`` fetches, in the order it fetches it."""

PRODUCTS: Final = tuple(RECIPES)
"""The names of the products."""


@dataclass(frozen=True)
class OptionInfo:
    """One option of a Kartograf command, as its schema declares it.

    Attributes
    ----------
    name : str
        snake_case name; the flag is ``--`` plus the name with dashes (AGI-3.1).
    type : str
        JSON type of the value.
    path_role : str or None
        ``input``, ``output`` or ``root`` for a path, ``None`` otherwise.
    allowed : tuple of str
        The values of its ``enum`` as text; empty when any value is allowed.
    required : bool
        Whether a call must give it.
    """

    name: str
    type: str
    path_role: str | None
    allowed: tuple[str, ...]
    required: bool

    @property
    def flag(self) -> str:
        """str: the command-line flag, for example ``--output-dir``."""
        return "--" + self.name.replace("_", "-")


@dataclass(frozen=True)
class CommandInfo:
    """One Kartograf command and the options its schema declares.

    Attributes
    ----------
    name : str
        ``<group> <verb>``.
    options : dict of str to OptionInfo
        The options by name.
    """

    name: str
    options: Mapping[str, OptionInfo]

    def problem(self, name: str, value: object) -> str | None:
        """Say why Kartograf cannot take ``value`` for the option ``name``.

        Parameters
        ----------
        name : str
            Option name in Kartograf's schema.
        value : object
            The value that would be passed.

        Returns
        -------
        str or None
            The reason, or ``None`` when the option exists and its ``enum`` (if any)
            holds every value.
        """
        option = self.options.get(name)
        if option is None:
            return f"`{self.name}` has no --{name.replace('_', '-')}"
        if option.allowed and not isinstance(value, bool):
            values = value if isinstance(value, list | tuple) else [value]
            for item in values:
                if _text(item) not in option.allowed:
                    return (
                        f"{option.flag} of `{self.name}` takes "
                        f"{', '.join(option.allowed)}, not {_text(item)}"
                    )
        return None


def _text(value: object) -> str:
    return str(value)


def parse_command_info(envelope: Mapping[str, Any], command: str) -> CommandInfo:
    """Read the options of ``command`` from the answer of ``commands schema``.

    Parameters
    ----------
    envelope : Mapping
        The ``kartograf-result/1`` document of
        ``kartograf commands schema --command <command> --json``.
    command : str
        The command that was asked about.

    Returns
    -------
    CommandInfo
        Its options with their path roles and allowed values.

    Raises
    ------
    MissingDependencyError
        If the document does not describe ``command`` (reason ``engine_incompatible``).
    """
    result = envelope.get("result")
    commands = result.get("commands") if isinstance(result, dict) else None
    entry = next(
        (
            item
            for item in commands or []
            if isinstance(item, dict) and item.get("name") == command
        ),
        None,
    )
    if entry is None or not isinstance(entry.get("options"), list):
        raise MissingDependencyError(
            f"the installed Kartograf does not describe `{command}`",
            details={"engine": "kartograf", "command": command},
            hint=_INCOMPATIBLE_HINT,
            reason="engine_incompatible",
        )
    options: dict[str, OptionInfo] = {}
    for raw in entry["options"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            continue
        enum = raw.get("enum")
        allowed = tuple(
            _text(item["value"])
            for item in (enum if isinstance(enum, list) else [])
            if isinstance(item, dict) and "value" in item
        )
        role = raw.get("path_role")
        options[raw["name"]] = OptionInfo(
            raw["name"],
            str(raw.get("type", "string")),
            role if isinstance(role, str) else None,
            allowed,
            bool(raw.get("required", False)),
        )
    return CommandInfo(command, options)


def plain_output_problem(info: CommandInfo) -> str | None:
    """Say why a Kartograf command cannot write plain files, if it cannot.

    Parameters
    ----------
    info : CommandInfo
        A command of the installed Kartograf.

    Returns
    -------
    str or None
        ``None`` when ``output_dir`` is declared with ``path_role: output`` (DEV-19.1:
        plain files in a directory); otherwise the reason, which names what the option
        is instead.
    """
    option = info.options.get("output_dir")
    if option is None:
        return f"`{info.name}` has no --output-dir"
    if option.path_role == "root":
        return (
            "its --output-dir is the root of a versioned store (path_role root), not "
            "a directory of plain files (path_role output)"
        )
    if option.path_role != "output":
        return f"its --output-dir has path_role {option.path_role}, not output"
    return None


def plan_targets(document: Any) -> list[dict[str, str]]:
    """Return the targets that a plan of ``--check`` lists.

    The field names of the plan are not fixed by the convention, so this reads every
    entry anywhere in the document that has an ``action`` of ``write``, ``replace`` or
    ``conflict`` and a ``path`` (DEV-19.10).

    Parameters
    ----------
    document : object
        The ``result`` of the envelope of a ``--check`` call.

    Returns
    -------
    list of dict
        ``path``, ``action`` and, when the entry has one, ``reason``; in document order.

    Examples
    --------
    >>> plan_targets({"items": [{"path": "/d/a.tif", "action": "write"}]})
    [{'path': '/d/a.tif', 'action': 'write'}]
    """
    found: list[dict[str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            path, action = node.get("path"), node.get("action")
            if isinstance(path, str) and action in _ACTIONS:
                entry = {"path": path, "action": str(action)}
                reason = node.get("reason")
                if isinstance(reason, str) and reason:
                    entry["reason"] = reason
                found.append(entry)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return found


@dataclass(frozen=True)
class KartografRun:
    """What one call of Kartograf returned.

    Attributes
    ----------
    command : str
        ``<group> <verb>``.
    argv : tuple of str
        The arguments after the program, ``--json`` included.
    status : {"ok", "partial", "failed"}
        The outcome of Kartograf (its exit code 0, 10 or 11).
    files : tuple of dict
        ``{path, size_bytes, sha256, status}`` of each file written (DEV-19.19).
    skipped : tuple of dict
        ``{id, reason, message}`` of each unit that plain mode left out (DEV-19.4).
    items : tuple of dict
        Per-unit outcomes ``{id, status, code?, reason?, message?}`` (AGI-4.2).
    notices : tuple of dict
        ``{level, code, message}`` of the envelope.
    targets : tuple of dict
        The targets of a ``--check`` plan (:func:`plan_targets`); empty for a real run.
    """

    command: str
    argv: tuple[str, ...]
    status: str
    files: tuple[dict[str, Any], ...]
    skipped: tuple[dict[str, str], ...]
    items: tuple[dict[str, Any], ...]
    notices: tuple[dict[str, str], ...]
    targets: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class _Completed:
    returncode: int
    stdout: str
    stderr_tail: tuple[str, ...]


def _stop(process: subprocess.Popen[str]) -> None:
    """Stop Kartograf (it removes its staging on SIGTERM) and wait for it."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=_STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _call(words: Sequence[str], timeout_s: float, label: str) -> _Completed:
    """Run Kartograf, log its stderr, and return its exit code and output.

    Raises
    ------
    MissingDependencyError
        If the program cannot be started (reason ``engine_unavailable``).
    SourceUnavailableError
        If it runs longer than ``timeout_s`` (reason ``kartograf_timeout``).
    KeyboardInterrupt, TerminatedError
        Re-raised after the program was stopped.
    """
    try:
        process = subprocess.Popen(  # noqa: S603 - the program is the detected Kartograf
            list(words),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise MissingDependencyError(
            f"Kartograf could not be started: {exc}",
            details={"engine": "kartograf", "command": list(words[:1])},
            hint="Check `hydraulik engines check` and the permissions of the program.",
            reason="engine_unavailable",
        ) from exc
    out: list[str] = []
    tail: deque[str] = deque(maxlen=_TAIL_LINES)

    def read_stdout() -> None:
        assert process.stdout is not None
        out.append(process.stdout.read())

    def read_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            text = line.rstrip("\r\n")
            if text:
                tail.append(text)
                logger.info("kartograf: %s", text)

    readers = [
        threading.Thread(target=read_stdout, name="kartograf-stdout", daemon=True),
        threading.Thread(target=read_stderr, name="kartograf-stderr", daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        returncode = process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _stop(process)
        for reader in readers:
            reader.join(_STOP_GRACE_S)
        raise SourceUnavailableError(
            f"Kartograf `{label}` did not finish within {timeout_s:g} s: stopped",
            details={
                "engine": "kartograf",
                "command": label,
                "timeout_s": timeout_s,
                "stderr_tail": list(tail)[-5:],
            },
            hint="Raise kartograf.timeout_s (HYDRAULIK_KARTOGRAF_TIMEOUT_S) or ask for "
            "a smaller area.",
            reason="kartograf_timeout",
        ) from None
    except BaseException:
        _stop(process)
        raise
    for reader in readers:
        reader.join(_STOP_GRACE_S)
    return _Completed(returncode, "".join(out), tuple(tail))


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _failure(label: str, completed: _Completed) -> HydraulikError:
    """Return the error of a call that ended with an exit code that is no outcome."""
    last = completed.stderr_tail[-1] if completed.stderr_tail else ""
    document = _json_object(last)
    if document is not None and document.get("schema") == ERROR_SCHEMA:
        details = dict(document.get("details") or {})
        details.setdefault("engine", "kartograf")
        details.setdefault("command", label)
        hint = document.get("hint")
        return rebuild_error(
            str(document.get("code", "internal_error")),
            str(document.get("message", f"Kartograf `{label}` failed")),
            details=details,
            hint=hint if isinstance(hint, str) else None,
        )
    return SourceUnavailableError(
        f"Kartograf `{label}` exited with code {completed.returncode} and printed no "
        "error document",
        details={
            "engine": "kartograf",
            "command": label,
            "returncode": completed.returncode,
            "stderr_tail": list(completed.stderr_tail)[-5:],
        },
        hint="Run the same Kartograf command yourself with --json and read its stderr.",
        reason="kartograf_failed",
    )


def _bad_output(label: str, why: str, completed: _Completed) -> SourceUnavailableError:
    return SourceUnavailableError(
        f"Kartograf `{label}` answered with something that is not {RESULT_SCHEMA}: "
        f"{why}",
        details={
            "engine": "kartograf",
            "command": label,
            "returncode": completed.returncode,
            "stdout_head": completed.stdout[:200],
        },
        hint="Check that the installed Kartograf implements the data-output "
        "convention.",
        reason="kartograf_output",
    )


def _envelope(label: str, completed: _Completed) -> dict[str, Any]:
    """Return the ``kartograf-result/1`` envelope of a call that ended in an outcome."""
    document = _json_object(completed.stdout)
    if document is None:
        raise _bad_output(label, "the output is not a JSON object", completed)
    if document.get("schema") != RESULT_SCHEMA:
        raise _bad_output(label, f"schema {document.get('schema')!r}", completed)
    return document


def _files(result: Mapping[str, Any], label: str, completed: _Completed) -> list[Any]:
    """Return ``files[]`` of a result, each entry as DEV-19.19 defines it."""
    files: list[dict[str, Any]] = []
    for entry in result.get("files") or []:
        valid = (
            isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and isinstance(entry.get("size_bytes"), int)
            and isinstance(entry.get("sha256"), str)
            and isinstance(entry.get("status"), str)
        )
        if not valid:
            raise _bad_output(
                label,
                "a files[] entry is not {path, size_bytes, sha256, status}",
                completed,
            )
        files.append(
            {
                "path": entry["path"],
                "size_bytes": entry["size_bytes"],
                "sha256": entry["sha256"],
                "status": entry["status"],
            }
        )
    return files


def _strings(entries: Any, keys: Sequence[str]) -> list[dict[str, str]]:
    """Return the dictionaries of ``entries`` with every key of ``keys`` as text."""
    return [
        {key: str(entry[key]) for key in keys}
        for entry in entries or []
        if isinstance(entry, dict) and all(key in entry for key in keys)
    ]


def _items(entries: Any) -> list[dict[str, Any]]:
    """Return the per-unit outcomes of an envelope (AGI-4.2)."""
    items: list[dict[str, Any]] = []
    for entry in entries or []:
        if isinstance(entry, dict) and "id" in entry and "status" in entry:
            items.append(
                {
                    key: entry[key]
                    for key in ("id", "status", "code", "reason", "message")
                    if key in entry
                }
            )
    return items


class KartografCli:
    """Kartograf as a program that is started once per call.

    Parameters
    ----------
    words : sequence of str
        The command that runs Kartograf: the program, and anything before the
        arguments (a test starts a Python script this way).
    timeout_s : float
        Seconds one call that may fetch data may take.
    probe_timeout_s : float, optional
        Seconds a call of ``commands schema`` may take.
    """

    def __init__(
        self,
        words: Sequence[str],
        *,
        timeout_s: float,
        probe_timeout_s: float = 60.0,
    ) -> None:
        self.words = tuple(words)
        self.timeout_s = timeout_s
        self.probe_timeout_s = probe_timeout_s
        self._schemas: dict[str, CommandInfo] = {}

    def version(self) -> str | None:
        """Return the first line of ``kartograf --version``, or ``None``."""
        try:
            completed = _call(
                [*self.words, "--version"], self.probe_timeout_s, "--version"
            )
        except HydraulikError:
            return None
        text = (completed.stdout or "\n".join(completed.stderr_tail)).strip()
        return text.splitlines()[0] if text else None

    def schema(self, command: str) -> CommandInfo:
        """Return the options that the installed Kartograf declares for ``command``.

        Parameters
        ----------
        command : str
            ``<group> <verb>``, for example ``elevation download``.

        Returns
        -------
        CommandInfo
            Read from ``kartograf commands schema --command <command> --json``; kept
            for the next call.

        Raises
        ------
        MissingDependencyError
            If Kartograf has no ``commands schema`` or does not know ``command``
            (reason ``engine_incompatible``), or cannot be started.
        SourceUnavailableError
            If the call times out or answers with something else than the schema.
        """
        if command not in self._schemas:
            label = "commands schema"
            completed = _call(
                [*self.words, *label.split(), f"--command={command}", "--json"],
                self.probe_timeout_s,
                label,
            )
            if completed.returncode != 0:
                raise MissingDependencyError(
                    f"the installed Kartograf has no `{label}` for `{command}` "
                    f"(exit code {completed.returncode})",
                    details={
                        "engine": "kartograf",
                        "command": command,
                        "returncode": completed.returncode,
                    },
                    hint=_INCOMPATIBLE_HINT,
                    reason="engine_incompatible",
                )
            self._schemas[command] = parse_command_info(
                _envelope(label, completed), command
            )
        return self._schemas[command]

    def _arguments(self, info: CommandInfo, options: Mapping[str, Any]) -> list[str]:
        """Build the arguments of ``options`` from the options the schema declares."""
        arguments: list[str] = []
        for name, value in options.items():
            if value is None:
                continue
            problem = info.problem(name, value)
            if problem is not None:
                raise MissingDependencyError(
                    f"the installed Kartograf cannot do what `{info.name}` needs: "
                    f"{problem}",
                    details={
                        "engine": "kartograf",
                        "command": info.name,
                        "option": name,
                    },
                    hint=_INCOMPATIBLE_HINT,
                    reason="engine_incompatible",
                )
            flag = info.options[name].flag
            if isinstance(value, bool):
                if value:
                    arguments.append(flag)
            elif isinstance(value, list | tuple):
                arguments.append(f"{flag}={','.join(_text(item) for item in value)}")
            else:
                arguments.append(f"{flag}={_text(value)}")
        return arguments

    def run(
        self, command: str, options: Mapping[str, Any], *, check: bool = False
    ) -> KartografRun:
        """Run one Kartograf command and read its result.

        Parameters
        ----------
        command : str
            ``<group> <verb>``.
        options : Mapping
            Option values by the names of Kartograf's schema: lists are joined with
            commas, ``True`` is a bare flag, ``False`` and ``None`` are left out. Every
            name must be declared by the schema of the installed Kartograf.
        check : bool, optional
            Ask for the plan (``--check``): nothing is fetched or written.

        Returns
        -------
        KartografRun
            What the call returned, for an outcome of Kartograf (exit code 0, 10 or 11).

        Raises
        ------
        MissingDependencyError
            If the installed Kartograf lacks an option the call needs or its
            ``output_dir`` is not a plain target (reason ``engine_incompatible``).
        HydraulikError
            The error Kartograf reported, with its code, details and hint.
        CancelledError
            If Kartograf ended with code 130.
        SourceUnavailableError
            If Kartograf timed out, died without an error document or printed something
            that is not a ``kartograf-result/1`` envelope.
        """
        info = self.schema(command)
        if "output_dir" in options:
            problem = plain_output_problem(info)
            if problem is not None:
                raise MissingDependencyError(
                    f"the installed Kartograf cannot write plain files: {problem}",
                    details={
                        "engine": "kartograf",
                        "command": command,
                        "option": "output_dir",
                    },
                    hint=_INCOMPATIBLE_HINT,
                    reason="engine_incompatible",
                )
        arguments = self._arguments(info, {**options, "check": True if check else None})
        arguments.append("--json")
        argv = (*command.split(), *arguments)
        completed = _call([*self.words, *argv], self.timeout_s, command)
        if completed.returncode == 130:
            raise CancelledError(
                f"Kartograf `{command}` was cancelled",
                details={"engine": "kartograf", "command": command},
            )
        if completed.returncode not in _OUTCOMES:
            raise _failure(command, completed)
        envelope = _envelope(command, completed)
        result = envelope.get("result")
        result = result if isinstance(result, dict) else {}
        status = envelope.get("status")
        outcome = str(status) if status in _OUTCOMES.values() else None
        return KartografRun(
            command=command,
            argv=argv,
            status=outcome or _OUTCOMES[completed.returncode],
            files=tuple(_files(result, command, completed)),
            skipped=tuple(_strings(result.get("skipped"), ("id", "reason", "message"))),
            items=tuple(_items(envelope.get("items"))),
            notices=tuple(
                _strings(envelope.get("notices"), ("level", "code", "message"))
            ),
            targets=tuple(plan_targets(result)) if check else (),
        )
