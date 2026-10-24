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
    "engine_timeout": "SFINCS przekroczył limit czasu i został zatrzymany.",
    "engine_unavailable": "Nie udało się uruchomić silnika.",
    "extra_missing": "Brakuje pakietu Pythona z dodatku Hydraulika.",
    "model_missing": "W katalogu nie ma modelu SFINCS (sfincs.inp).",
    "results_missing": "Nie ma wyników przebiegu SFINCS (sfincs_map.nc).",
    "map_layout": "Mapa nie jest siatką regularną SFINCS.",
    "below_huthresh": "Próg głębokości jest niższy niż próg suchy/mokry modelu.",
    "invalid_inp": "Plik wejściowy jest niepoprawny.",
    "output_format": "Model nie zapisuje wyników w formacie NetCDF.",
    "unknown_node": "Sieć nie ma takiego węzła.",
    "inflow_required": "Tabela sieci nie ma własnego dopływu; podaj --inflow.",
    "option_not_applicable": "Opcja nie dotyczy wybranego źródła lub kształtu.",
    "invalid_network_table": "Tabela sieci jest niepoprawna.",
    "invalid_hydrograph": "Tabela hydrogramu jest niepoprawna.",
    "flow_units": "Plik SWMM musi używać jednostek SI (FLOW_UNITS CMS).",
    "invalid_rain_table": "Tabela opadu jest niepoprawna.",
    "invalid_hietogram": (
        "Hietogram jest niepoprawny; podaj wynik `hydrolog precip hietogram`."
    ),
    "invalid_pmaxtp": (
        "Dokument PMAXTP jest niepoprawny; podaj wynik `imgw pmaxtp fetch`."
    ),
    "pmaxtp_no_data": (
        "PMAXTP nie ma wysokości dla tego czasu trwania i prawdopodobieństwa."
    ),
    "source_unreachable": (
        "IMGW-PIB nie odpowiada; podaj wysokość opadu ręcznie (--total-mm)."
    ),
    "source_data": "Nie udało się odczytać odpowiedzi źródła danych.",
    "hydrolog_failed": "Hydrolog nie policzył hietogramu.",
    "invalid_bbox": (
        "Prostokąt --bbox to min_x,min_y,max_x,max_y, minima poniżej maksimów."
    ),
    "invalid_crs": (
        "Nie rozpoznano układu współrzędnych; podaj kod EPSG, np. EPSG:2180."
    ),
    "crs_missing": "Plik nie ma układu współrzędnych; przypisz go danym.",
    "crs_not_supported": (
        "Model wymaga układu rzutowanego w metrach z kodem EPSG (dla Polski EPSG:2180)."
    ),
    "raster_unreadable": (
        "GDAL nie odczytał rastra; podaj GeoTIFF z układem współrzędnych."
    ),
    "vector_unreadable": (
        "Nie odczytano warstwy wektorowej; sprawdź plik i nazwę warstwy."
    ),
    "empty_geometry": "Warstwa nie zawiera żadnej geometrii.",
    "empty_domain": "Obszar modelu nie zawiera żadnej komórki.",
    "grid_too_large": (
        "Siatka miałaby ponad 25 mln komórek; zwiększ --dx-m lub zmniejsz obszar."
    ),
    "dem_gaps": "Część obszaru nie ma wysokości; podaj rastry pokrywające cały obszar.",
    "manning_gaps": (
        "Część obszaru nie ma współczynnika Manninga; raster musi pokrywać obszar."
    ),
    "cn_gaps": "Raster infiltracji nie pokrywa żadnej komórki obszaru.",
    "invalid_retention": "Retencja SCS S jest w mm i nie może być ujemna.",
    "outlet_outside_domain": "Odpływ (--outlet) nie dotyka obszaru modelu.",
    "outlet_not_on_edge": (
        "Odpływ leży wewnątrz obszaru; woda może wypłynąć tylko brzegiem."
    ),
    "station_outside_domain": "Stacja leży poza obszarem modelu.",
    "invalid_station_table": "Tabela stacji jest niepoprawna (kolumny name, x_m, y_m).",
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
