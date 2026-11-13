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
RD = "Regulamin: https://danepubliczne.imgw.pl/regulations"


def test_merged_lines_follow_the_order_of_the_standard_whatever_the_inputs() -> None:
    station = Attribution((CP, "Own note", P, S), (RD,))

    merged = Attribution.of(PMAXTP, station, PMAXTP)

    assert merged.lines == (S, P, *PMAXTP.lines, CP, "Own note")
    assert merged.notice == (PMAXTP.notice[0], RD, PMAXTP.notice[1])


def test_the_attribution_file_reads_back_into_the_two_lists(tmp_path: Path) -> None:
    both = Attribution.of(PMAXTP, Attribution((S, P), (RD,)))
    (tmp_path / "ATTRIBUTION.txt").write_text(both.to_file(), encoding="utf-8")

    assert read_attribution_file(tmp_path) == both
    assert read_attribution_file(tmp_path / "missing") == Attribution()
