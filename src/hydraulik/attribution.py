"""The attribution and the terms notice that the data providers' terms require.

This module is the one source of the texts in Hydraulik (ADR-0012). PMAXTP, the design
rainfall depths of IMGW-PIB, has terms of its own (the „Regulamin udostępniania danych
projektu PMAXTP” on https://klimat.imgw.pl/opady-maksymalne): every work made with the
data names the source with the address of the page, cites the monograph of the project
and, once the data are processed, says so. A design rain, a model, a run and every map
or table made from them are processed data, so they carry all three lines, and the
terms notice links the PMAXTP terms (Nogat DEV-20.7, ECO-065): the line names whose
terms it opens, and no product restates them. The lines are Polish and verbatim (Nogat
DEV-20); they are never translated.

Both travel with the data as lists of lines, in the forms of DEV-20.5:

* JSON: the fields ``attribution`` and ``terms_notice`` of every result document made
  from provider data; read from the same fields of a producer's document (the envelope
  or its ``result``) when Hydraulik reads one;
* CSV: the trailing columns ``attribution`` and ``terms_notice``, one line per cell from
  the first data row down, empty below; when the table has fewer rows than lines, the
  rest is joined into the last cell with newlines. Obserwator's columns
  ``attribution_source`` and ``attribution_processed`` are read as attribution too;
* a directory (a model, a run, a network run): the file :data:`ATTRIBUTION_NAME`, the
  attribution and then the notice, one line per line, which ``model run``,
  ``model couple`` and ``results`` read back. There the two lists are told apart by the
  terms lines' own form, „Regulamin <whose terms>: <address>”;
* GeoTIFF: the metadata tags ``attribution`` and ``terms_notice``, lines joined by
  newlines.

Lines from several inputs are merged without duplicates: the lines of DEV-20 in the
order of DEV-20.4 and DEV-20.7 (S, P, PS, PP, M, C, CP; RD, RH, RK), any other line
after them in the order first seen. Lines that ECO-065 retired, which older products
and stored files still hold, are dropped as they are read: the hydro.imgw.pl line H,
the sentence N on the conditions of use and the terms lines of the old form
„Regulamin: <address>”, of which the three of DEV-20 are read as their new form.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "ATTRIBUTION_NAME",
    "CSV_COLUMNS",
    "PMAXTP",
    "PMAXTP_MONOGRAPH",
    "PMAXTP_PROCESSED",
    "PMAXTP_SOURCE",
    "PMAXTP_TERMS",
    "Attribution",
    "read_attribution_file",
    "read_csv_attribution",
]

PMAXTP_SOURCE: Final = (
    "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – "
    "Państwowy Instytut Badawczy, dane pochodzą ze strony "
    "https://klimat.imgw.pl/opady-maksymalne"
)
"""The source of PMAXTP data, verbatim from ust. 1 of the PMAXTP terms."""

PMAXTP_PROCESSED: Final = (
    "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
    "Badawczego pochodzące ze strony https://klimat.imgw.pl/opady-maksymalne "
    "zostały przetworzone"
)
"""The mark of processed PMAXTP data, verbatim from ust. 2 of the PMAXTP terms."""

PMAXTP_MONOGRAPH: Final = (
    "„Modele probabilistyczne opadów maksymalnych o określonym czasie trwania i "
    "prawdopodobieństwie przewyższenia – Projekt PMAXTP”, red. Bogdan Ozga-Zieliński, "
    "Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy, "
    "Warszawa 2022"
)
"""The monograph of the PMAXTP project that ust. 1 of the terms asks to cite."""

_TERMS_FORM: Final = re.compile(r"Regulamin [^:]+: \S+")
"""A terms line of DEV-20.7: „Regulamin <whose terms>: <address>”."""

_TERMS_DANEPUBLICZNE: Final = (
    "Regulamin danych IMGW-PIB: https://danepubliczne.imgw.pl/regulations"
)
_TERMS_HYDRO: Final = (
    "Regulamin serwisu hydrologicznego IMGW-PIB: https://hydro.imgw.pl/#/regulamin"
)

PMAXTP_TERMS: Final = "Regulamin danych PMAXTP: https://klimat.imgw.pl/opady-maksymalne"
"""The terms of PMAXTP, the line RK of the terms notice."""

_RETIRED_TERMS_PREFIX: Final = "Regulamin: "

_RETIRED: Final[Mapping[str, str]] = {
    f"{_RETIRED_TERMS_PREFIX}https://danepubliczne.imgw.pl/regulations": (
        _TERMS_DANEPUBLICZNE
    ),
    f"{_RETIRED_TERMS_PREFIX}https://hydro.imgw.pl/#/regulamin": _TERMS_HYDRO,
    f"{_RETIRED_TERMS_PREFIX}https://klimat.imgw.pl/opady-maksymalne": PMAXTP_TERMS,
}
"""The old terms lines of DEV-20 and the lines that replace them (ECO-065)."""

_DROPPED: Final = frozenset(
    {
        "Dane pochodzą z serwisu hydrologicznego IMGW-PIB https://hydro.imgw.pl",
        (
            "Dane IMGW-PIB można wykorzystywać nieodpłatnie do celów prywatnych "
            "(niezarobkowych). Wykorzystanie w działalności gospodarczej, na stronach "
            "z reklamami lub do celów wymienionych w regulaminie (m.in. planowanie w "
            "gospodarowaniu wodami, art. 317 Prawa wodnego) wymaga umowy z IMGW-PIB."
        ),
    }
)
"""The lines H and N, retired by ECO-065, which no product carries any more."""

ATTRIBUTION_NAME: Final = "ATTRIBUTION.txt"
"""The file of a model or run directory that holds the attribution of its data."""

CSV_COLUMNS: Final = ("attribution", "terms_notice")
"""The trailing columns of a CSV table that carry the two lists."""

_OBSERWATOR_COLUMNS: Final = ("attribution_source", "attribution_processed")

_ORDER: Final = (
    (
        "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – "
        "Państwowy Instytut Badawczy"
    ),
    (
        "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
        "Badawczego zostały przetworzone"
    ),
    PMAXTP_SOURCE,
    PMAXTP_PROCESSED,
    PMAXTP_MONOGRAPH,
    (
        "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), "
        "https://opendata.chmi.cz, licencja CC BY 4.0 "
        "(https://creativecommons.org/licenses/by/4.0/)"
    ),
    "Dane ČHMÚ zostały przetworzone",
    _TERMS_DANEPUBLICZNE,
    _TERMS_HYDRO,
    PMAXTP_TERMS,
)
"""The lines of Nogat DEV-20 in their order (S, P, PS, PP, M, C, CP; RD, RH, RK);
the ČHMÚ processed mark CP is matched by its beginning, it names what was done."""

_CP_INDEX: Final = 6


def _rank(line: str) -> int:
    for index, known in enumerate(_ORDER):
        if line == known or (index == _CP_INDEX and line.startswith(known)):
            return index
    return len(_ORDER)


def _current(line: str) -> str | None:
    """Return the line as DEV-20 has it now; ``None`` for a line ECO-065 retired."""
    if line in _DROPPED:
        return None
    if line.startswith(_RETIRED_TERMS_PREFIX):
        return _RETIRED.get(line)
    return line


def _merge(groups: Iterable[Iterable[str]]) -> tuple[str, ...]:
    """Merge lines without duplicates, those of DEV-20 first and in their order."""
    found: dict[str, None] = {}
    for group in groups:
        for line in group:
            text = _current(line.strip())
            if text:
                found.setdefault(text)
    return tuple(sorted(found, key=_rank))


def _is_terms(line: str) -> bool:
    return _TERMS_FORM.fullmatch(line) is not None


def _cells(lines: Sequence[str], rows: int) -> list[str]:
    """Spread lines over ``rows`` cells, the rest joined into the last one."""
    if rows <= 0:
        return []
    if len(lines) <= rows:
        return [*lines, *([""] * (rows - len(lines)))]
    return [*lines[: rows - 1], "\n".join(lines[rows - 1 :])]


@dataclass(frozen=True)
class Attribution:
    """What a product must say about the data it was made from.

    Attributes
    ----------
    lines : tuple of str
        The attribution (``attribution``): source, processed mark, monograph.
    notice : tuple of str
        The terms notice (``terms_notice``): the links to the terms that apply.

    Examples
    --------
    >>> Attribution.of(Attribution(("a",)), Attribution(("a", "b"))).lines
    ('a', 'b')
    """

    lines: tuple[str, ...] = ()
    notice: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """bool: whether there is anything to say."""
        return bool(self.lines or self.notice)

    @classmethod
    def of(cls, *parts: Attribution) -> Attribution:
        """Merge several attributions in the order first seen, without duplicates.

        Parameters
        ----------
        *parts : Attribution
            The attributions of the inputs.

        Returns
        -------
        Attribution
            Their union.
        """
        return cls(
            _merge(part.lines for part in parts), _merge(part.notice for part in parts)
        )

    @classmethod
    def from_lines(cls, lines: Iterable[str]) -> Attribution:
        """Read the lines of a file: terms lines go to ``notice``, others to ``lines``.

        Parameters
        ----------
        lines : iterable of str
            The lines, in any order.

        Returns
        -------
        Attribution
            The two lists.

        Examples
        --------
        >>> Attribution.from_lines([PMAXTP_SOURCE, PMAXTP_TERMS]).notice
        ('Regulamin danych PMAXTP: https://klimat.imgw.pl/opady-maksymalne',)
        """
        merged = _merge([lines])
        return cls(
            tuple(line for line in merged if not _is_terms(line)),
            tuple(line for line in merged if _is_terms(line)),
        )

    @classmethod
    def from_document(cls, document: object) -> Attribution:
        """Read ``attribution`` and ``terms_notice`` of a producer's JSON document.

        Parameters
        ----------
        document : object
            A parsed document: an envelope (``<tool>-result/1``) whose ``result`` may
            have the fields too, or the domain document alone.

        Returns
        -------
        Attribution
            The lines of both places, merged; empty when there are none.

        Examples
        --------
        >>> Attribution.from_document(
        ...     {"attribution": ["a"], "result": {"attribution": ["a", "b"]}}
        ... ).lines
        ('a', 'b')
        """
        if not isinstance(document, Mapping):
            return cls()
        places = [document]
        body = document.get("result")
        if isinstance(body, Mapping):
            places.append(body)

        def strings(key: str) -> list[list[str]]:
            return [
                [item for item in value if isinstance(item, str)]
                for value in (place.get(key) for place in places)
                if isinstance(value, list)
            ]

        return cls(_merge(strings("attribution")), _merge(strings("terms_notice")))

    def header(self) -> tuple[str, ...]:
        """Return the CSV columns to append; none when there is nothing to say."""
        return CSV_COLUMNS if self else ()

    def columns(self, rows: int) -> list[tuple[str, ...]]:
        r"""Return the cells of the trailing CSV columns for a table of ``rows`` rows.

        Parameters
        ----------
        rows : int
            Number of data rows of the table.

        Returns
        -------
        list of tuple of str
            For each row, the cells to append (``attribution``, ``terms_notice``);
            empty tuples when there is nothing to say.

        Examples
        --------
        >>> Attribution(("a", "b", "c"), ("n",)).columns(2)
        [('a', 'n'), ('b\nc', '')]
        """
        if not self:
            return [() for _ in range(rows)]
        return list(
            zip(_cells(self.lines, rows), _cells(self.notice, rows), strict=True)
        )

    def to_file(self) -> str:
        """Return the text of :data:`ATTRIBUTION_NAME`, one line per line.

        Returns
        -------
        str
            The attribution, then the notice, each line ending in a newline.
        """
        return "".join(f"{line}\n" for line in self.lines + self.notice)

    def to_tags(self) -> dict[str, str]:
        """Return the GeoTIFF metadata tags, the lines joined by newlines.

        Returns
        -------
        dict of str to str
            ``attribution`` and ``terms_notice``, each only when it has lines.
        """
        tags = {"attribution": "\n".join(self.lines)} if self.lines else {}
        if self.notice:
            tags["terms_notice"] = "\n".join(self.notice)
        return tags


PMAXTP: Final = Attribution(
    (PMAXTP_SOURCE, PMAXTP_PROCESSED, PMAXTP_MONOGRAPH),
    (PMAXTP_TERMS,),
)
"""What a product made from PMAXTP data carries, in the order of Nogat DEV-20."""


def read_csv_attribution(path: str | Path) -> Attribution:
    r"""Return the attribution of the trailing columns of a CSV table.

    Parameters
    ----------
    path : str or Path
        The table.

    Returns
    -------
    Attribution
        The lines of ``attribution`` (and of Obserwator's ``attribution_source`` and
        ``attribution_processed``) and of ``terms_notice``; empty when the table has
        none of them, is missing or is not UTF-8 CSV (reading the table reports that).

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     p = pathlib.Path(tmp) / "rain.csv"
    ...     _ = p.write_text('time_min,depth_mm,attribution\n5,1,"a\nb"\n10,2,\n')
    ...     read_csv_attribution(p).lines
    ('a', 'b')
    """
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
    except (OSError, UnicodeDecodeError, csv.Error):
        return Attribution()

    def column(*names: str) -> list[str]:
        return [
            line
            for row in rows
            for name in names
            for line in (row.get(name) or "").splitlines()
        ]

    return Attribution(
        _merge([column("attribution", *_OBSERWATOR_COLUMNS)]),
        _merge([column("terms_notice")]),
    )


def read_attribution_file(directory: Path) -> Attribution:
    """Return the attribution of a model or run directory.

    Parameters
    ----------
    directory : Path
        The directory.

    Returns
    -------
    Attribution
        The lines of its :data:`ATTRIBUTION_NAME`; empty when there is none.
    """
    path = directory / ATTRIBUTION_NAME
    if not path.is_file():
        return Attribution()
    return Attribution.from_lines(path.read_text(encoding="utf-8-sig").splitlines())
