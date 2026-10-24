"""Typed result documents of Hydraulik (AGI-4.1, AGI-4.4).

Every machine-readable document has a top-level ``schema`` of the form
``hydraulik-<kind>/<n>``. A library function returns a :class:`Document`; its
:meth:`Document.to_dict` is identical to what the CLI prints as ``result`` in the
envelope. Adding an optional field keeps ``<n>``; removing a field or changing its
meaning increments it (AGI-4.1). The JSON Schemas are in ``hydraulik/schemas/``.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePath
from typing import Any, ClassVar

__all__ = [
    "CommandsDocument",
    "ConfigDocument",
    "Document",
    "GuideDocument",
    "PlanDocument",
    "to_jsonable",
]


def to_jsonable(value: object) -> Any:
    """Return a JSON-compatible copy of ``value``.

    Dataclasses become dictionaries, paths become strings, enums their value, tuples
    and sets lists; unknown objects become their ``str``.

    Parameters
    ----------
    value : object
        Value to convert.

    Returns
    -------
    object
        ``None``, ``bool``, ``int``, ``float``, ``str``, ``list`` or ``dict``.

    Examples
    --------
    >>> to_jsonable({"path": PurePath("a/b"), "ids": (1, 2)})["ids"]
    [1, 2]
    """
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, Document):
        return value.to_dict()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((to_jsonable(item) for item in value), key=str)
    return str(value)


class Document:
    """Base class of the result documents.

    A subclass is a dataclass with a class attribute ``SCHEMA``
    (``hydraulik-<kind>/<n>``); its fields are the keys of the document.
    """

    SCHEMA: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        """Return the document as a JSON-compatible dictionary, ``schema`` first.

        Returns
        -------
        dict
            The same dictionary the CLI prints as ``result`` (AGI-4.4).
        """
        body: dict[str, Any] = {"schema": self.SCHEMA}
        if dataclasses.is_dataclass(self):
            for field in dataclasses.fields(self):
                body[field.name] = to_jsonable(getattr(self, field.name))
        return body

    def to_json(self, indent: int | None = 2) -> str:
        """Return the document as JSON text.

        Parameters
        ----------
        indent : int or None, optional
            Indentation; ``None`` gives one compact line.

        Returns
        -------
        str
            JSON with non-ASCII characters kept.
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class _Carrier:
    """Mixin for the envelope parts a document carries besides its own keys."""

    def __post_init__(self) -> None:
        self.notices: list[dict[str, str]] = []
        self.items: list[dict[str, Any]] = []
        self.status = "ok"


@dataclass
class CommandsDocument(_Carrier, Document):
    """``hydraulik-commands/1``: the command catalog or one entry of it.

    Attributes
    ----------
    tool : str
        ``hydraulik``.
    version : str
        Package version.
    commands : list of dict
        Command declarations as in the vendored ``commands-1`` schema.
    """

    SCHEMA: ClassVar[str] = "hydraulik-commands/1"
    tool: str
    version: str
    commands: list[dict[str, Any]]


@dataclass
class ConfigDocument(_Carrier, Document):
    """``hydraulik-config/1``: the settings with their sources (DEV-18.6).

    Attributes
    ----------
    config_file : dict
        ``path``, ``source`` and ``exists`` of the settings file looked for.
    settings : list of dict
        ``key``, ``value``, ``source``, ``env`` and ``description`` of each setting.
    credentials : list
        Credentials the tool reads; always empty for Hydraulik.
    store : dict or None
        The store root; always ``None`` for Hydraulik (ADR-0001).
    """

    SCHEMA: ClassVar[str] = "hydraulik-config/1"
    config_file: dict[str, Any]
    settings: list[dict[str, Any]]
    credentials: list[dict[str, Any]] = field(default_factory=list)
    store: dict[str, Any] | None = None


@dataclass
class GuideDocument(_Carrier, Document):
    """``hydraulik-guide/1``: a rendered agent guide.

    Attributes
    ----------
    format : str
        ``agents``, ``llms`` or ``agents-md-block``.
    text : str
        The rendered text.
    injected_into : str or None
        File whose block was replaced (or would be, with ``--check``).
    changed : bool
        Whether that file changed (or would change).
    """

    SCHEMA: ClassVar[str] = "hydraulik-guide/1"
    format: str
    text: str
    injected_into: str | None = None
    changed: bool = False


@dataclass
class PlanDocument(_Carrier, Document):
    """``hydraulik-plan/1``: the plan of ``--check`` without effects (DEV-19.10).

    Attributes
    ----------
    output_dir : str
        Directory the files would go into.
    force : bool
        Whether existing files would be replaced.
    targets : list of dict
        ``name``, ``path``, ``action`` (``write``, ``replace`` or ``conflict``) and,
        for a conflict, ``reason``.
    conflicts : list of str
        Reasons that would make the real run fail; empty when it would succeed.
    steps : list of str
        What else the real run would do (for example the engine run).
    """

    SCHEMA: ClassVar[str] = "hydraulik-plan/1"
    output_dir: str
    force: bool
    targets: list[dict[str, Any]]
    conflicts: list[str]
    steps: list[str] = field(default_factory=list)

    @classmethod
    def from_write_plan(cls, plan: Any, steps: list[str] | None = None) -> PlanDocument:
        """Build the document from a :class:`hydraulik.output.WritePlan`."""
        body = plan.to_dict()
        return cls(
            output_dir=body["output_dir"],
            force=body["force"],
            targets=body["targets"],
            conflicts=body["conflicts"],
            steps=list(steps or []),
        )
