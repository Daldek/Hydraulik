"""The Kartograf adapter against a fake program that answers by the convention."""

import hashlib
from pathlib import Path

import pytest

from hydraulik.data.kartograf import (
    KartografCli,
    parse_command_info,
    plain_output_problem,
    plan_targets,
)
from hydraulik.exceptions import (
    CancelledError,
    ConflictError,
    MissingDependencyError,
    NoDataError,
    SourceUnavailableError,
)

from ..fake_kartograf import FakeKartograf, install

AREA = {"bbox": [361500.0, 504000.0, 363000.0, 505500.0], "bbox_crs": "EPSG:2180"}
ELEVATION = {"product": "nmt", "country": "pl", "cutout": True, **AREA}


def _cli(fake: FakeKartograf, *, timeout_s: float = 60.0) -> KartografCli:
    return KartografCli(fake.words, timeout_s=timeout_s)


def test_the_schema_tells_that_output_dir_is_a_plain_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch)

    info = _cli(fake).schema("elevation download")

    assert info.options["output_dir"].path_role == "output"
    assert info.options["output_dir"].flag == "--output-dir"
    assert info.options["product"].allowed == ("nmt", "nmpt")
    assert plain_output_problem(info) is None


def test_an_output_dir_that_is_a_store_root_is_refused_before_anything_is_fetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, plain=False)
    cli = _cli(fake)

    problem = plain_output_problem(cli.schema("elevation download"))
    with pytest.raises(MissingDependencyError) as caught:
        cli.run("elevation download", {**ELEVATION, "output_dir": str(tmp_path / "d")})

    assert problem is not None and "versioned store" in problem
    assert caught.value.details["reason"] == "engine_incompatible"
    assert "versioned store" in str(caught.value)
    assert fake.plans() == [] and fake.downloads() == []
    assert not (tmp_path / "d").exists()


def test_only_options_that_the_schema_declares_are_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, no_check=True)
    cli = _cli(fake)
    target = str(tmp_path / "d")

    with pytest.raises(MissingDependencyError) as no_option:
        cli.run("soil hsg", {"depth": "0-5cm", "wat": 1, "output_dir": target})
    with pytest.raises(MissingDependencyError) as no_plan:
        cli.run("soil hsg", {"depth": "0-5cm", "output_dir": target}, check=True)

    assert no_option.value.details["option"] == "wat"
    assert "--wat" in str(no_option.value)
    assert no_plan.value.details["option"] == "check"
    assert fake.plans() == [] and fake.downloads() == []


def test_a_value_outside_the_enum_of_the_schema_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch)

    with pytest.raises(MissingDependencyError) as caught:
        _cli(fake).run(
            "elevation download",
            {"product": "contours", "output_dir": str(tmp_path / "d")},
        )

    assert caught.value.details["option"] == "product"
    assert "nmt, nmpt" in str(caught.value) and "contours" in str(caught.value)
    assert fake.downloads() == []


def test_arguments_are_flags_with_equals_lists_with_commas_and_bare_booleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch)
    options = {
        "product": "nmt",
        "bbox": [-447000.0, -1100000.0, -437000.0, -1090000.5],
        "bbox_crs": "EPSG:5514",
        "cutout": True,
        "force": False,
        "layer": None,
        "output_dir": str(tmp_path / "d"),
    }

    _cli(fake).run("elevation download", options)

    (call,) = fake.downloads()
    assert call == [
        "elevation",
        "download",
        "--product=nmt",
        "--bbox=-447000.0,-1100000.0,-437000.0,-1090000.5",
        "--bbox-crs=EPSG:5514",
        "--cutout",
        f"--output-dir={tmp_path / 'd'}",
        "--json",
    ]


def test_a_run_reports_files_with_their_hash_skipped_units_items_and_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skipped = [{"id": "N-34-1", "reason": "skipped_incomplete", "message": "no flight"}]
    fake = install(
        tmp_path,
        monkeypatch,
        skipped={"elevation download": skipped},
    )
    target = tmp_path / "d"

    run = _cli(fake).run("elevation download", {**ELEVATION, "output_dir": str(target)})

    (entry,) = run.files
    written = Path(entry["path"])
    assert written.parent == target and written.read_bytes()
    assert entry["size_bytes"] == written.stat().st_size
    assert entry["sha256"] == hashlib.sha256(written.read_bytes()).hexdigest()
    assert entry["status"] == "written"
    assert run.status == "ok" and run.skipped == tuple(skipped)
    assert [item["status"] for item in run.items] == ["ok"]
    assert run.notices[0]["code"] == "fake_notice"
    assert run.targets == ()


def test_a_second_run_without_force_conflicts_and_with_force_replaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch)
    options = {**ELEVATION, "output_dir": str(tmp_path / "d")}
    cli = _cli(fake)
    first = cli.run("elevation download", options)

    with pytest.raises(ConflictError) as caught:
        cli.run("elevation download", options)
    again = cli.run("elevation download", {**options, "force": True})

    assert caught.value.details["reason"] == "output_exists"
    assert caught.value.details["paths"] == [first.files[0]["path"]]
    assert "--force" in str(caught.value.hint)
    assert [f["status"] for f in again.files] == ["replaced"]


def test_a_plan_lists_every_target_with_its_action_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(
        tmp_path,
        monkeypatch,
        names={"landcover download": ["1465.gpkg", "3064.gpkg"]},
    )
    options = {"product": "bdot10k", **AREA, "output_dir": str(tmp_path / "d")}
    cli = _cli(fake)
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "3064.gpkg").write_bytes(b"old")

    plan = cli.run("landcover download", options, check=True)
    forced = cli.run("landcover download", {**options, "force": True}, check=True)

    assert [(Path(t["path"]).name, t["action"]) for t in plan.targets] == [
        ("1465.gpkg", "write"),
        ("3064.gpkg", "conflict"),
    ]
    assert plan.targets[1]["reason"] == "output_exists"
    assert [t["action"] for t in forced.targets] == ["write", "replace"]
    assert plan.files == () and fake.downloads() == []
    assert sorted(p.name for p in (tmp_path / "d").iterdir()) == ["3064.gpkg"]


def test_a_partial_and_a_failed_outcome_are_relayed_with_the_failed_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(
        tmp_path,
        monkeypatch,
        names={"landcover download": ["1465.gpkg", "3064.gpkg"]},
        outcomes={"landcover download": "partial", "soil hsg": "failed"},
    )
    cli = _cli(fake)
    land = {"product": "bdot10k", **AREA, "output_dir": str(tmp_path / "land")}
    soil = {"depth": "0-5cm", **AREA, "output_dir": str(tmp_path / "soil")}

    partial = cli.run("landcover download", land)
    failed = cli.run("soil hsg", soil)

    assert partial.status == "partial" and len(partial.files) == 1
    assert [(i["id"], i["status"]) for i in partial.items] == [
        ("1465", "ok"),
        ("3064", "failed"),
    ]
    assert partial.items[1]["code"] == "source_unavailable"
    assert failed.status == "failed" and failed.files == ()


def test_an_error_document_comes_back_as_the_same_class_with_its_hint_and_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = {
        "code": "no_data",
        "message": "no sheet has a full flight",
        "details": {"reason": "skipped_incomplete", "option": "bbox"},
        "hint": "Try another area.",
    }
    fake = install(tmp_path, monkeypatch, errors={"elevation download": error})

    with pytest.raises(NoDataError) as caught:
        _cli(fake).run(
            "elevation download", {**ELEVATION, "output_dir": str(tmp_path / "d")}
        )

    assert str(caught.value) == "no sheet has a full flight"
    assert caught.value.hint == "Try another area."
    assert caught.value.details == {
        "reason": "skipped_incomplete",
        "option": "bbox",
        "engine": "kartograf",
        "command": "elevation download",
    }


def test_a_program_that_dies_without_an_error_document_is_source_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, crash={"soil hsg": 3})

    with pytest.raises(SourceUnavailableError) as caught:
        _cli(fake).run("soil hsg", {"depth": "0-5cm", "output_dir": str(tmp_path)})

    assert caught.value.details["reason"] == "kartograf_failed"
    assert caught.value.details["returncode"] == 3
    assert "the fake crashed" in caught.value.details["stderr_tail"][-1]


def test_exit_code_130_is_a_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, crash={"soil hsg": 130})

    with pytest.raises(CancelledError):
        _cli(fake).run("soil hsg", {"depth": "0-5cm", "output_dir": str(tmp_path)})


def test_output_that_is_not_a_result_document_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, garbage=["soil hsg"])

    with pytest.raises(SourceUnavailableError) as caught:
        _cli(fake).run("soil hsg", {"depth": "0-5cm", "output_dir": str(tmp_path)})

    assert caught.value.details["reason"] == "kartograf_output"
    assert caught.value.details["stdout_head"].startswith("this is not json")


def test_a_schema_that_is_not_json_makes_the_kartograf_incompatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, garbage=["elevation download"])

    with pytest.raises(SourceUnavailableError) as caught:
        _cli(fake).schema("elevation download")

    assert caught.value.details["reason"] == "kartograf_output"


def test_a_command_that_the_kartograf_does_not_know_is_incompatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch)

    with pytest.raises(MissingDependencyError) as caught:
        _cli(fake).schema("soil download")

    assert caught.value.details["reason"] == "engine_incompatible"


def test_a_call_that_takes_too_long_is_stopped_with_the_end_of_its_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, hang=["soil hsg"])
    cli = _cli(fake, timeout_s=1.0)
    cli.schema("soil hsg")  # the schema call is not subject to the timeout of a fetch

    with pytest.raises(SourceUnavailableError) as caught:
        cli.run("soil hsg", {"depth": "0-5cm", "output_dir": str(tmp_path / "d")})

    assert caught.value.details["reason"] == "kartograf_timeout"
    assert caught.value.details["timeout_s"] == 1.0
    assert "kartograf.timeout_s" in str(caught.value.hint)


def test_a_program_that_cannot_be_started_is_a_missing_dependency(
    tmp_path: Path,
) -> None:
    cli = KartografCli((str(tmp_path / "no-such-kartograf"),), timeout_s=5.0)

    with pytest.raises(MissingDependencyError) as caught:
        cli.schema("soil hsg")

    assert caught.value.details["reason"] == "engine_unavailable"
    assert cli.version() is None


def test_the_version_is_the_first_line_of_the_version_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(tmp_path, monkeypatch, version="kartograf 1.2.3\nsecond line")

    assert _cli(fake).version() == "kartograf 1.2.3"


def test_plan_targets_are_found_wherever_a_plan_keeps_them() -> None:
    plan = {
        "schema": "kartograf-plan/1",
        "items": [
            {"path": "/d/a.tif", "action": "write"},
            {"path": "/d/b.tif", "action": "conflict", "reason": "output_exists"},
            {"path": "/d/c.tif", "status": "current"},
            {"action": "write"},
        ],
        "extra": {"actions": [{"path": "/d/e.tif", "action": "replace"}]},
        "odd": [{"path": "/d/f.tif", "action": "delete"}],
    }

    assert plan_targets(plan) == [
        {"path": "/d/a.tif", "action": "write"},
        {"path": "/d/b.tif", "action": "conflict", "reason": "output_exists"},
        {"path": "/d/e.tif", "action": "replace"},
    ]
    assert plan_targets({"schema": "kartograf-plan/1"}) == []


def test_a_schema_document_that_lacks_the_command_is_incompatible() -> None:
    document = {"result": {"commands": [{"name": "other", "options": []}]}}

    with pytest.raises(MissingDependencyError):
        parse_command_info(document, "elevation download")
