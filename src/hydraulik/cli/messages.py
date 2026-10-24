"""Translation resources of the human-readable output (DEV-2.3, AGI-9.1).

The keys are English identifiers; ``EN`` and ``PL`` hold the same keys (a contract
test checks it). Machine output (``--json``, the error document on the last line of
stderr) never uses these texts (AGI-9.2).
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = ["EN", "PL", "reason_text", "text"]

EN: Final[dict[str, str]] = {
    "status.ok": "ok",
    "status.partial": "partial: some units failed",
    "status.failed": "failed: no unit succeeded",
    "status.cancelled": "cancelled",
    "check.header": "Plan (nothing was written)",
    "result.header": "Result",
    "error.label": "Error",
    "hint.label": "Hint",
    "notices.header": "Notices",
    "items.header": "Units",
    "usage.header": "usage",
}

PL: Final[dict[str, str]] = {
    "status.ok": "OK",
    "status.partial": "częściowo: część jednostek zakończyła się błędem",
    "status.failed": "niepowodzenie: żadna jednostka się nie powiodła",
    "status.cancelled": "anulowano",
    "check.header": "Plan (nic nie zapisano)",
    "result.header": "Wynik",
    "error.label": "Błąd",
    "hint.label": "Wskazówka",
    "notices.header": "Uwagi",
    "items.header": "Jednostki",
    "usage.header": "użycie",
}

# Polish explanation of the reasons (details.reason) that users meet most often.
REASONS_PL: Final[dict[str, str]] = {
    "output_exists": "Plik wynikowy już istnieje; użyj --force, aby go zastąpić.",
    "duplicate_output_name": "Dwa pliki wynikowe miałyby tę samą nazwę.",
    "output_in_store": "Katalog należy do magazynu innego narzędzia Nogat.",
    "missing_option": "Brakuje wymaganej opcji.",
    "unknown_option": "Nieznana opcja.",
    "unknown_command": "Nieznane polecenie; zobacz `hydraulik commands list`.",
    "wrong_type": "Wartość ma zły typ.",
    "not_allowed": "Wartość spoza dozwolonego zbioru.",
    "out_of_range": "Wartość poza dozwolonym zakresem.",
    "exclusive_options": "Opcje wykluczają się wzajemnie.",
    "usage": "Błędne wywołanie polecenia.",
    "engine_missing": "Nie znaleziono silnika; zobacz `hydraulik engines check`.",
    "engine_failed": "Silnik zakończył pracę błędem.",
    "invalid_settings_file": "Plik ustawień nie jest poprawnym TOML.",
    "unknown_setting": "Nieznane ustawienie.",
    "invalid_setting": "Nieprawidłowa wartość ustawienia.",
    "path_missing": "Plik lub katalog nie istnieje.",
}


def text(key: str, lang: Literal["pl", "en"]) -> str:
    """Return the text of ``key`` in ``lang``.

    Parameters
    ----------
    key : str
        English identifier from :data:`EN`.
    lang : {"pl", "en"}
        Language.

    Returns
    -------
    str
        The translation; the English text when Polish has none.

    Examples
    --------
    >>> text("error.label", "pl")
    'Błąd'
    """
    return (PL if lang == "pl" else EN).get(key) or EN[key]


def reason_text(reason: str | None, lang: Literal["pl", "en"]) -> str | None:
    """Return the Polish explanation of a ``details.reason``, or ``None``.

    Parameters
    ----------
    reason : str or None
        The reason of an error document.
    lang : {"pl", "en"}
        Language; English has no table because the message is English already.

    Returns
    -------
    str or None
        The explanation, or ``None`` when there is none.
    """
    if lang != "pl" or reason is None:
        return None
    return REASONS_PL.get(reason)
