"""Design rain from Hydrolog and IMGWTools: the library routes and their documents.

``hietogram_euler_ii.json`` is the output of ``hydrolog precip hietogram --json`` as
Hydrolog prints it; ``pmaxtp_fetch.json`` has the layout that ``imgw pmaxtp fetch
--json`` prints (IMGWTools' own command code made it), with synthetic depths.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from hydraulik.data.rainfall import (
    fetch_pmaxtp,
    generate_hyetograph,
    pmaxtp_depth,
    read_hietogram_document,
    read_pmaxtp_document,
)
from hydraulik.exceptions import (
    InputDataError,
    InvalidInputError,
    NoDataError,
    NotFoundError,
    SourceUnavailableError,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "rain"


def _peak_position(depths: tuple[float, ...]) -> float:
    """The relative position of the heaviest step in the duration."""
    return (depths.index(max(depths)) + 0.5) / len(depths)


@pytest.mark.parametrize("kind", ["block", "triangular", "beta", "euler_ii"])
def test_every_shape_keeps_the_depth_and_the_steps(kind: str) -> None:
    table = generate_hyetograph(kind, 40.0, 120.0, 10.0)

    assert table.step_min == 10.0 and len(table.depth_mm) == 12
    assert table.total_mm == pytest.approx(40.0)
    assert min(table.depth_mm) >= 0.0
    assert table.duration_min == 120.0


def test_the_block_is_uniform_and_the_shapes_peak_where_hydrolog_says() -> None:
    block = generate_hyetograph("block", 30.0, 60.0, 15.0)
    euler = generate_hyetograph("euler_ii", 40.0, 120.0, 5.0)
    early = generate_hyetograph("beta", 40.0, 120.0, 5.0, alpha=2.0, beta=5.0)
    late = generate_hyetograph("beta", 40.0, 120.0, 5.0, alpha=5.0, beta=2.0)
    centred = generate_hyetograph("triangular", 40.0, 120.0, 5.0, peak_position=0.5)

    assert block.depth_mm == (7.5, 7.5, 7.5, 7.5)
    assert _peak_position(euler.depth_mm) == pytest.approx(0.33, abs=0.05)
    assert _peak_position(early.depth_mm) < 0.3 < 0.7 < _peak_position(late.depth_mm)
    assert _peak_position(centred.depth_mm) == pytest.approx(0.5, abs=0.05)


def test_a_duration_that_is_not_a_multiple_of_the_step_is_cut_to_whole_steps() -> None:
    table = generate_hyetograph("block", 30.0, 62.0, 5.0)

    assert len(table.depth_mm) == 12 and table.duration_min == 60.0
    assert table.total_mm == pytest.approx(30.0)  # the depth is kept


@pytest.mark.parametrize(
    ("kind", "parameters"),
    [
        ("block", {"alpha": 2.0}),
        ("beta", {"peak_position": 0.4}),
        ("triangular", {"beta": 3.0}),
        ("euler_ii", {"alpha": 1.0}),
    ],
)
def test_a_parameter_of_another_shape_is_refused_not_ignored(
    kind: str, parameters: dict[str, float]
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        generate_hyetograph(kind, 40.0, 60.0, 5.0, **parameters)

    assert caught.value.details["reason"] == "option_not_applicable"
    assert caught.value.details["option"] == next(iter(parameters))


def test_hydrolog_refusals_become_validation_errors_with_its_message() -> None:
    with pytest.raises(InvalidInputError) as unknown:
        generate_hyetograph("gauss", 40.0, 60.0, 5.0)
    with pytest.raises(InvalidInputError) as negative:
        generate_hyetograph("block", -1.0, 60.0, 5.0)
    with pytest.raises(InvalidInputError) as longer:
        generate_hyetograph("block", 40.0, 5.0, 10.0)
    with pytest.raises(InvalidInputError) as peak:
        generate_hyetograph("euler_ii", 40.0, 60.0, 5.0, peak_position=1.5)

    assert unknown.value.details["reason"] == "not_allowed"
    assert [e.value.details["reason"] for e in (negative, longer, peak)] == [
        "out_of_range"
    ] * 3
    assert "total_mm" in str(negative.value)


def test_the_document_of_hydrolog_is_read_as_it_is_printed() -> None:
    document = read_hietogram_document(FIXTURES / "hietogram_euler_ii.json")
    result = json.loads((FIXTURES / "hietogram_euler_ii.json").read_text())["result"]

    assert document.hietogram_type == "euler_ii"
    assert document.parameters == {"peak_position": 0.33}
    assert document.table.step_min == 10.0
    assert document.table.depth_mm == tuple(result["depths_mm"])
    assert document.table.total_mm == pytest.approx(40.0)


def test_the_result_alone_is_as_good_as_the_envelope(tmp_path: Path) -> None:
    result = json.loads((FIXTURES / "hietogram_euler_ii.json").read_text())["result"]
    (tmp_path / "bare.json").write_text(json.dumps(result), encoding="utf-8")

    bare = read_hietogram_document(tmp_path / "bare.json")
    full = read_hietogram_document(FIXTURES / "hietogram_euler_ii.json")

    assert bare.table == full.table


@pytest.mark.parametrize(
    ("document", "why"),
    [
        ("not json", "not a JSON document"),
        ("[1, 2]", "not a JSON object"),
        ('{"result": {"times_min": [5]}}', "lacks times_min and depths_mm"),
        ('{"times_min": [5, 11], "depths_mm": [1, 1]}', "not regular"),
        ('{"times_min": [5, 10], "depths_mm": [1, -1]}', "negative"),
        ('{"times_min": [5, 10], "depths_mm": [1]}', "same length"),
        ('{"times_min": [5, "x"], "depths_mm": [1, 1]}', "not a number"),
    ],
)
def test_a_malformed_hietogram_document_is_a_data_error_that_says_why(
    tmp_path: Path, document: str, why: str
) -> None:
    path = tmp_path / "h.json"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(InputDataError) as caught:
        read_hietogram_document(path)

    assert caught.value.details["reason"] == "invalid_hietogram"
    assert why in str(caught.value)


def test_a_missing_document_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        read_hietogram_document(tmp_path / "none.json")
    with pytest.raises(NotFoundError):
        read_pmaxtp_document(tmp_path / "none.json")


def test_the_pmaxtp_document_gives_the_depth_of_a_duration_and_a_probability() -> None:
    pmaxtp = read_pmaxtp_document(FIXTURES / "pmaxtp_fetch.json")

    depth = pmaxtp_depth(pmaxtp, 60.0, 10)

    assert (pmaxtp.method, pmaxtp.latitude, pmaxtp.longitude) == ("POT", 52.23, 21.01)
    assert sorted(pmaxtp.quantiles_mm) == [15, 30, 45, 60, 90, 120, 180]
    assert depth.depth_mm == 38.8
    assert (depth.duration_min, depth.probability_percent) == (60, 10)
    assert depth.upper_bound_mm == 43.5 and depth.error_mm == 3.1
    # the depth grows with the duration and falls with the probability
    assert pmaxtp_depth(pmaxtp, 120, 10).depth_mm > depth.depth_mm
    assert (
        pmaxtp_depth(pmaxtp, 60, 1).depth_mm
        > depth.depth_mm
        > (pmaxtp_depth(pmaxtp, 60, 50).depth_mm)
    )


@pytest.mark.parametrize(("duration", "probability"), [(75, 10), (60, 3), (60.5, 10)])
def test_a_pair_that_pmaxtp_does_not_have_is_no_data_and_lists_what_it_has(
    duration: float, probability: int
) -> None:
    pmaxtp = read_pmaxtp_document(FIXTURES / "pmaxtp_fetch.json")

    with pytest.raises(NoDataError) as caught:
        pmaxtp_depth(pmaxtp, duration, probability)

    assert caught.value.details["reason"] == "pmaxtp_no_data"
    assert caught.value.details["durations_min"] == [15, 30, 45, 60, 90, 120, 180]
    assert caught.value.details["probabilities_percent"] == [1, 2, 5, 10, 20, 50]


def test_prefixed_keys_and_the_bare_result_are_accepted(tmp_path: Path) -> None:
    document: dict[str, Any] = {
        "method": "AMP",
        "data": {"ks": {"t60": {"p10": 40.0}}},
    }
    (tmp_path / "p.json").write_text(json.dumps(document), encoding="utf-8")

    pmaxtp = read_pmaxtp_document(tmp_path / "p.json")

    assert pmaxtp.method == "AMP" and pmaxtp.latitude is None
    assert pmaxtp_depth(pmaxtp, 60, 10).depth_mm == 40.0
    assert pmaxtp_depth(pmaxtp, 60, 10).upper_bound_mm is None


@pytest.mark.parametrize("document", ['{"data": {"sg": {}}}', '{"result": 3}', "{}"])
def test_a_document_without_quantiles_is_a_data_error(
    tmp_path: Path, document: str
) -> None:
    (tmp_path / "p.json").write_text(document, encoding="utf-8")

    with pytest.raises(InputDataError) as caught:
        read_pmaxtp_document(tmp_path / "p.json")

    assert caught.value.details["reason"] == "invalid_pmaxtp"


def test_the_point_is_fetched_through_the_public_function_of_imgwtools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import imgwtools
    from imgwtools import PMaXTPData, PMaXTPResult

    calls: list[tuple[Any, ...]] = []

    def fake(latitude: float, longitude: float, method: str = "POT") -> PMaXTPResult:
        calls.append((latitude, longitude, method))
        return PMaXTPResult(
            method=method,
            latitude=latitude,
            longitude=longitude,
            data=PMaXTPData(ks={"60": {"10": 31.5}}, sg={"60": {"10": 35.0}}),
        )

    monkeypatch.setattr(imgwtools, "fetch_pmaxtp", fake)

    pmaxtp = fetch_pmaxtp(52.1, 21.0, "AMP")

    assert calls == [(52.1, 21.0, "AMP")]
    assert (pmaxtp.method, pmaxtp.latitude) == ("AMP", 52.1)
    depth = pmaxtp_depth(pmaxtp, 60, 10)
    assert (depth.depth_mm, depth.upper_bound_mm, depth.error_mm) == (31.5, 35.0, None)


@pytest.mark.parametrize(
    ("failure", "expected", "reason"),
    [
        ("IMGWValidationError", InvalidInputError, "out_of_range"),
        ("IMGWConnectionError", SourceUnavailableError, "source_unreachable"),
        ("IMGWDataError", InputDataError, "source_data"),
    ],
)
def test_the_failures_of_imgwtools_become_registry_errors(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected: type[Exception],
    reason: str,
) -> None:
    import imgwtools

    def fake(latitude: float, longitude: float, method: str = "POT") -> None:
        raise getattr(imgwtools, failure)("it failed")

    monkeypatch.setattr(imgwtools, "fetch_pmaxtp", fake)

    with pytest.raises(expected) as caught:
        fetch_pmaxtp(10.0, 10.0)

    assert caught.value.details["reason"] == reason  # type: ignore[attr-defined]
    assert "it failed" in str(caught.value)
