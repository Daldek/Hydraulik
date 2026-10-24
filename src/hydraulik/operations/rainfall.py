"""``rainfall build``: a design rain as the rain table that ``model build`` reads."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hydraulik.data.rainfall import (
    HIETOGRAM_TYPES,
    PMAXTP_DURATIONS_MIN,
    PMAXTP_METHODS,
    PMAXTP_PROBABILITIES_PERCENT,
    Pmaxtp,
    PmaxtpDepth,
    fetch_pmaxtp,
    generate_hyetograph,
    pmaxtp_depth,
    read_hietogram_document,
    read_pmaxtp_document,
)
from hydraulik.data.tables import RainTable, render_rain_table
from hydraulik.documents import PlanDocument, RainDocument, notice
from hydraulik.exceptions import InvalidInputError
from hydraulik.operations._support import (
    extra_blocker,
    extra_version,
    file_dicts,
    missing_extras,
    require_extras,
)
from hydraulik.output import Writer, plan_file

__all__ = ["build_rainfall"]

DEFAULT_TIMESTEP_MIN: Final = 5.0
"""Length of a step when ``timestep_min`` is not given [min]; Hydrolog's default."""

IMGW_TERMS_URL: Final = "https://danepubliczne.imgw.pl/regulations"

_DESIGN_ONLY: Final = (
    "hietogram_type",
    "total_mm",
    "pmaxtp",
    "latitude",
    "longitude",
    "method",
    "probability_percent",
    "duration_min",
    "timestep_min",
    "alpha",
    "beta",
    "peak_position",
)


def _flag(option: str) -> str:
    return "--" + option.replace("_", "-")


def _refuse(
    option: str, why: str, reason: str, hint: str | None = None
) -> InvalidInputError:
    return InvalidInputError(
        f"{_flag(option)}: {why}",
        details={"option": option},
        hint=hint,
        reason=reason,
    )


def _missing(option: str, hint: str) -> InvalidInputError:
    return _refuse(option, "is required here", "missing_option", hint)


@dataclass(frozen=True)
class _Design:
    """A rain that Hydrolog generates, with the way its depth is found."""

    hietogram_type: str
    duration_min: float
    timestep_min: float
    total_mm: float | None
    pmaxtp_path: Path | None
    point: tuple[float, float, str] | None
    probability_percent: int | None
    parameters: dict[str, float]


def _design(
    *,
    hietogram_type: str,
    total_mm: float | None,
    pmaxtp: str | os.PathLike[str] | None,
    latitude: float | None,
    longitude: float | None,
    method: str | None,
    probability_percent: int | None,
    duration_min: float | None,
    timestep_min: float | None,
    alpha: float | None,
    beta: float | None,
    peak_position: float | None,
) -> _Design:
    """Check the options of a generated rain against each other."""
    sources = [
        name
        for name, value in (
            ("total_mm", total_mm),
            ("pmaxtp", pmaxtp),
            ("latitude", latitude),
        )
        if value is not None
    ]
    if not sources:
        raise _missing(
            "total_mm",
            "Give the depth: --total-mm, a PMAXTP document (--pmaxtp) or a point "
            "(--latitude and --longitude).",
        )
    if len(sources) > 1:
        raise _refuse(
            sources[1],
            f"excludes {_flag(sources[0])}: the depth has one source",
            "exclusive_options",
            "Give --total-mm, --pmaxtp or --latitude with --longitude.",
        )
    if (latitude is None) != (longitude is None):
        raise _missing(
            "longitude" if longitude is None else "latitude",
            "--latitude and --longitude name one point.",
        )
    if duration_min is None:
        raise _missing("duration_min", "Give the length of the rain in minutes.")
    if total_mm is not None:
        if probability_percent is not None:
            raise _refuse(
                "probability_percent",
                "belongs to a PMAXTP depth, not to --total-mm",
                "option_not_applicable",
            )
    elif probability_percent is None:
        raise _missing(
            "probability_percent",
            "Give the probability of exceedance of the PMAXTP depth, one of "
            f"{', '.join(str(p) for p in PMAXTP_PROBABILITIES_PERCENT)} [percent].",
        )
    if method is not None and latitude is None:
        raise _refuse(
            "method",
            "applies to a point; a PMAXTP document says which method it holds",
            "option_not_applicable",
        )
    if method is not None and method not in PMAXTP_METHODS:
        raise InvalidInputError(
            f"{_flag('method')}: must be one of {', '.join(PMAXTP_METHODS)}",
            details={
                "option": "method",
                "value": method,
                "allowed": list(PMAXTP_METHODS),
            },
            reason="not_allowed",
        )
    if latitude is not None:
        if float(duration_min) not in {float(d) for d in PMAXTP_DURATIONS_MIN}:
            raise InvalidInputError(
                f"PMAXTP has no duration of {duration_min:g} min",
                details={
                    "option": "duration_min",
                    "value": duration_min,
                    "allowed": list(PMAXTP_DURATIONS_MIN),
                },
                reason="not_allowed",
            )
        if probability_percent not in PMAXTP_PROBABILITIES_PERCENT:
            raise InvalidInputError(
                f"PMAXTP has no probability of {probability_percent} %",
                details={
                    "option": "probability_percent",
                    "value": probability_percent,
                    "allowed": list(PMAXTP_PROBABILITIES_PERCENT),
                },
                reason="not_allowed",
            )
    parameters = {
        name: value
        for name, value in (
            ("alpha", alpha),
            ("beta", beta),
            ("peak_position", peak_position),
        )
        if value is not None
    }
    return _Design(
        hietogram_type,
        float(duration_min),
        DEFAULT_TIMESTEP_MIN if timestep_min is None else float(timestep_min),
        total_mm,
        None if pmaxtp is None else Path(pmaxtp),
        None
        if latitude is None or longitude is None
        else (latitude, longitude, method or "POT"),
        probability_percent,
        parameters,
    )


def _depth_block(
    design: _Design, pmaxtp: Pmaxtp | None, depth: PmaxtpDepth | None
) -> dict[str, Any]:
    if depth is None or pmaxtp is None:
        assert design.total_mm is not None
        return {"source": "given", "value_mm": design.total_mm}
    block: dict[str, Any] = {
        "source": "pmaxtp",
        "via": "document" if design.pmaxtp_path is not None else "library",
        "value_mm": depth.depth_mm,
        "duration_min": depth.duration_min,
        "probability_percent": depth.probability_percent,
        "method": pmaxtp.method,
        "latitude": pmaxtp.latitude,
        "longitude": pmaxtp.longitude,
        "upper_bound_mm": depth.upper_bound_mm,
        "error_mm": depth.error_mm,
    }
    if design.pmaxtp_path is not None:
        block["path"] = str(design.pmaxtp_path)
    return block


def build_rainfall(
    *,
    hietogram_type: str | None = None,
    hietogram: str | os.PathLike[str] | None = None,
    total_mm: float | None = None,
    pmaxtp: str | os.PathLike[str] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    method: str | None = None,
    probability_percent: int | None = None,
    duration_min: float | None = None,
    timestep_min: float | None = None,
    alpha: float | None = None,
    beta: float | None = None,
    peak_position: float | None = None,
    output: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> RainDocument | PlanDocument:
    """Write a design rain as a rain table (``time_min``, ``depth_mm``).

    Two ways to a rain table. **Design**: a Hydrolog hyetograph shape
    (``hietogram_type``) with a depth that is given (``total_mm``), or the PMAXTP depth
    of IMGW-PIB for ``duration_min`` and ``probability_percent``, read from a document
    of ``imgw pmaxtp fetch --json`` (``pmaxtp``) or fetched for a point with IMGWTools
    (``latitude`` and ``longitude``, needs the network). **Document**: the result of
    ``hydrolog precip hietogram --json`` (``hietogram``), converted as it is.

    Parameters
    ----------
    hietogram_type : {"block", "triangular", "beta", "euler_ii"} or None, optional
        The shape, as in ``hydrolog precip hietogram``. Exactly one of
        ``hietogram_type`` and ``hietogram``.
    hietogram : path-like or None, optional
        A Hydrolog hyetograph document. It carries its own depth, duration and step, so
        no design option may be given with it.
    total_mm : float or None, optional
        Depth of the rain [mm]. One of ``total_mm``, ``pmaxtp`` and ``latitude``.
    pmaxtp : path-like or None, optional
        A PMAXTP document of IMGWTools (``imgw-result/1`` or its ``result``).
    latitude, longitude : float or None, optional
        A point in Poland [degrees]; PMAXTP is fetched from IMGW-PIB.
    method : {"POT", "AMP"} or None, optional
        PMAXTP method for a point; ``POT`` when not given.
    probability_percent : int or None, optional
        Probability of exceedance of the PMAXTP depth [percent]: 1, 2, 5, 10, 20, 50.
    duration_min : float or None, optional
        Length of the rain [min]; required for a design. For PMAXTP one of 15, 30, 45,
        60, 90, 120, 180.
    timestep_min : float or None, optional
        Length of a step [min]; 5 when not given.
    alpha, beta : float or None, optional
        Shape of the ``beta`` hyetograph.
    peak_position : float or None, optional
        Position of the peak of ``triangular`` and ``euler_ii``, between 0 and 1.
    output : path-like
        The rain table to write (exactly one file).
    force : bool, optional
        Replace the file when it exists.
    check : bool, optional
        Plan without effects and without the network call.

    Returns
    -------
    RainDocument or PlanDocument
        ``hydraulik-rain/1`` (the notices carry the IMGW-PIB attribution and a duration
        that was shortened to whole steps), or the ``hydraulik-plan/1`` of ``check``.

    Raises
    ------
    InvalidInputError
        If the combination of options is wrong (reasons ``missing_option``,
        ``exclusive_options``, ``option_not_applicable``), a value is not allowed, or
        Hydrolog or IMGWTools refuse it (``out_of_range``).
    NotFoundError, InputDataError
        If a document is missing or malformed (``invalid_hietogram``,
        ``invalid_pmaxtp``).
    NoDataError
        If PMAXTP has no depth for the duration and the probability.
    SourceUnavailableError
        If IMGW-PIB does not answer (reason ``source_unreachable``).
    MissingDependencyError
        If Hydrolog or IMGWTools is not installed (extra ``rainfall``).
    ConflictError
        If ``output`` exists without ``force`` or lies inside a store.

    Examples
    --------
    >>> build_rainfall(output="rain.csv")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.InvalidInputError: --hietogram-type: is required here
    """
    given = {
        "hietogram_type": hietogram_type,
        "total_mm": total_mm,
        "pmaxtp": pmaxtp,
        "latitude": latitude,
        "longitude": longitude,
        "method": method,
        "probability_percent": probability_percent,
        "duration_min": duration_min,
        "timestep_min": timestep_min,
        "alpha": alpha,
        "beta": beta,
        "peak_position": peak_position,
    }
    if hietogram is not None:
        for name in _DESIGN_ONLY:
            if given[name] is not None:
                raise _refuse(
                    name,
                    "does not apply to a rain read from a hyetograph document",
                    "option_not_applicable",
                    "The document carries its depth, duration and step.",
                )
    elif hietogram_type is None:
        raise _missing(
            "hietogram_type",
            "Give the shape (block, triangular, beta, euler_ii) or a Hydrolog "
            "document with --hietogram.",
        )
    elif hietogram_type not in HIETOGRAM_TYPES:
        raise InvalidInputError(
            f"{_flag('hietogram_type')}: must be one of {', '.join(HIETOGRAM_TYPES)}",
            details={
                "option": "hietogram_type",
                "value": hietogram_type,
                "allowed": list(HIETOGRAM_TYPES),
            },
            reason="not_allowed",
        )
    plan = plan_file(output, force=force)
    name = Path(output).name
    document = None if hietogram is None else read_hietogram_document(hietogram)
    design = (
        None
        if hietogram is not None or hietogram_type is None
        else _design(
            hietogram_type=hietogram_type,
            total_mm=total_mm,
            pmaxtp=pmaxtp,
            latitude=latitude,
            longitude=longitude,
            method=method,
            probability_percent=probability_percent,
            duration_min=duration_min,
            timestep_min=timestep_min,
            alpha=alpha,
            beta=beta,
            peak_position=peak_position,
        )
    )
    packages: list[str] = []
    document_pmaxtp: Pmaxtp | None = None
    document_depth: PmaxtpDepth | None = None
    if design is not None:
        packages.append("hydrolog")
        if design.point is not None:
            packages.append("imgwtools")
        if design.pmaxtp_path is not None and design.probability_percent is not None:
            document_pmaxtp = read_pmaxtp_document(design.pmaxtp_path)
            document_depth = pmaxtp_depth(
                document_pmaxtp, design.duration_min, design.probability_percent
            )
    if check:
        if document is not None:
            steps = [
                f"read the hyetograph {document.table.total_mm:.1f} mm in "
                f"{len(document.table.depth_mm)} steps of "
                f"{document.table.step_min:g} min from {hietogram}"
            ]
        else:
            assert design is not None
            if document_depth is not None:
                found = f"the PMAXTP depth {document_depth.depth_mm:.1f} mm"
            elif design.point is not None:
                lat, lon, how = design.point
                found = (
                    f"the PMAXTP depth ({how}) fetched for {lat:g}, {lon:g} from "
                    f"IMGW-PIB (network)"
                )
            else:
                found = f"{design.total_mm:g} mm"
            steps = [
                f"generate a {design.hietogram_type} hyetograph of {found} over "
                f"{design.duration_min:g} min in steps of {design.timestep_min:g} min "
                f"with Hydrolog {extra_version('hydrolog') or '(not installed)'}"
            ]
        steps.append(f"write the rain table {name} to {plan.directory}")
        return PlanDocument.from_write_plan(
            plan,
            steps=steps,
            blockers=[extra_blocker(item) for item in missing_extras(packages)],
        )
    require_extras(*packages)
    pmaxtp_result, depth = document_pmaxtp, document_depth
    if design is not None:
        if design.point is not None:
            assert design.probability_percent is not None
            pmaxtp_result = fetch_pmaxtp(*design.point)
            depth = pmaxtp_depth(
                pmaxtp_result, design.duration_min, design.probability_percent
            )
        total = depth.depth_mm if depth is not None else design.total_mm
        assert total is not None
        table = generate_hyetograph(
            design.hietogram_type,
            total,
            design.duration_min,
            design.timestep_min,
            **design.parameters,
        )
        kind: str | None = design.hietogram_type
        parameters: dict[str, Any] = dict(design.parameters)
        depth_block: dict[str, Any] | None = _depth_block(design, pmaxtp_result, depth)
    else:
        assert document is not None
        table = document.table
        kind, parameters, depth_block = (
            document.hietogram_type,
            document.parameters,
            None,
        )
    with Writer(plan) as writer:
        writer.staged_path(name).write_text(
            render_rain_table(table.step_min, table.depth_mm), encoding="utf-8"
        )
        records = writer.commit()
    result = RainDocument(
        source="design" if design is not None else "hietogram",
        hietogram_type=kind,
        parameters=parameters,
        total_mm=round(table.total_mm, 6),
        duration_min=table.duration_min,
        timestep_min=table.step_min,
        n_steps=len(table.depth_mm),
        peak_intensity_mm_h=round(table.peak_intensity_mm_h, 4),
        depth=depth_block,
        files=file_dicts(records),
    )
    result.notices.extend(_notices(design, depth, table))
    return result


def _notices(
    design: _Design | None, depth: PmaxtpDepth | None, table: RainTable
) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if design is not None and not math.isclose(
        table.duration_min, design.duration_min, rel_tol=1e-9
    ):
        found.append(
            notice(
                "warning",
                "duration_truncated",
                f"{design.duration_min:g} min is not a multiple of the step "
                f"{design.timestep_min:g} min: the rain lasts {table.duration_min:g} "
                f"min, with the whole depth of {table.total_mm:.1f} mm",
            )
        )
    if depth is not None:
        found.append(
            notice(
                "info",
                "pmaxtp_attribution",
                "the depth is a PMAXTP quantile of IMGW-PIB: name IMGW-PIB as its "
                f"source; see {IMGW_TERMS_URL}",
            )
        )
    return found
