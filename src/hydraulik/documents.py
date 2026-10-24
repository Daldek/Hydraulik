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
    "EnginesDocument",
    "ExportDocument",
    "GuideDocument",
    "PlanDocument",
    "ResultsDocument",
    "RunDocument",
    "notice",
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


def notice(level: str, code: str, message: str) -> dict[str, str]:
    """Return a notice of the result envelope (AGI-4.2).

    Parameters
    ----------
    level : {"info", "warning"}
        How much attention it needs.
    code : str
        Short identifier in snake_case, for example ``balance_residual``.
    message : str
        One English sentence.

    Returns
    -------
    dict
        ``{"level", "code", "message"}``.

    Examples
    --------
    >>> notice("warning", "dem_gaps", "12 cells have no elevation")["level"]
    'warning'
    """
    return {"level": level, "code": code, "message": message}


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
    blockers : list of dict
        Reasons other than the output that would make the real run fail, each
        ``{"reason", "message"}`` and, when there is one, ``"hint"`` (an engine or an
        extra that is missing). Empty when the run would go ahead.
    """

    SCHEMA: ClassVar[str] = "hydraulik-plan/1"
    output_dir: str
    force: bool
    targets: list[dict[str, Any]]
    conflicts: list[str]
    steps: list[str] = field(default_factory=list)
    blockers: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_write_plan(
        cls,
        plan: Any,
        steps: list[str] | None = None,
        blockers: list[dict[str, str]] | None = None,
    ) -> PlanDocument:
        """Build the document from a :class:`hydraulik.output.WritePlan`."""
        body = plan.to_dict()
        return cls(
            output_dir=body["output_dir"],
            force=body["force"],
            targets=body["targets"],
            conflicts=body["conflicts"],
            steps=list(steps or []),
            blockers=list(blockers or []),
        )


@dataclass
class EnginesDocument(_Carrier, Document):
    """``hydraulik-engines/1``: what Hydraulik found on this machine.

    Attributes
    ----------
    engines : list of dict
        ``name`` (``sfincs``, ``sfincs-library``, ``swmm``, ``kartograf``), ``found``,
        ``via``, ``location``, ``version``, ``detail`` and ``hint`` of each program.
    extras : list of dict
        ``name`` (the Python package), ``extra`` (the extra of Hydraulik that installs
        it), ``found`` and ``version``.
    features : list of dict
        For each command that needs an engine or an extra: ``command``,
        ``available``, ``needs`` and ``missing``.
    """

    SCHEMA: ClassVar[str] = "hydraulik-engines/1"
    engines: list[dict[str, Any]]
    extras: list[dict[str, Any]]
    features: list[dict[str, Any]]


@dataclass
class ResultsDocument(_Carrier, Document):
    """``hydraulik-results/1``: what a SFINCS run computed.

    Attributes
    ----------
    source : str
        The ``sfincs_map.nc`` that was read.
    engine : dict
        ``build_revision``, ``status``, ``runtime_s`` and ``average_dt_s`` of the run.
    grid : dict
        ``epsg``, ``dx_m``, ``x0_m``, ``y0_m``, ``rows``, ``columns``,
        ``active_cells``, ``area_m2`` and ``huthresh_m``.
    depth : dict
        ``max_depth_m`` and its position, ``max_velocity_ms`` and the flooded area by
        depth threshold.
    balance : dict
        ``rain_m3``, ``infiltration_m3``, ``stored_m3``, ``residual_m3``,
        ``residual_percent``, ``open_boundary``, ``expected_rain_m3``, ``flags``.
    stations : list of dict
        ``name``, position, ``max_depth_m`` and ``time_of_max_s`` of each station.
    """

    SCHEMA: ClassVar[str] = "hydraulik-results/1"
    source: str
    engine: dict[str, Any]
    grid: dict[str, Any]
    depth: dict[str, Any]
    balance: dict[str, Any]
    stations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunDocument(_Carrier, Document):
    """``hydraulik-run/1``: one SFINCS run and what it computed.

    Attributes
    ----------
    engine : dict
        ``kind`` (``exe`` or ``docker``), ``location`` and ``version`` of the SFINCS
        that ran.
    elapsed_s : float
        Wall time of the run [s].
    results : dict
        The ``hydraulik-results/1`` document of the run.
    files : list of dict
        The files written: ``path``, ``size_bytes``, ``sha256``, ``status``.
    """

    SCHEMA: ClassVar[str] = "hydraulik-run/1"
    engine: dict[str, Any]
    elapsed_s: float
    results: dict[str, Any]
    files: list[dict[str, Any]]


@dataclass
class ExportDocument(_Carrier, Document):
    """``hydraulik-export/1``: a map or a table written from the results of a run.

    Attributes
    ----------
    variable : str
        What was exported (``max_depth``, ``max_velocity``, ``final_depth``,
        ``infiltration`` or ``stations``).
    format : str
        ``geotiff`` or ``csv``.
    source : str
        The result file it was made from.
    files : list of dict
        The file written: ``path``, ``size_bytes``, ``sha256``, ``status``.
    """

    SCHEMA: ClassVar[str] = "hydraulik-export/1"
    variable: str
    format: str
    source: str
    files: list[dict[str, Any]]
