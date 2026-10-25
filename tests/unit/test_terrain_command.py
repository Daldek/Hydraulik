"""``terrain download`` with a fake Kartograf: plans, conflicts, outcomes, refusals."""

import json
from pathlib import Path
from typing import Any

import pytest

from hydraulik import check_command, download_terrain
from hydraulik.cli import main
from hydraulik.documents import PlanDocument, TerrainDocument
from hydraulik.engines.detect import EngineStatus
from hydraulik.exceptions import (
    ConflictError,
    InvalidInputError,
    MissingDependencyError,
    NotFoundError,
    SourceUnavailableError,
)
from hydraulik.output import STORE_MARKERS

from ..fake_kartograf import FakeKartograf, install, use

BBOX = [361500.0, 504000.0, 363000.0, 505500.0]
AREA_ARGUMENTS = ["--bbox=361500.0,504000.0,363000.0,505500.0", "--bbox-crs=EPSG:2180"]


def _fetch(out: Path, **options: Any) -> TerrainDocument:
    document = download_terrain(bbox=BBOX, crs="EPSG:2180", output_dir=out, **options)
    assert isinstance(document, TerrainDocument)
    return document


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeKartograf:
    """A Kartograf that writes plain files, found by ``terrain download``."""
    program = install(tmp_path, monkeypatch)
    use(monkeypatch, program)
    return program


def test_every_product_goes_to_its_own_directory_with_its_options_and_terms(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    out = tmp_path / "data"

    document = _fetch(out)

    body = document.to_dict()
    assert body["schema"] == "hydraulik-terrain/1" and document.status == "ok"
    assert [p["product"] for p in body["products"]] == [
        "elevation",
        "landcover",
        "soil",
    ]
    assert [Path(f["path"]).parent.name for f in body["files"]] == [
        "elevation",
        "landcover",
        "soil",
    ]
    assert all(
        f["status"] == "written" and len(f["sha256"]) == 64 for f in body["files"]
    )
    for product in body["products"]:
        assert product["status"] == "ok" and product["directory"] == str(
            out.resolve() / product["product"]
        )
        assert product["files"] == [
            f["path"]
            for f in body["files"]
            if f["path"].startswith(product["directory"])
        ]
    assert body["area"] == {
        "source": "bbox",
        "bbox": BBOX,
        "crs": "EPSG:2180",
    }
    assert [(s["product"], s["provider"], s["licence"]) for s in body["sources"]] == [
        ("elevation", "GUGiK", "PL-PGiK-40a"),
        ("landcover", "GUGiK", "PL-PGiK-40a"),
        ("soil", "ISRIC", "CC-BY-4.0"),
    ]
    assert body["engine"]["name"] == "kartograf"
    codes = [n["code"] for n in document.notices]
    assert codes.count("fake_notice") == 3 and codes[-1] == "attribution"
    assert document.notices[-1]["message"].endswith(
        "publish a result: GUGiK (PL-PGiK-40a); ISRIC (CC-BY-4.0); see sources[]"
    )
    assert sorted(p.name for p in out.iterdir()) == ["elevation", "landcover", "soil"]


def test_the_products_are_fetched_with_the_options_that_fix_them(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    out = (tmp_path / "data").resolve()

    _fetch(out)

    elevation, landcover, soil = fake.downloads()
    assert elevation == [
        "elevation",
        "download",
        "--product=nmt",
        "--country=pl",
        "--cutout",
        "--horizontal-crs=EPSG:2180",
        "--vertical-crs=EVRF2007",
        *AREA_ARGUMENTS,
        f"--output-dir={out / 'elevation'}",
        "--json",
    ]
    assert landcover == [
        "landcover",
        "download",
        "--product=bdot10k",
        *AREA_ARGUMENTS,
        f"--output-dir={out / 'landcover'}",
        "--json",
    ]
    assert soil == [
        "soil",
        "hsg",
        "--depth=0-5cm",
        *AREA_ARGUMENTS,
        f"--output-dir={out / 'soil'}",
        "--json",
    ]


def test_the_plan_of_every_product_is_read_before_anything_is_fetched(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    _fetch(tmp_path / "data")

    calls = fake.calls()
    first_download = min(i for i, c in enumerate(calls) if c in fake.downloads())
    plans = [i for i, c in enumerate(calls) if c in fake.plans()]
    assert len(plans) == 3 and max(plans) < first_download


def test_a_geometry_goes_to_kartograf_as_an_absolute_path_with_its_layer(
    tmp_path: Path, fake: FakeKartograf, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "area.gpkg").write_bytes(b"x")

    document = download_terrain(
        geometry="area.gpkg", layer="catchment", products=["soil"], output_dir="d"
    )

    assert isinstance(document, TerrainDocument)
    (call,) = fake.downloads()
    assert (
        f"--geometry={tmp_path / 'area.gpkg'}" in call and "--layer=catchment" in call
    )
    assert document.area == {
        "source": "geometry",
        "path": str(tmp_path / "area.gpkg"),
        "layer": "catchment",
    }
    assert [p["product"] for p in document.products] == ["soil"]
    assert not (tmp_path / "d" / "elevation").exists()


def test_products_are_fetched_in_the_fixed_order_whatever_the_order_given(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    document = _fetch(tmp_path / "d", products=["soil", "elevation", "soil"])

    assert [p["product"] for p in document.products] == ["elevation", "soil"]


def test_an_existing_file_fails_the_whole_call_before_any_product_is_fetched(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    out = tmp_path / "data"
    existing = out / "soil" / "hsg_361500_504000_363000_505500.tif"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"mine")

    with pytest.raises(ConflictError) as caught:
        _fetch(out)

    assert caught.value.details["reason"] == "output_exists"
    assert caught.value.details["paths"] == [str(existing.resolve())]
    assert "--force" in str(caught.value.hint)
    assert fake.downloads() == []
    assert not (out / "elevation").exists() and existing.read_bytes() == b"mine"


def test_force_replaces_what_exists_and_nothing_else(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    out = tmp_path / "data"
    existing = out / "soil" / "hsg_361500_504000_363000_505500.tif"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"mine")
    other = out / "soil" / "notes.txt"
    other.write_text("keep", encoding="utf-8")

    document = _fetch(out, force=True)

    statuses = {Path(f["path"]).parent.name: f["status"] for f in document.files}
    assert statuses == {
        "elevation": "written",
        "landcover": "written",
        "soil": "replaced",
    }
    assert other.read_text(encoding="utf-8") == "keep"
    assert all("--force" in call for call in fake.downloads())


def test_check_returns_the_plan_of_every_product_and_fetches_nothing(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    out = tmp_path / "data"

    plan = download_terrain(
        bbox=BBOX,
        crs="EPSG:2180",
        output_dir=out,
        check=True,
        products=["elevation", "soil"],
    )

    assert isinstance(plan, PlanDocument)
    body = plan.to_dict()
    assert [(t["name"].split("/")[0], t["action"]) for t in body["targets"]] == [
        ("elevation", "write"),
        ("soil", "write"),
    ]
    assert body["conflicts"] == [] and body["blockers"] == []
    assert body["output_dir"] == str(out.resolve()) and body["force"] is False
    assert len(body["steps"]) == 2 and "elevation:" in body["steps"][0]
    assert fake.downloads() == [] and not out.exists()


def test_a_plan_with_a_conflict_is_a_result_and_the_run_is_the_error(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    out = tmp_path / "data"
    (out / "elevation").mkdir(parents=True)
    taken = out / "elevation" / "361500_504000_363000_505500.tif"
    taken.write_bytes(b"mine")

    plan = check_command(
        "terrain download",
        bbox=BBOX,
        crs="EPSG:2180",
        products=["elevation"],
        output_dir=out,
    )

    assert isinstance(plan, PlanDocument)
    assert plan.targets[0]["action"] == "conflict"
    assert plan.targets[0]["reason"] == "output_exists"
    assert plan.targets[0]["name"] == "elevation/" + taken.name
    assert plan.conflicts == ["output_exists"]


def test_a_plan_with_force_says_replace(tmp_path: Path, fake: FakeKartograf) -> None:
    out = tmp_path / "data"
    (out / "elevation").mkdir(parents=True)
    (out / "elevation" / "361500_504000_363000_505500.tif").write_bytes(b"mine")

    plan = download_terrain(
        bbox=BBOX,
        crs="EPSG:2180",
        products=["elevation"],
        output_dir=out,
        force=True,
        check=True,
    )

    assert isinstance(plan, PlanDocument)
    assert [t["action"] for t in plan.targets] == ["replace"] and plan.conflicts == []


def test_a_directory_inside_a_store_is_refused_without_asking_kartograf_for_data(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / STORE_MARKERS[0]).write_text("{}", encoding="utf-8")

    with pytest.raises(ConflictError) as caught:
        _fetch(store / "data")
    plan = download_terrain(
        bbox=BBOX, crs="EPSG:2180", output_dir=store / "data", check=True
    )

    assert caught.value.details["reason"] == "output_in_store"
    assert isinstance(plan, PlanDocument) and plan.conflicts == ["output_in_store"]
    assert fake.plans() == [] and fake.downloads() == []


def test_a_kartograf_without_plain_files_is_refused_and_nothing_is_fetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = install(tmp_path, monkeypatch, plain=False)
    use(monkeypatch, program)

    with pytest.raises(MissingDependencyError) as caught:
        _fetch(tmp_path / "d")
    plan = download_terrain(
        bbox=BBOX, crs="EPSG:2180", output_dir=tmp_path / "d", check=True
    )

    assert caught.value.details["reason"] == "engine_incompatible"
    assert "versioned store" in str(caught.value)
    assert "data-output convention" in str(caught.value.hint)
    assert isinstance(plan, PlanDocument)
    assert [b["reason"] for b in plan.blockers] == ["engine_incompatible"]
    assert plan.targets == [] and len(plan.steps) == 3
    assert program.plans() == [] and program.downloads() == []
    assert not (tmp_path / "d").exists()


def test_a_missing_kartograf_is_missing_and_a_plan_names_the_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = EngineStatus(
        "kartograf",
        False,
        None,
        None,
        None,
        "the kartograf command was not found",
        "Install it.",
    )
    monkeypatch.setattr(
        "hydraulik.operations.terrain.find_kartograf", lambda settings: (status, None)
    )

    with pytest.raises(MissingDependencyError) as caught:
        _fetch(tmp_path / "d")
    plan = download_terrain(
        bbox=BBOX, crs="EPSG:2180", output_dir=tmp_path / "d", check=True
    )

    assert caught.value.details["reason"] == "engine_missing"
    assert caught.value.hint == "Install it."
    assert isinstance(plan, PlanDocument)
    assert plan.blockers == [
        {
            "reason": "engine_missing",
            "message": "the kartograf command was not found",
            "hint": "Install it.",
        }
    ]


def test_a_product_that_fails_after_another_succeeded_is_a_partial_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = {
        "code": "source_unavailable",
        "message": "GUGiK did not answer",
        "details": {"reason": "download_failed"},
        "hint": "Try again later.",
    }
    program = install(tmp_path, monkeypatch, errors={"landcover download": error})
    use(monkeypatch, program)

    document = _fetch(tmp_path / "d")

    assert document.status == "partial"
    statuses = {p["product"]: p["status"] for p in document.products}
    assert statuses == {"elevation": "ok", "landcover": "failed", "soil": "ok"}
    failed = [i for i in document.items if i["status"] == "failed"]
    assert failed == [
        {
            "id": "landcover",
            "status": "failed",
            "code": "source_unavailable",
            "message": "GUGiK did not answer",
            "reason": "download_failed",
        }
    ]
    assert {Path(f["path"]).parent.name for f in document.files} == {
        "elevation",
        "soil",
    }
    assert [s["product"] for s in document.sources] == ["elevation", "soil"]


def test_a_partial_outcome_of_kartograf_keeps_its_unit_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = install(
        tmp_path,
        monkeypatch,
        names={"landcover download": ["1465.gpkg", "3064.gpkg"]},
        outcomes={"landcover download": "partial"},
    )
    use(monkeypatch, program)

    document = _fetch(tmp_path / "d", products=["landcover"])

    assert document.status == "partial"
    assert [(i["id"], i["status"]) for i in document.items] == [
        ("landcover/1465", "ok"),
        ("landcover/3064", "failed"),
    ]
    assert document.products[0]["status"] == "partial"
    assert len(document.files) == 1


def test_every_product_of_several_failing_is_a_failed_result_with_the_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = {"code": "no_data", "message": "nothing there", "exit_code": 14}
    program = install(
        tmp_path,
        monkeypatch,
        errors={"elevation download": error, "soil hsg": error},
    )
    use(monkeypatch, program)

    document = _fetch(tmp_path / "d", products=["elevation", "soil"])

    assert document.status == "failed" and document.files == []
    assert [(i["id"], i["code"]) for i in document.items] == [
        ("elevation", "no_data"),
        ("soil", "no_data"),
    ]


def test_the_only_product_failing_raises_the_error_of_kartograf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = {"code": "source_unavailable", "message": "GUGiK did not answer"}
    program = install(tmp_path, monkeypatch, errors={"soil hsg": error})
    use(monkeypatch, program)

    with pytest.raises(SourceUnavailableError, match="GUGiK did not answer"):
        _fetch(tmp_path / "d", products=["soil"])


def test_the_exit_codes_and_the_envelope_of_the_cli_follow_the_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    error = {"code": "source_unavailable", "message": "GUGiK did not answer"}
    program = install(tmp_path, monkeypatch, errors={"landcover download": error})
    use(monkeypatch, program)
    arguments = ["terrain", "download", "--bbox", "361500,504000,363000,505500"]
    arguments += ["--crs", "EPSG:2180", "--output-dir", str(tmp_path / "d"), "--json"]

    code = main(arguments)
    envelope = json.loads(capsys.readouterr().out)

    assert code == 10 and envelope["status"] == "partial"
    assert envelope["command"] == "terrain download" and envelope["check"] is False
    assert envelope["result"]["schema"] == "hydraulik-terrain/1"
    assert [i["status"] for i in envelope["items"]] == ["ok", "failed", "ok"]
    assert envelope["items"][1]["code"] == "source_unavailable"


def test_the_cli_plan_and_a_clear_refusal_for_a_kartograf_without_plain_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    program = install(tmp_path, monkeypatch, plain=False)
    use(monkeypatch, program)
    arguments = ["terrain", "download", "--bbox", "361500,504000,363000,505500"]
    arguments += ["--crs", "EPSG:2180", "-o", str(tmp_path / "d"), "--json"]

    code = main(arguments)
    err = capsys.readouterr().err.strip().splitlines()[-1]

    document = json.loads(err)
    assert code == 6 and document["code"] == "missing_dependency"
    assert document["details"]["reason"] == "engine_incompatible"
    assert "path_role output" in document["message"]


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({}, "missing_option"),
        ({"bbox": BBOX, "geometry": "a.gpkg", "crs": "EPSG:2180"}, "exclusive_options"),
        ({"bbox": BBOX}, "missing_option"),
        ({"bbox": BBOX[:3], "crs": "EPSG:2180"}, "invalid_bbox"),
        ({"bbox": [2.0, 2.0, 1.0, 3.0], "crs": "EPSG:2180"}, "invalid_bbox"),
        ({"bbox": BBOX, "crs": "EPSG:2180", "layer": "x"}, "option_not_applicable"),
        ({"geometry": "a.gpkg", "crs": "EPSG:2180"}, "option_not_applicable"),
        ({"bbox": BBOX, "crs": "EPSG:2180", "products": ["wind"]}, "not_allowed"),
        ({"bbox": BBOX, "crs": "EPSG:2180", "products": []}, "missing_option"),
        ({"bbox": BBOX, "crs": "EPSG:32633"}, "not_allowed"),
    ],
)
def test_options_that_cannot_work_are_refused_before_anything_is_fetched(
    tmp_path: Path,
    fake: FakeKartograf,
    monkeypatch: pytest.MonkeyPatch,
    options: dict[str, Any],
    reason: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.gpkg").write_bytes(b"x")

    with pytest.raises(InvalidInputError) as caught:
        download_terrain(output_dir=tmp_path / "d", **options)

    assert caught.value.details["reason"] == reason
    assert fake.downloads() == [] and fake.plans() == []


def test_a_geometry_that_does_not_exist_is_not_found(
    tmp_path: Path, fake: FakeKartograf
) -> None:
    with pytest.raises(NotFoundError) as caught:
        download_terrain(geometry=tmp_path / "gone.gpkg", output_dir=tmp_path / "d")

    assert caught.value.details["reason"] == "path_missing"


def test_the_timeout_of_a_call_is_the_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = install(tmp_path, monkeypatch, hang=["elevation download"])
    use(monkeypatch, program)
    monkeypatch.setenv("HYDRAULIK_KARTOGRAF_TIMEOUT_S", "1")

    with pytest.raises(SourceUnavailableError) as caught:
        _fetch(tmp_path / "d")

    assert caught.value.details["reason"] == "kartograf_timeout"
    assert caught.value.details["timeout_s"] == 1.0
    assert program.downloads() == []


def test_a_plan_that_cannot_be_read_stops_the_call_before_any_product_is_fetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = {"code": "source_unavailable", "message": "the sheet index is down"}
    program = install(tmp_path, monkeypatch, plan_errors={"soil hsg": error})
    use(monkeypatch, program)

    with pytest.raises(SourceUnavailableError, match="the sheet index is down"):
        _fetch(tmp_path / "d")

    assert program.downloads() == [] and not (tmp_path / "d").exists()
