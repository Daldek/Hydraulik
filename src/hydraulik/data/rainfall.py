"""Design rain from Hydrolog and IMGWTools, through their public interfaces only.

Hydraulik makes the rain table of a model (:mod:`hydraulik.data.tables`) from

* a **hyetograph shape** of Hydrolog: the classes ``BlockHietogram``,
  ``TriangularHietogram``, ``BetaHietogram`` and ``EulerIIHietogram`` of
  ``hydrolog.precipitation`` (the library), or the document that
  ``hydrolog precip hietogram --json`` prints (``hydrolog-precip-hietogram/1``, either
  the whole ``hydrolog-result/1`` envelope or its ``result``);
* a **depth** that is given, or the PMAXTP depth of IMGW-PIB for a duration and a
  probability, from ``imgwtools.fetch_pmaxtp`` (the library, needs the network) or from
  the document that ``imgw pmaxtp fetch --json`` prints (``imgw-result/1`` whose
  ``result`` is the PMAXTP result).

Nothing here reaches into the internals of either tool, and nothing is imported until a
function needs it, so the documents are read without Hydrolog or IMGWTools installed.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from hydraulik._optional import require
from hydraulik.data.tables import RainTable, rain_table_from_series
from hydraulik.exceptions import (
    CalculationError,
    InputDataError,
    InvalidInputError,
    NoDataError,
    NotFoundError,
    SourceUnavailableError,
)

__all__ = [
    "HIETOGRAM_TYPES",
    "PMAXTP_DURATIONS_MIN",
    "PMAXTP_METHODS",
    "PMAXTP_PROBABILITIES_PERCENT",
    "HyetographDocument",
    "Pmaxtp",
    "PmaxtpDepth",
    "fetch_pmaxtp",
    "generate_hyetograph",
    "pmaxtp_depth",
    "read_hietogram_document",
    "read_pmaxtp_document",
]

HIETOGRAM_TYPES: Final = ("block", "triangular", "beta", "euler_ii")
"""The shapes of Hydrolog, by the names of ``hydrolog precip hietogram``."""

PMAXTP_METHODS: Final = ("POT", "AMP")
"""The estimation methods of PMAXTP (peak over threshold, annual maxima)."""

PMAXTP_DURATIONS_MIN: Final = (15, 30, 45, 60, 90, 120, 180)
"""Durations that PMAXTP gives [min] (documented by ``imgwtools.fetch_pmaxtp``)."""

PMAXTP_PROBABILITIES_PERCENT: Final = (1, 2, 5, 10, 20, 50)
"""Probabilities of exceedance that PMAXTP gives [percent]."""

_SHAPE_PARAMETERS: Final = {
    "block": (),
    "triangular": ("peak_position",),
    "beta": ("alpha", "beta"),
    "euler_ii": ("peak_position",),
}

_CLASSES: Final = {
    "block": "BlockHietogram",
    "triangular": "TriangularHietogram",
    "beta": "BetaHietogram",
    "euler_ii": "EulerIIHietogram",
}


def generate_hyetograph(
    hietogram_type: str,
    total_mm: float,
    duration_min: float,
    timestep_min: float,
    *,
    alpha: float | None = None,
    beta: float | None = None,
    peak_position: float | None = None,
) -> RainTable:
    """Generate a design hyetograph with Hydrolog.

    Parameters
    ----------
    hietogram_type : {"block", "triangular", "beta", "euler_ii"}
        The shape.
    total_mm : float
        Total depth [mm], positive.
    duration_min : float
        Duration [min]. Hydrolog makes ``int(duration_min / timestep_min)`` steps, so
        a duration that is not a multiple of the step is shortened to the last whole
        step (the depth stays ``total_mm``).
    timestep_min : float
        Length of a step [min].
    alpha, beta : float or None, optional
        Shape of ``beta`` (Hydrolog defaults 2 and 5 when not given).
    peak_position : float or None, optional
        Position of the peak of ``triangular`` (default 0.5) and ``euler_ii``
        (default 0.33), between 0 and 1.

    Returns
    -------
    RainTable
        The depth of every step.

    Raises
    ------
    InvalidInputError
        If the shape is unknown, a parameter does not belong to the shape (reason
        ``option_not_applicable``) or Hydrolog refuses a value (reason
        ``out_of_range``).
    MissingDependencyError
        If Hydrolog is not installed (extra ``rainfall``).

    Examples
    --------
    >>> generate_hyetograph("block", 30.0, 60.0, 15.0).depth_mm
    (7.5, 7.5, 7.5, 7.5)
    """
    if hietogram_type not in HIETOGRAM_TYPES:
        raise InvalidInputError(
            f"unknown hyetograph type {hietogram_type!r}",
            details={
                "option": "hietogram_type",
                "value": hietogram_type,
                "allowed": list(HIETOGRAM_TYPES),
            },
            reason="not_allowed",
        )
    given = {"alpha": alpha, "beta": beta, "peak_position": peak_position}
    for name, value in given.items():
        if value is not None and name not in _SHAPE_PARAMETERS[hietogram_type]:
            raise InvalidInputError(
                f"--{name.replace('_', '-')} does not apply to the {hietogram_type} "
                "hyetograph",
                details={"option": name},
                hint=(
                    "alpha and beta belong to beta, peak_position to triangular and "
                    "euler_ii."
                ),
                reason="option_not_applicable",
            )
    hydrolog = require("hydrolog", "rainfall")
    precipitation = require("hydrolog.precipitation", "rainfall")
    shape = getattr(precipitation, _CLASSES[hietogram_type])
    parameters = {k: v for k, v in given.items() if v is not None}
    try:
        result = shape(**parameters).generate(
            total_mm=total_mm, duration_min=duration_min, timestep_min=timestep_min
        )
    except hydrolog.InvalidParameterError as exc:
        raise InvalidInputError(
            str(exc),
            details={"tool": "hydrolog", "hietogram_type": hietogram_type},
            hint="Hydrolog refused the values; see `hydrolog precip hietogram`.",
            reason="out_of_range",
        ) from exc
    except hydrolog.HydrologError as exc:
        raise CalculationError(str(exc), reason="hydrolog_failed") from exc
    return rain_table_from_series(
        [float(t) for t in result.times_min],
        [float(d) for d in result.intensities_mm],
        name=f"the {hietogram_type} hyetograph of Hydrolog",
        reason="invalid_hietogram",
    )


def _document_body(document: object, name: str, reason: str) -> Mapping[str, Any]:
    """Return the domain part of a document: the envelope's ``result`` or itself."""
    if not isinstance(document, Mapping):
        raise InputDataError(
            f"{name}: not a JSON object",
            details={"path": name},
            reason=reason,
        )
    schema, result = document.get("schema"), document.get("result")
    if (
        isinstance(schema, str)
        and schema.endswith("-result/1")
        and isinstance(result, Mapping)
    ):
        return result
    return document


def _load_json(path: Path, reason: str) -> object:
    if not path.is_file():
        raise NotFoundError(
            f"document not found: {path}",
            details={"path": str(path)},
            reason="path_missing",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputDataError(
            f"{path.name}: not a JSON document ({exc})",
            details={"path": str(path)},
            hint="Give the output of the tool's --json option, saved to a file.",
            reason=reason,
        ) from exc


@dataclass(frozen=True)
class HyetographDocument:
    """A hyetograph read from a Hydrolog document.

    Attributes
    ----------
    table : RainTable
        The depth of every step.
    hietogram_type : str or None
        The shape the document says it has.
    parameters : dict
        The shape parameters the document lists.
    """

    table: RainTable
    hietogram_type: str | None
    parameters: dict[str, Any] = field(default_factory=dict)


def read_hietogram_document(path: str | os.PathLike[str]) -> HyetographDocument:
    """Read the hyetograph document ``hydrolog precip hietogram --json`` prints.

    Parameters
    ----------
    path : path-like
        A JSON file: the ``hydrolog-result/1`` envelope or its ``result``
        (``hydrolog-precip-hietogram/1``).

    Returns
    -------
    Hietogram
        The steps (``times_min`` and ``depths_mm`` of the document) and the shape.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If it is not JSON, lacks ``times_min`` or ``depths_mm``, or the steps are not
        a regular series from time zero (reason ``invalid_hietogram``).

    Examples
    --------
    >>> import json, pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     p = pathlib.Path(tmp) / "h.json"
    ...     _ = p.write_text(json.dumps({"times_min": [5, 10], "depths_mm": [1, 3]}))
    ...     read_hietogram_document(p).table.total_mm
    4.0
    """
    source = Path(path)
    body = _document_body(
        _load_json(source, "invalid_hietogram"), source.name, "invalid_hietogram"
    )
    times, depths = body.get("times_min"), body.get("depths_mm")
    if not isinstance(times, list) or not isinstance(depths, list):
        raise InputDataError(
            f"{source.name}: lacks times_min and depths_mm",
            details={"path": str(source)},
            hint="Give the result of `hydrolog precip hietogram --json`.",
            reason="invalid_hietogram",
        )
    try:
        table = rain_table_from_series(
            [float(t) for t in times],
            [float(d) for d in depths],
            name=source.name,
            details={"path": str(source)},
            reason="invalid_hietogram",
        )
    except (TypeError, ValueError) as exc:
        raise InputDataError(
            f"{source.name}: a time or a depth is not a number",
            details={"path": str(source)},
            reason="invalid_hietogram",
        ) from exc
    kind = body.get("hietogram_type")
    parameters = body.get("parameters")
    return HyetographDocument(
        table,
        kind if isinstance(kind, str) else None,
        dict(parameters) if isinstance(parameters, Mapping) else {},
    )


def _quantiles(table: object) -> dict[int, dict[float, float]]:
    """Return ``{duration: {probability: mm}}`` from the nested dicts of PMAXTP.

    The keys are text (``"15"`` and ``"50"``); a prefix such as ``t15`` or ``p50`` is
    tolerated. A probability keeps its fraction (``"0.5"`` is 0.5, not 5); a whole one
    is an ``int`` (``"50"`` is 50), so ``row.get(50)`` finds it.
    """
    found: dict[int, dict[float, float]] = {}
    if not isinstance(table, Mapping):
        return found
    for duration, row in table.items():
        if not isinstance(row, Mapping):
            continue
        digits = re.sub(r"\D", "", str(duration))
        if not digits:
            continue
        values: dict[float, float] = {}
        for probability, value in row.items():
            found_number = re.search(r"\d+(?:\.\d+)?", str(probability))
            if (
                found_number
                and isinstance(value, int | float)
                and not isinstance(value, bool)
            ):
                number = float(found_number.group())
                values[int(number) if number.is_integer() else number] = float(value)
        found[int(digits)] = values
    return found


@dataclass(frozen=True)
class Pmaxtp:
    """The PMAXTP result of one point.

    Attributes
    ----------
    method : str or None
        ``POT`` or ``AMP``.
    latitude, longitude : float or None
        The point [degrees].
    quantiles_mm : dict
        ``{duration_min: {probability_percent: depth_mm}}`` (``ks``).
    upper_bound_mm, error_mm : dict
        The same layout for the upper confidence bound (``sg``) and the estimation
        error (``rb``).
    """

    method: str | None
    latitude: float | None
    longitude: float | None
    quantiles_mm: dict[int, dict[float, float]]
    upper_bound_mm: dict[int, dict[float, float]] = field(default_factory=dict)
    error_mm: dict[int, dict[float, float]] = field(default_factory=dict)


def _pmaxtp_from(body: Mapping[str, Any], name: str, details: dict[str, Any]) -> Pmaxtp:
    data = body.get("data")
    if not isinstance(data, Mapping) or not _quantiles(data.get("ks")):
        raise InputDataError(
            f"{name}: no PMAXTP quantiles (data.ks)",
            details=details,
            hint="Give the result of `imgw pmaxtp fetch --json`.",
            reason="invalid_pmaxtp",
        )

    def number(key: str) -> float | None:
        value = body.get(key)
        return float(value) if isinstance(value, int | float) else None

    method = body.get("method")
    return Pmaxtp(
        method if isinstance(method, str) else None,
        number("latitude"),
        number("longitude"),
        _quantiles(data.get("ks")),
        _quantiles(data.get("sg")),
        _quantiles(data.get("rb")),
    )


def read_pmaxtp_document(path: str | os.PathLike[str]) -> Pmaxtp:
    """Read the PMAXTP document ``imgw pmaxtp fetch --json`` prints.

    Parameters
    ----------
    path : path-like
        A JSON file: the ``imgw-result/1`` envelope or its ``result``
        (``method``, ``latitude``, ``longitude`` and ``data`` with ``ks``).

    Returns
    -------
    Pmaxtp
        The quantiles by duration and probability.

    Raises
    ------
    NotFoundError
        If the file does not exist.
    InputDataError
        If it is not JSON or has no quantiles (reason ``invalid_pmaxtp``).
    """
    source = Path(path)
    body = _document_body(
        _load_json(source, "invalid_pmaxtp"), source.name, "invalid_pmaxtp"
    )
    return _pmaxtp_from(body, source.name, {"path": str(source)})


def fetch_pmaxtp(latitude: float, longitude: float, method: str = "POT") -> Pmaxtp:
    """Fetch the PMAXTP quantiles of a point with ``imgwtools.fetch_pmaxtp``.

    Parameters
    ----------
    latitude, longitude : float
        The point [degrees], in Poland.
    method : {"POT", "AMP"}, optional
        The estimation method; ``POT`` is the one IMGWTools recommends.

    Returns
    -------
    Pmaxtp
        The quantiles of the point.

    Raises
    ------
    MissingDependencyError
        If IMGWTools is not installed (extra ``rainfall``).
    InvalidInputError
        If the point is outside Poland (reason ``out_of_range``).
    SourceUnavailableError
        If IMGW-PIB does not answer (reason ``source_unreachable``).
    InputDataError
        If its answer cannot be read (reason ``source_data``).
    """
    imgwtools = require("imgwtools", "rainfall")
    try:
        result = imgwtools.fetch_pmaxtp(latitude, longitude, method=method)
    except imgwtools.IMGWValidationError as exc:
        raise InvalidInputError(
            str(exc),
            details={"option": "latitude", "value": latitude},
            hint="PMAXTP covers Poland: latitude 49 to 55, longitude 14 to 24.5.",
            reason="out_of_range",
        ) from exc
    except imgwtools.IMGWConnectionError as exc:
        raise SourceUnavailableError(
            f"IMGW-PIB did not answer the PMAXTP request: {exc}",
            details={"source": "imgw-pmaxtp"},
            hint="Check the network, or give the depth with --total-mm or --pmaxtp.",
            reason="source_unreachable",
        ) from exc
    except imgwtools.IMGWError as exc:
        raise InputDataError(
            f"the PMAXTP answer could not be read: {exc}",
            details={"source": "imgw-pmaxtp"},
            reason="source_data",
        ) from exc
    body = {
        "method": result.method,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "data": {
            "ks": result.data.ks,
            "sg": result.data.sg,
            "rb": result.data.rb,
        },
    }
    return _pmaxtp_from(body, "the PMAXTP answer", {"source": "imgw-pmaxtp"})


@dataclass(frozen=True)
class PmaxtpDepth:
    """One depth of a PMAXTP result.

    Attributes
    ----------
    depth_mm : float
        The quantile for the duration and the probability [mm].
    duration_min : int
        The duration [min].
    probability_percent : int
        The probability of exceedance [percent].
    upper_bound_mm, error_mm : float or None
        The upper confidence bound and the estimation error, when the result has them.
    """

    depth_mm: float
    duration_min: int
    probability_percent: int
    upper_bound_mm: float | None
    error_mm: float | None


def pmaxtp_depth(
    pmaxtp: Pmaxtp, duration_min: float, probability_percent: int
) -> PmaxtpDepth:
    """Pick the depth of a duration and a probability.

    Parameters
    ----------
    pmaxtp : Pmaxtp
        The result of a point.
    duration_min : float
        A duration PMAXTP gives [min] (a whole number).
    probability_percent : int
        A probability of exceedance PMAXTP gives [percent].

    Returns
    -------
    PmaxtpDepth
        The depth and its bounds.

    Raises
    ------
    NoDataError
        If the result has no value for the pair (reason ``pmaxtp_no_data``); the error
        lists the durations and probabilities it has.

    Examples
    --------
    >>> p = Pmaxtp("POT", 52.0, 21.0, {60: {1: 55.0, 50: 25.0}})
    >>> pmaxtp_depth(p, 60, 1).depth_mm
    55.0
    """
    duration = int(duration_min) if float(duration_min).is_integer() else None
    row = pmaxtp.quantiles_mm.get(duration, {}) if duration is not None else {}
    value = row.get(probability_percent)
    if duration is None or value is None:
        probabilities = sorted({p for r in pmaxtp.quantiles_mm.values() for p in r})
        raise NoDataError(
            f"PMAXTP has no depth for {duration_min:g} min at {probability_percent} %",
            details={
                "durations_min": sorted(pmaxtp.quantiles_mm),
                "probabilities_percent": probabilities,
            },
            hint=(
                "Choose one of the durations and probabilities listed in "
                "details; they are those of PMAXTP."
            ),
            reason="pmaxtp_no_data",
        )
    return PmaxtpDepth(
        value,
        duration,
        probability_percent,
        pmaxtp.upper_bound_mm.get(duration, {}).get(probability_percent),
        pmaxtp.error_mm.get(duration, {}).get(probability_percent),
    )
