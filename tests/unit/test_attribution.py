"""Provider attribution: merging the lines of several inputs, and the directory file."""

from pathlib import Path

from hydraulik.attribution import (
    PMAXTP,
    Attribution,
    read_attribution_file,
)

S = (
    "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – "
    "Państwowy Instytut Badawczy"
)
P = (
    "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
    "Badawczego zostały przetworzone"
)
CP = "Dane ČHMÚ zostały przetworzone (przeliczone na sumy dobowe)"
RD = "Regulamin danych IMGW-PIB: https://danepubliczne.imgw.pl/regulations"
RH = "Regulamin serwisu hydrologicznego IMGW-PIB: https://hydro.imgw.pl/#/regulamin"
RK = "Regulamin danych PMAXTP: https://klimat.imgw.pl/opady-maksymalne"


def test_merged_lines_follow_the_order_of_the_standard_whatever_the_inputs() -> None:
    station = Attribution((CP, "Own note", P, S), (RD,))

    merged = Attribution.of(PMAXTP, station, PMAXTP)

    assert merged.lines == (S, P, *PMAXTP.lines, CP, "Own note")
    assert merged.notice == (RD, RK)


def test_the_attribution_file_reads_back_into_the_two_lists(tmp_path: Path) -> None:
    both = Attribution.of(PMAXTP, Attribution((S, P), (RD,)))
    (tmp_path / "ATTRIBUTION.txt").write_text(both.to_file(), encoding="utf-8")

    assert read_attribution_file(tmp_path) == both
    assert read_attribution_file(tmp_path / "missing") == Attribution()


def test_a_file_from_before_eco_065_reads_without_the_retired_lines(
    tmp_path: Path,
) -> None:
    old = [
        S,
        "Dane pochodzą z serwisu hydrologicznego IMGW-PIB https://hydro.imgw.pl",
        "Dane IMGW-PIB można wykorzystywać nieodpłatnie do celów prywatnych "
        "(niezarobkowych). Wykorzystanie w działalności gospodarczej, na stronach z "
        "reklamami lub do celów wymienionych w regulaminie (m.in. planowanie w "
        "gospodarowaniu wodami, art. 317 Prawa wodnego) wymaga umowy z IMGW-PIB.",
        "Regulamin: https://danepubliczne.imgw.pl/regulations",
        "Regulamin: https://hydro.imgw.pl/#/regulamin",
        "Regulamin: https://klimat.imgw.pl/opady-maksymalne",
        "Regulamin: https://example.org/terms",
    ]
    (tmp_path / "ATTRIBUTION.txt").write_text("\n".join(old), encoding="utf-8")

    assert read_attribution_file(tmp_path) == Attribution((S,), (RD, RH, RK))


def test_a_terms_line_of_another_provider_is_kept_as_a_terms_line() -> None:
    own = "Regulamin serwisu przykładowego: https://example.org/terms"

    read = Attribution.from_lines([own, S, RK])

    assert read == Attribution((S,), (RK, own))
