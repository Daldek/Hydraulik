"""The land-cover tables of ``model build``: class values and the BDOT10k mapping.

Two tables ship in ``hydraulik/_data/landcover`` and are documented with their sources
in ``docs/LAND_COVER.md`` (ADR-0007):

``classes.csv``
    The classes of the model, each with a Manning ``n`` for shallow overland flow and
    the SCS curve number for the hydrologic soil groups A to D.
``mapping.csv``
    Which BDOT10k feature becomes which class: the layer, optionally an attribute and
    one of its values (``*`` stands for every other value), and the class. The rows are
    painted in the order of the file, so a later row lies over an earlier one.

``--classes FILE`` replaces values of the first table (:func:`load_classes`). This
module reads text files and imports nothing heavy, so ``model build --check`` can
validate them.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Final

from hydraulik.exceptions import InputDataError, NotFoundError

__all__ = [
    "BUILDING",
    "HSG_LETTERS",
    "OTHER_VALUES",
    "UNCLASSIFIED",
    "ClassTable",
    "LandClass",
    "MappingRow",
    "load_classes",
    "load_mapping",
    "normalise",
]

HSG_LETTERS: Final = ("A", "B", "C", "D")
"""The hydrologic soil groups, in the order of the raster codes 1 to 4."""

UNCLASSIFIED: Final = "unclassified"
"""The class of land that no polygon covers."""

BUILDING: Final = "building"
"""The class of roofs: painted as a mask over the other classes."""

OTHER_VALUES: Final = "*"
"""The value of a mapping row that stands for every value the other rows do not name."""

_MANNING_RANGE: Final = (0.001, 1.0)
_CN_RANGE: Final = (30.0, 100.0)
_CN_COLUMNS: Final = ("cn_a", "cn_b", "cn_c", "cn_d")
_VALUE_COLUMNS: Final = ("manning_n", *_CN_COLUMNS)


def normalise(text: object) -> str:
    """Return an attribute value in the form in which values are compared.

    Parameters
    ----------
    text : object
        A value of an attribute or of the mapping table.

    Returns
    -------
    str
        Unicode NFC, case-folded, with runs of white space made one space.

    Examples
    --------
    >>> normalise("  Żwir ")
    'żwir'
    """
    return " ".join(unicodedata.normalize("NFC", str(text)).casefold().split())


@dataclass(frozen=True)
class LandClass:
    """One class of the model and its values.

    Attributes
    ----------
    name : str
        snake_case name.
    description : str
        What the class holds.
    manning_n : float
        Manning ``n`` for shallow overland flow [s/m^(1/3)].
    curve_numbers : tuple of float
        SCS curve number for the groups A, B, C and D, not decreasing from A to D.
    manning_basis, cn_basis : str
        Where the values come from (the shipped table only).
    """

    name: str
    description: str
    manning_n: float
    curve_numbers: tuple[float, float, float, float]
    manning_basis: str = ""
    cn_basis: str = ""


@dataclass(frozen=True)
class ClassTable:
    """The classes of the model.

    Attributes
    ----------
    classes : tuple of LandClass
        In the order of the table; the position of a class is its code in the painted
        raster.
    source : str
        ``shipped``, or the path of the file that overrides values.
    overridden : tuple of str
        The classes whose values the override file changed.
    """

    classes: tuple[LandClass, ...]
    source: str = "shipped"
    overridden: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        """Tuple of str: the class names, in code order."""
        return tuple(item.name for item in self.classes)

    def index(self, name: str) -> int:
        """Return the code of a class.

        Raises
        ------
        KeyError
            If the table has no such class.
        """
        return self.names.index(name)


@dataclass(frozen=True)
class MappingRow:
    """One row of the mapping from BDOT10k to the classes.

    Attributes
    ----------
    layer : str
        The layer of the GeoPackage, for example ``OT_PTWP_A``.
    field : str or None
        The attribute that decides, or ``None`` when every feature of the layer belongs
        to the class.
    value : str or None
        The value of the attribute as it is written (``None`` without a field, ``*`` for
        every other value).
    class_name : str
        The class.
    """

    layer: str
    field: str | None
    value: str | None
    class_name: str


def _invalid(why: str, source: str, **details: object) -> InputDataError:
    return InputDataError(
        f"the land-cover table {source} is not valid: {why}",
        details={"path": source, **details},
        hint="Columns: class, manning_n, cn_a, cn_b, cn_c, cn_d (docs/LAND_COVER.md).",
        reason="invalid_classes_table",
    )


def _rows(text: str, source: str) -> tuple[list[dict[str, str]], bool]:
    """Return the rows of a CSV text keyed by their header, and whether it used ``;``.

    A file saved by a spreadsheet of a Polish locale separates with a semicolon and
    writes the decimal comma; both are read.
    """
    head = text.lstrip("\ufeff").splitlines()[:1]
    semicolon = bool(head) and ";" in head[0] and "," not in head[0]
    reader = csv.DictReader(
        io.StringIO(text.lstrip("\ufeff")), delimiter=";" if semicolon else ","
    )
    rows = [
        {
            str(key).strip(): (value or "").strip()
            for key, value in row.items()
            if key is not None
        }
        for row in reader
    ]
    if not rows:
        raise _invalid("it has no rows", source)
    return rows, semicolon


def _number(text: str, column: str, name: str, source: str, comma: bool) -> float:
    try:
        return float(text.replace(",", ".") if comma else text)
    except ValueError:
        raise _invalid(
            f"{column} of {name} is not a number: {text!r}",
            source,
            **{"class": name, "column": column, "value": text},
        ) from None


def _check(item: LandClass, source: str) -> None:
    """Refuse values outside what SFINCS and the curve-number method allow."""
    low, high = _MANNING_RANGE
    if not low <= item.manning_n <= high:
        raise _invalid(
            f"manning_n of {item.name} is {item.manning_n:g}, not in "
            f"{low:g} to {high:g}",
            source,
            **{"class": item.name, "column": "manning_n"},
        )
    low, high = _CN_RANGE
    curve = item.curve_numbers
    if not all(low <= value <= high for value in curve):
        raise _invalid(
            f"the curve numbers of {item.name} are not all in {low:g} to {high:g}",
            source,
            **{"class": item.name, "column": "cn"},
        )
    if list(curve) != sorted(curve):
        raise _invalid(
            f"the curve numbers of {item.name} must not decrease from group A to D",
            source,
            **{"class": item.name, "column": "cn"},
        )


def _shipped(name: str) -> str:
    return (
        resources.files("hydraulik")
        .joinpath("_data", "landcover", name)
        .read_text(encoding="utf-8")
    )


def _shipped_classes() -> ClassTable:
    rows, _ = _rows(_shipped("classes.csv"), "shipped")
    classes = []
    for row in rows:
        values = {
            column: _number(row[column], column, row["class"], "shipped", False)
            for column in _VALUE_COLUMNS
        }
        item = LandClass(
            row["class"],
            row["description"],
            values["manning_n"],
            (values["cn_a"], values["cn_b"], values["cn_c"], values["cn_d"]),
            row["manning_basis"],
            row["cn_basis"],
        )
        _check(item, "shipped")
        classes.append(item)
    return ClassTable(tuple(classes))


def load_classes(override: str | Path | None = None) -> ClassTable:
    """Return the classes of the model, with the values of a file replaced.

    Parameters
    ----------
    override : path-like or None, optional
        A CSV file (comma or semicolon, decimal point or comma) with a ``class`` column
        and any of ``manning_n``, ``cn_a``, ``cn_b``, ``cn_c``, ``cn_d``. A blank cell
        keeps the shipped value; a class that is not listed keeps its values.

    Returns
    -------
    ClassTable
        The shipped classes with those values replaced.

    Raises
    ------
    NotFoundError
        If ``override`` does not exist.
    InputDataError
        If the file cannot be read, names a class the table does not have, holds a
        number that is not one, or sets a value outside its range (reason
        ``invalid_classes_table``).

    Examples
    --------
    >>> table = load_classes()
    >>> table.index("water"), table.classes[table.index("water")].curve_numbers
    (0, (100.0, 100.0, 100.0, 100.0))
    """
    table = _shipped_classes()
    if override is None:
        return table
    path = Path(override)
    if not path.is_file():
        raise NotFoundError(
            f"land-cover table not found: {path}",
            details={"path": str(path)},
            reason="path_missing",
        )
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _invalid(f"it cannot be read: {exc}", source) from exc
    rows, comma = _rows(text, source)
    if "class" not in rows[0] or not any(
        column in rows[0] for column in _VALUE_COLUMNS
    ):
        raise _invalid(
            "it needs a class column and at least one of " + ", ".join(_VALUE_COLUMNS),
            source,
        )
    by_name = {item.name: item for item in table.classes}
    changed: list[str] = []
    for row in rows:
        name = row.get("class", "")
        if name not in by_name:
            raise _invalid(
                f"{name!r} is not a class; the classes are {', '.join(by_name)}",
                source,
                **{"class": name, "allowed": list(by_name)},
            )
        item = by_name[name]
        values = {
            column: _number(row[column], column, name, source, comma)
            for column in _VALUE_COLUMNS
            if row.get(column)
        }
        if not values:
            continue
        curve = tuple(
            values.get(column, item.curve_numbers[index])
            for index, column in enumerate(_CN_COLUMNS)
        )
        item = replace(
            item,
            manning_n=values.get("manning_n", item.manning_n),
            curve_numbers=(curve[0], curve[1], curve[2], curve[3]),
        )
        _check(item, source)
        by_name[name] = item
        changed.append(name)
    classes = tuple(by_name[item.name] for item in table.classes)
    return ClassTable(classes, source, tuple(dict.fromkeys(changed)))


def load_mapping(table: ClassTable) -> tuple[MappingRow, ...]:
    """Return the mapping from BDOT10k layers and attributes to the classes.

    Parameters
    ----------
    table : ClassTable
        The classes the rows may name.

    Returns
    -------
    tuple of MappingRow
        In painting order.

    Raises
    ------
    InputDataError
        If a row names a class that the table does not have (a defect of the shipped
        table, reason ``invalid_mapping``).

    Examples
    --------
    >>> rows = load_mapping(load_classes())
    >>> rows[0].layer, rows[0].class_name
    ('OT_PTWP_A', 'water')
    """
    rows, _ = _rows(_shipped("mapping.csv"), "mapping")
    known = set(table.names)
    mapping = []
    for row in rows:
        if row["class"] not in known:
            raise InputDataError(
                f"the mapping names the class {row['class']!r}, which the table lacks",
                details={"class": row["class"], "layer": row["layer"]},
                reason="invalid_mapping",
            )
        mapping.append(
            MappingRow(
                row["layer"],
                row["field"] or None,
                row["value"] or None,
                row["class"],
            )
        )
    return tuple(mapping)
