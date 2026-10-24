"""Exceptions of Hydraulik and the ``hydraulik-error/1`` document.

Every :class:`HydraulikError` carries a ``code`` of the shared Nogat error
registry (DEV-11.1, ERR-1), JSON-compatible ``details`` and an optional one-line
``hint``. Each subclass has a default code; a raise site may pass another
registered code with ``code=``. Finer distinctions go to ``details["reason"]``
(ERR-1), which :class:`HydraulikError` accepts as the keyword ``reason``.

Messages and hints are English (AGI-9.2); only the registry titles exist in Polish
as well. :func:`error_document` turns any exception into the document that the CLI
prints on the last line of stderr (AGI-3.3).
"""

from __future__ import annotations

import copy
import errno
import os
from collections.abc import Mapping
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, ClassVar, Final, Literal

from hydraulik._errors import BY_CODE, CODES, ErrorCodeName, RegistryCode

__all__ = [
    "ERROR_CODES",
    "ERROR_SCHEMA",
    "CalculationError",
    "CancelledError",
    "ConflictError",
    "EngineError",
    "ErrorCode",
    "ForbiddenPathError",
    "HydraulikError",
    "InputDataError",
    "InvalidInputError",
    "MissingDependencyError",
    "NoDataError",
    "NotFoundError",
    "OutputError",
    "SourceUnavailableError",
    "TerminatedError",
    "UnsupportedError",
    "error_document",
]

ErrorCode = ErrorCodeName
"""Name of a registry code that a CLI call can end with."""

ERROR_SCHEMA: Final = "hydraulik-error/1"
"""Value of the ``schema`` key of an error document."""

ERROR_CODES: Mapping[str, RegistryCode] = MappingProxyType(
    {entry.code: entry for entry in CODES if entry.exit_code is not None}
)
"""Registry codes with an exit code, keyed by code (ERR-3, from ``_errors``)."""

_INTERNAL_HINT: Final = (
    "This is a bug: report it with the command, the inputs and the Hydraulik version."
)
_IO_HINT: Final = "Check that the path exists and that you have permission to use it."


class HydraulikError(Exception):
    """Base exception for all Hydraulik errors.

    Parameters
    ----------
    message : str, optional
        Human-readable description (English); becomes ``str(exc)``.
    code : ErrorCode or None, optional
        Registry code; ``None`` selects the class default (:attr:`default_code`).
    details : Mapping[str, object] or None, optional
        JSON-compatible context (``option``, ``value``, ``allowed``, ``path``,
        ``paths``); stored as an independent deep copy.
    hint : str or None, optional
        One-line remediation: the option to change, the command to run.
    reason : str or None, optional
        Project-specific sub-code in snake_case (ERR-1); stored as
        ``details["reason"]``.

    Attributes
    ----------
    default_code : ErrorCode
        Code used when the raise site does not pass ``code``.
    code : ErrorCode
        Registered code of this instance.
    details : dict
        Copy of the given context; empty when none was given.
    hint : str or None
        Remediation, if any.

    Raises
    ------
    ValueError
        If ``code`` is not an error code with an exit code in the registry.

    Examples
    --------
    >>> exc = InvalidInputError("dx_m must be positive", reason="out_of_range")
    >>> exc.code, exc.details
    ('validation_error', {'reason': 'out_of_range'})
    """

    default_code: ClassVar[ErrorCode] = "internal_error"

    code: ErrorCode
    details: dict[str, Any]
    hint: str | None

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode | None = None,
        details: Mapping[str, object] | None = None,
        hint: str | None = None,
        reason: str | None = None,
    ) -> None:
        resolved = self.default_code if code is None else code
        if resolved not in ERROR_CODES:
            raise ValueError(
                f"Unknown error code {resolved!r}; allowed: {', '.join(ERROR_CODES)}"
            )
        super().__init__(message)
        self.code = resolved
        self.details = copy.deepcopy(dict(details or {}))
        if reason is not None:
            self.details["reason"] = reason
        self.hint = hint

    @property
    def exit_code(self) -> int:
        """int: process exit code of this error's code (ERR §2)."""
        exit_code = ERROR_CODES[self.code].exit_code
        assert exit_code is not None  # ERROR_CODES keeps codes with an exit code
        return exit_code


class InvalidInputError(HydraulikError, ValueError):
    """An option or argument is unknown, mistyped, out of range or inconsistent.

    Default code: ``validation_error``.
    """

    default_code: ClassVar[ErrorCode] = "validation_error"


class NotFoundError(HydraulikError):
    """A referenced file, directory or command does not exist.

    Default code: ``not_found``.
    """

    default_code: ClassVar[ErrorCode] = "not_found"


class ConflictError(HydraulikError):
    """The operation conflicts with the current state (an output file exists).

    Default code: ``conflict``.
    """

    default_code: ClassVar[ErrorCode] = "conflict"


class SourceUnavailableError(HydraulikError):
    """A remote service or a data tool failed (timeout, download failure).

    Default code: ``source_unavailable``.
    """

    default_code: ClassVar[ErrorCode] = "source_unavailable"


class MissingDependencyError(HydraulikError):
    """An extra or an external program (an engine) is not installed.

    Default code: ``missing_dependency``; the hint names the install command.
    """

    default_code: ClassVar[ErrorCode] = "missing_dependency"


class InputDataError(HydraulikError):
    """Input data is unreadable or malformed (raster, table, model file).

    Default code: ``data_error``.
    """

    default_code: ClassVar[ErrorCode] = "data_error"


class OutputError(HydraulikError):
    """Reading or writing files failed (permissions, no space).

    Default code: ``io_error``.
    """

    default_code: ClassVar[ErrorCode] = "io_error"


class ForbiddenPathError(HydraulikError):
    """A path lies outside the allowed directories.

    Default code: ``forbidden``.
    """

    default_code: ClassVar[ErrorCode] = "forbidden"


class CalculationError(HydraulikError):
    """The input is valid but no result can be computed.

    Default code: ``calculation_error``.
    """

    default_code: ClassVar[ErrorCode] = "calculation_error"


class EngineError(CalculationError):
    """An engine run failed or its output does not hold what the run promised.

    Default code: ``calculation_error``, reason ``engine_failed`` unless the raise
    site gives another.
    """

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode | None = None,
        details: Mapping[str, object] | None = None,
        hint: str | None = None,
        reason: str | None = "engine_failed",
    ) -> None:
        super().__init__(message, code=code, details=details, hint=hint, reason=reason)


class CancelledError(HydraulikError):
    """The user cancelled the run (Ctrl+C, a declined plan).

    Default code: ``cancelled``.
    """

    default_code: ClassVar[ErrorCode] = "cancelled"


class TerminatedError(HydraulikError):
    """The process was terminated by SIGTERM (a container stop, a timeout).

    Default code: ``terminated``.
    """

    default_code: ClassVar[ErrorCode] = "terminated"


class NoDataError(HydraulikError):
    """The request is valid but the source has no data for it.

    Default code: ``no_data``.
    """

    default_code: ClassVar[ErrorCode] = "no_data"


class UnsupportedError(HydraulikError):
    """The request is valid but this combination is not supported.

    Default code: ``unsupported``.
    """

    default_code: ClassVar[ErrorCode] = "unsupported"


def _jsonable(value: object) -> Any:
    """Return a JSON-compatible copy of ``value``; unknown objects become ``str``."""
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((_jsonable(item) for item in value), key=str)
    return str(value)


def _os_error_parts(exc: OSError) -> tuple[ErrorCode, str, dict[str, Any]]:
    """Code, message and details of a file-system error that no operation wrapped."""
    filename = exc.filename
    path = (
        os.fsdecode(filename)
        if isinstance(filename, str | bytes | os.PathLike)
        else None
    )
    reason = exc.strerror or str(exc)
    details: dict[str, Any] = {}
    if exc.errno is not None:
        details["errno"] = errno.errorcode.get(exc.errno, str(exc.errno))
    if path is not None:
        details["path"] = path
    code: ErrorCode = "not_found" if isinstance(exc, FileNotFoundError) else "io_error"
    details["reason"] = "path_missing" if code == "not_found" else "os_error"
    return code, (f"{reason}: {path}" if path else reason), details


def error_document(
    exc: BaseException,
    command: str | None = None,
    lang: Literal["pl", "en"] = "en",
) -> dict[str, Any]:
    """Describe an exception as a ``hydraulik-error/1`` document.

    A :class:`HydraulikError` keeps its ``code``, ``hint`` and ``details``. A
    :class:`FileNotFoundError` becomes ``not_found`` and any other
    :class:`OSError` ``io_error``; :class:`KeyboardInterrupt` becomes
    ``cancelled``. Every other exception is a bug and becomes ``internal_error``
    with the exception class in ``details["exception"]``.

    Parameters
    ----------
    exc : BaseException
        The exception to describe.
    command : str or None, optional
        Catalog name of the failed command (``"model build"``), if known.
    lang : {"pl", "en"}, optional
        Language of ``title``; ``message`` and ``hint`` are always English
        (machine output is English, AGI-9.2).

    Returns
    -------
    dict
        ``{"schema": "hydraulik-error/1", "code", "title", "message", "hint",
        "details", "exit_code", "command"}``, JSON-compatible; ``hint`` and
        ``command`` are left out when there is none.

    Raises
    ------
    ValueError
        If ``lang`` is not ``"pl"`` or ``"en"``.

    Examples
    --------
    >>> doc = error_document(NotFoundError("No such command"), "x y", "en")
    >>> doc["code"], doc["title"], doc["exit_code"]
    ('not_found', 'Not found', 3)
    """
    if lang not in ("pl", "en"):
        raise ValueError(f"Unknown language {lang!r}; allowed: pl, en")
    details: Mapping[str, object]
    if isinstance(exc, HydraulikError):
        code: ErrorCode = exc.code
        message = str(exc)
        hint = exc.hint
        details = exc.details
    elif isinstance(exc, OSError):
        code, message, details = _os_error_parts(exc)
        hint = _IO_HINT
    elif isinstance(exc, KeyboardInterrupt):
        code, message, hint, details = "cancelled", "Cancelled by the user.", None, {}
    else:
        code = "internal_error"
        message = f"{type(exc).__name__}: {exc}"
        hint = _INTERNAL_HINT
        details = {"exception": type(exc).__name__}
    entry = BY_CODE[code]
    title = entry.title if lang == "en" else entry.title_pl
    document: dict[str, Any] = {
        "schema": ERROR_SCHEMA,
        "code": code,
        "title": title,
        "message": message or entry.title,
    }
    if hint:
        document["hint"] = hint
    document["details"] = _jsonable(details)
    document["exit_code"] = entry.exit_code
    if command is not None:
        document["command"] = command
    return document
