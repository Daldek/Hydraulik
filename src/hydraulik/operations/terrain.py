"""``terrain download``: terrain, land cover and soil groups of an area (Kartograf)."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from hydraulik.data.kartograf import (
    PRODUCTS,
    RECIPES,
    KartografCli,
    KartografRun,
    Recipe,
)
from hydraulik.documents import PlanDocument, TerrainDocument, notice
from hydraulik.engines.detect import EngineStatus, find_kartograf
from hydraulik.exceptions import (
    CancelledError,
    ConflictError,
    HydraulikError,
    MissingDependencyError,
    NotFoundError,
    TerminatedError,
)
from hydraulik.operations._support import blocker, refuse_option
from hydraulik.output import WritePlan, plan_directory, sigterm_as_error
from hydraulik.settings import load_settings

__all__ = ["download_terrain"]

logger = logging.getLogger(__name__)

_REASONS: Final = ("output_in_store", "duplicate_output_name", "output_exists")
"""The reasons of a conflict, in the order DEV-19.6 and DEV-19.11 check them."""


@dataclass(frozen=True)
class _Area:
    """The area of the request, as Kartograf's options and as a document."""

    options: dict[str, Any]
    document: dict[str, Any]
    crs: str | None


def _area(
    bbox: Sequence[float] | None,
    crs: str | None,
    geometry: str | os.PathLike[str] | None,
    layer: str | None,
) -> _Area:
    """Check the options that describe the area and return them for Kartograf."""
    if bbox is not None and geometry is not None:
        raise refuse_option(
            "geometry",
            "an area is --bbox or --geometry, not both",
            "exclusive_options",
            "Give the rectangle or the polygon of the area.",
        )
    if bbox is None and geometry is None:
        raise refuse_option(
            "bbox",
            "an area is required: --bbox with --crs, or --geometry",
            "missing_option",
            "Give the rectangle (min_x,min_y,max_x,max_y) or a vector file.",
        )
    if bbox is not None:
        if len(bbox) != 4:
            raise refuse_option(
                "bbox",
                f"four numbers are required (min_x,min_y,max_x,max_y), got {len(bbox)}",
                "invalid_bbox",
            )
        min_x, min_y, max_x, max_y = (float(item) for item in bbox)
        if not (min_x < max_x and min_y < max_y):
            raise refuse_option(
                "bbox",
                "each minimum must be below its maximum (min_x,min_y,max_x,max_y)",
                "invalid_bbox",
            )
        if crs is None:
            raise refuse_option(
                "crs",
                "--bbox needs the CRS its numbers are in",
                "missing_option",
                "Give --crs, for example EPSG:2180 or EPSG:4326 (x is east or "
                "longitude).",
            )
        if layer is not None:
            raise refuse_option(
                "layer",
                "--layer names a layer of --geometry, which was not given",
                "option_not_applicable",
            )
        numbers = [min_x, min_y, max_x, max_y]
        return _Area(
            {"bbox": numbers, "bbox_crs": crs},
            {"source": "bbox", "bbox": numbers, "crs": crs},
            crs,
        )
    assert geometry is not None
    if crs is not None:
        raise refuse_option(
            "crs",
            "--crs describes --bbox, which was not given",
            "option_not_applicable",
        )
    path = Path(geometry).expanduser().resolve()
    if not path.is_file():
        raise NotFoundError(
            f"vector file not found: {path}",
            details={"path": str(path)},
            reason="path_missing",
        )
    return _Area(
        {"geometry": str(path), "layer": layer},
        {"source": "geometry", "path": str(path), "layer": layer},
        None,
    )


def _chosen(products: Sequence[str] | None) -> tuple[str, ...]:
    """Return the products to fetch in the order they are fetched."""
    if products is None:
        return PRODUCTS
    unknown = [name for name in products if name not in RECIPES]
    if unknown:
        error = refuse_option(
            "products",
            f"unknown product {unknown[0]!r}",
            "not_allowed",
            f"Choose from: {', '.join(PRODUCTS)}.",
        )
        error.details["allowed"] = list(PRODUCTS)
        raise error
    if not products:
        raise refuse_option(
            "products", "at least one product is required", "missing_option"
        )
    return tuple(name for name in PRODUCTS if name in products)


def _options(
    recipe: Recipe, area: _Area, directory: Path, force: bool
) -> dict[str, Any]:
    """Return the options of the Kartograf call that fetches one product."""
    return {
        **recipe.options,
        **area.options,
        "output_dir": str(directory),
        "force": True if force else None,
    }


def _check_crs(cli: KartografCli, names: Sequence[str], area: _Area) -> None:
    """Refuse a rectangle in a CRS that the installed Kartograf does not take."""
    if area.crs is None:
        return
    for name in names:
        option = cli.schema(RECIPES[name].command).options.get("bbox_crs")
        if option is not None and option.allowed and area.crs not in option.allowed:
            raise refuse_option(
                "crs",
                f"Kartograf takes {', '.join(option.allowed)} for the CRS of a "
                f"rectangle, not {area.crs}",
                "not_allowed",
                "Give the rectangle in one of those CRS, or give --geometry, a file "
                "in any CRS.",
            )


def _targets(root: Path, runs: Mapping[str, KartografRun]) -> list[dict[str, str]]:
    """Return the targets of the plans of Kartograf as ``hydraulik-plan/1`` targets."""
    targets: list[dict[str, str]] = []
    for run in runs.values():
        for entry in run.targets:
            path = Path(entry["path"])
            try:
                name = path.relative_to(root).as_posix()
            except ValueError:
                name = path.name
            target = {"name": name, "path": str(path), "action": entry["action"]}
            if "reason" in entry:
                target["reason"] = entry["reason"]
            targets.append(target)
    return targets


def _reason(target: Mapping[str, str]) -> str:
    reason = target.get("reason", "output_exists")
    return reason if reason in _REASONS else "output_exists"


def _conflicts(plan: WritePlan, targets: Sequence[Mapping[str, str]]) -> list[str]:
    found = set(plan.conflicts)
    found.update(_reason(t) for t in targets if t["action"] == "conflict")
    return [reason for reason in _REASONS if reason in found]


def _raise_conflicts(plan: WritePlan, targets: Sequence[Mapping[str, str]]) -> None:
    """Fail before the first byte when a plan lists a conflict (DEV-19.6)."""
    refused = [t for t in targets if t["action"] == "conflict"]
    if not refused:
        return
    reason = _conflicts(plan, targets)[0]
    raise ConflictError(
        f"{len(refused)} output file(s) cannot be written",
        reason=reason,
        details={"paths": [t["path"] for t in refused]},
        hint=(
            "Use --force to replace them, or choose another --output-dir."
            if reason == "output_exists"
            else "Choose another --output-dir."
        ),
    )


def _outcome(items: Sequence[Mapping[str, Any]]) -> str:
    failed = any(item["status"] == "failed" for item in items)
    succeeded = any(item["status"] == "ok" for item in items)
    if not failed:
        return "ok"
    return "partial" if succeeded else "failed"


def _unit_items(
    name: str, run: KartografRun | None, error: HydraulikError | None
) -> list[dict[str, Any]]:
    """Return the per-unit outcomes of one product, ids prefixed with the product."""
    if error is not None:
        item: dict[str, Any] = {
            "id": name,
            "status": "failed",
            "code": error.code,
            "message": str(error),
        }
        if "reason" in error.details:
            item["reason"] = error.details["reason"]
        return [item]
    assert run is not None
    if run.items:
        items = [{**entry, "id": f"{name}/{entry['id']}"} for entry in run.items]
        for entry in items:
            if entry["status"] == "failed":
                entry.setdefault("code", "source_unavailable")
        return items
    if run.status == "ok":
        return [{"id": name, "status": "ok"}]
    return [
        {
            "id": name,
            "status": "failed",
            "code": "source_unavailable",
            "reason": "kartograf_failed",
            "message": f"Kartograf reported {run.status} without per-unit outcomes",
        }
    ]


def _document(
    status: EngineStatus,
    area: _Area,
    root: Path,
    names: Sequence[str],
    runs: Mapping[str, KartografRun],
    errors: Mapping[str, HydraulikError],
) -> TerrainDocument:
    """Assemble ``hydraulik-terrain/1`` from what the calls returned."""
    products: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    notices: list[dict[str, str]] = []
    sources: list[dict[str, Any]] = []
    for name in names:
        recipe = RECIPES[name]
        run = runs.get(name)
        products.append(
            {
                "product": name,
                "command": recipe.command,
                "directory": str(root / name),
                "status": "failed" if run is None else run.status,
                "files": [] if run is None else [f["path"] for f in run.files],
                "summary": recipe.summary,
            }
        )
        items.extend(_unit_items(name, run, errors.get(name)))
        if run is None:
            continue
        files.extend(dict(entry) for entry in run.files)
        skipped.extend(
            {**entry, "id": f"{name}/{entry['id']}"} for entry in run.skipped
        )
        notices.extend(
            notice(
                entry["level"] if entry["level"] in ("info", "warning") else "info",
                entry["code"],
                f"kartograf {recipe.command}: {entry['message']}",
            )
            for entry in run.notices
        )
        if run.files:
            sources.append({"product": name, **asdict(recipe.source)})
    document = TerrainDocument(
        engine={
            "name": "kartograf",
            "version": status.version,
            "location": status.location,
        },
        area=area.document,
        products=products,
        files=files,
        skipped=skipped,
        sources=sources,
    )
    document.items.extend(items)
    document.status = _outcome(items)
    document.notices.extend(notices)
    if sources:
        terms = "; ".join(
            dict.fromkeys(
                f"{source['provider']} ({source['licence']})" for source in sources
            )
        )
        document.notices.append(
            notice(
                "info",
                "attribution",
                f"plain files carry no licence sidecar: name the sources when you "
                f"publish a result: {terms}; see sources[]",
            )
        )
    return document


def download_terrain(
    *,
    bbox: Sequence[float] | None = None,
    crs: str | None = None,
    geometry: str | os.PathLike[str] | None = None,
    layer: str | None = None,
    products: Sequence[str] | None = None,
    output_dir: str | os.PathLike[str],
    force: bool = False,
    check: bool = False,
) -> TerrainDocument | PlanDocument:
    """Download the terrain, land cover and soil groups of an area with Kartograf.

    Kartograf is started as a program, once per product, and writes plain files with
    its ``--output-dir`` (DEV-19.1) into one sub-directory of ``output_dir`` for each
    product: ``elevation`` (the 1 m terrain model as one GeoTIFF in EPSG:2180),
    ``landcover`` (the BDOT10k GeoPackage of the county or counties) and ``soil`` (the
    hydrologic soil groups as a GeoTIFF). Before the first byte is fetched, the plan of
    every product is read with ``--check`` and a conflict in any of them fails the whole
    call (DEV-19.6); nothing is replaced without ``force``.

    Parameters
    ----------
    bbox : sequence of float or None, optional
        ``min_x, min_y, max_x, max_y`` of the area in ``crs``. Exactly one of ``bbox``
        and ``geometry`` is required.
    crs : str or None, optional
        CRS of ``bbox``; the CRS that Kartograf takes (for example ``EPSG:2180`` or
        ``EPSG:4326``). Required with ``bbox``.
    geometry : path-like or None, optional
        Vector file (GeoPackage or Shapefile) of the area; its extent is the area.
    layer : str or None, optional
        Layer of ``geometry``; the first layer when not given.
    products : sequence of str or None, optional
        Which of ``elevation``, ``landcover`` and ``soil`` to fetch; all three when not
        given.
    output_dir : path-like
        Directory for the files; created when missing. It must not be, or lie in, the
        store of another Nogat tool.
    force : bool, optional
        Replace files that exist.
    check : bool, optional
        Plan without effects: Kartograf is asked for its plan of every product (it
        fetches nothing, it may use the network to look at what exists).

    Returns
    -------
    TerrainDocument or PlanDocument
        ``hydraulik-terrain/1`` with the files written, or the ``hydraulik-plan/1`` of
        ``check``. Its status is ``partial`` when a product failed after another had
        succeeded and ``failed`` when every product of several failed; ``items`` has the
        outcome of every unit.

    Raises
    ------
    InvalidInputError
        If the options do not go together or the CRS of ``bbox`` is one Kartograf does
        not take (reasons ``missing_option``, ``exclusive_options``,
        ``option_not_applicable``, ``invalid_bbox``, ``not_allowed``).
    NotFoundError
        If ``geometry`` does not exist.
    MissingDependencyError
        If Kartograf is not found (reason ``engine_missing``), or the installed one
        cannot write plain files or lacks an option the call needs (reason
        ``engine_incompatible``).
    ConflictError
        If a target exists without ``force``, or ``output_dir`` is inside a store.
    HydraulikError
        The error Kartograf reported when the only product failed.

    Examples
    --------
    >>> download_terrain(output_dir="data")
    Traceback (most recent call last):
        ...
    hydraulik.exceptions.InvalidInputError: --bbox: an area is required: --bbox with \
--crs, or --geometry
    """
    area = _area(bbox, crs, geometry, layer)
    names = _chosen(products)
    plan = plan_directory(output_dir, (), force=force)
    root = plan.directory
    settings = load_settings()
    status, words = find_kartograf(settings)
    steps = [
        f"{name}: kartograf {RECIPES[name].command} for the area: "
        f"{RECIPES[name].summary}, into {root / name}"
        for name in names
    ]
    if words is None:
        reason = "engine_missing" if status.via is None else "engine_incompatible"
        if check:
            return PlanDocument(
                output_dir=str(root),
                force=force,
                targets=[],
                conflicts=list(plan.conflicts),
                steps=steps,
                blockers=[blocker(reason, status.detail, status.hint)],
            )
        raise MissingDependencyError(
            status.detail,
            details={"engine": "kartograf"},
            hint=status.hint,
            reason=reason,
        )
    cli = KartografCli(words, timeout_s=float(settings.value("kartograf.timeout_s")))
    _check_crs(cli, names, area)
    if check and plan.store_paths:
        return PlanDocument(
            output_dir=str(root),
            force=force,
            targets=[],
            conflicts=list(plan.conflicts),
            steps=steps,
        )
    if not check:
        plan.raise_on_conflict()
    runs: dict[str, KartografRun] = {}
    errors: dict[str, HydraulikError] = {}
    with sigterm_as_error():
        plans = {
            name: cli.run(
                RECIPES[name].command,
                _options(RECIPES[name], area, root / name, force),
                check=True,
            )
            for name in names
        }
        targets = _targets(root, plans)
        if check:
            return PlanDocument(
                output_dir=str(root),
                force=force,
                targets=targets,
                conflicts=_conflicts(plan, targets),
                steps=steps,
            )
        _raise_conflicts(plan, targets)
        for name in names:
            recipe = RECIPES[name]
            logger.info("terrain download: fetching %s (%s)", name, recipe.command)
            try:
                runs[name] = cli.run(
                    recipe.command, _options(recipe, area, root / name, force)
                )
            except (CancelledError, TerminatedError):
                raise
            except HydraulikError as exc:
                errors[name] = exc
    if len(names) == 1 and names[0] in errors:
        raise errors[names[0]]
    return _document(status, area, root, names, runs, errors)
