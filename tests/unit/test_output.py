"""Plain-mode writing: preflight, staging, replacement and cleanup (DEV §19)."""

import hashlib
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from hydraulik.exceptions import (
    ConflictError,
    InvalidInputError,
    OutputError,
    TerminatedError,
)
from hydraulik.output import (
    STAGING_DIR,
    STORE_MARKERS,
    Writer,
    plan_directory,
    plan_file,
    remove_stale_staging,
)


def _stage(writer: Writer, name: str, text: str) -> None:
    writer.staged_path(name).write_text(text, encoding="utf-8")


def test_plan_of_an_empty_directory_writes_every_target(tmp_path: Path) -> None:
    plan = plan_directory(tmp_path / "out", ["a.json", "sub/b.tif"])

    assert [(t.name, t.action) for t in plan.targets] == [
        ("a.json", "write"),
        ("sub/b.tif", "write"),
    ]
    assert plan.conflicts == ()
    assert not (tmp_path / "out").exists()  # planning has no effect


def test_existing_target_is_a_conflict_without_force_and_a_replace_with_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.json").write_text("old", encoding="utf-8")

    without = plan_directory(tmp_path, ["a.json", "b.json"])
    with_force = plan_directory(tmp_path, ["a.json", "b.json"], force=True)

    assert [t.action for t in without.targets] == ["conflict", "write"]
    assert without.conflicts == ("output_exists",)
    assert [t.action for t in with_force.targets] == ["replace", "write"]
    assert with_force.conflicts == ()


def test_conflict_error_lists_every_existing_path(tmp_path: Path) -> None:
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text("old", encoding="utf-8")
    plan = plan_directory(tmp_path, ["a.json", "b.json", "c.json"])

    with pytest.raises(ConflictError) as caught:
        plan.raise_on_conflict()

    assert caught.value.details["reason"] == "output_exists"
    assert sorted(caught.value.details["paths"]) == [
        str(tmp_path.resolve() / "a.json"),
        str(tmp_path.resolve() / "b.json"),
    ]


def test_duplicate_names_are_a_conflict_before_existing_files_are_looked_at(
    tmp_path: Path,
) -> None:
    (tmp_path / "x.json").write_text("old", encoding="utf-8")
    plan = plan_directory(tmp_path, ["x.json", "y.json", "y.json", "./y.json"])

    assert plan.duplicates == ("y.json",)
    with pytest.raises(ConflictError) as caught:
        plan.raise_on_conflict()
    assert caught.value.details["reason"] == "duplicate_output_name"
    assert caught.value.details["paths"] == [str(tmp_path.resolve() / "y.json")]


def test_a_plan_with_conflicts_is_still_a_plan(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("old", encoding="utf-8")

    document = plan_directory(tmp_path, ["a.json"]).to_dict()

    assert document["schema"] == "hydraulik-plan/1"
    assert document["conflicts"] == ["output_exists"]
    assert document["targets"][0]["action"] == "conflict"


@pytest.mark.parametrize("marker", STORE_MARKERS)
def test_directory_inside_a_store_is_a_conflict(tmp_path: Path, marker: str) -> None:
    store = tmp_path / "store"
    (store / "work").mkdir(parents=True)
    (store / marker).write_text("{}", encoding="utf-8")

    plan = plan_directory(store / "work", ["a.json"])

    assert plan.conflicts == ("output_in_store",)
    with pytest.raises(ConflictError) as caught:
        plan.raise_on_conflict()
    assert caught.value.details["reason"] == "output_in_store"
    assert caught.value.details["paths"] == [str(store.resolve() / marker)]


def test_a_subdirectory_that_holds_a_store_marker_is_a_conflict(
    tmp_path: Path,
) -> None:
    (tmp_path / "inner").mkdir()
    (tmp_path / "inner" / STORE_MARKERS[0]).write_text("{}", encoding="utf-8")

    plan = plan_directory(tmp_path, ["inner/a.json"])

    assert plan.conflicts == ("output_in_store",)


@pytest.mark.parametrize(
    "name",
    ["", "../a.json", "/etc/passwd", "a/../../b", "a\x00b", f"{STAGING_DIR}/x"],
)
def test_unsafe_names_are_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(InvalidInputError) as caught:
        plan_directory(tmp_path, [name])

    assert caught.value.details["reason"] == "unsafe_output_name"


def test_output_dir_that_is_a_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidInputError) as caught:
        plan_directory(tmp_path / "f", ["a"])

    assert caught.value.details["reason"] == "not_a_directory"


def test_plan_file_has_one_target_named_by_the_caller(tmp_path: Path) -> None:
    plan = plan_file(tmp_path / "rain.csv")

    assert [t.name for t in plan.targets] == ["rain.csv"]
    assert plan.directory == tmp_path.resolve()


def test_plan_file_refuses_a_directory(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError) as caught:
        plan_file(tmp_path)

    assert caught.value.details["reason"] == "not_a_file"


def test_writer_creates_the_directory_and_moves_the_files_into_place(
    tmp_path: Path,
) -> None:
    out = tmp_path / "new" / "dir"
    with Writer(plan_directory(out, ["a.txt", "sub/b.txt"])) as writer:
        _stage(writer, "a.txt", "alpha")
        _stage(writer, "sub/b.txt", "beta")
        files = writer.commit()

    assert (out / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (out / "sub" / "b.txt").read_text(encoding="utf-8") == "beta"
    assert [f.status for f in files] == ["written", "written"]
    assert files[0].size_bytes == 5
    assert files[0].sha256 == hashlib.sha256(b"alpha").hexdigest()
    assert files[0].to_dict()["path"] == str(out.resolve() / "a.txt")


def test_nothing_but_the_data_files_is_left_behind(tmp_path: Path) -> None:
    with Writer(plan_directory(tmp_path, ["a.txt"])) as writer:
        _stage(writer, "a.txt", "x")
        writer.commit()

    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt"]


def test_force_replaces_the_target_and_touches_no_other_file(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("old", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")

    with Writer(plan_directory(tmp_path, ["a.txt"], force=True)) as writer:
        _stage(writer, "a.txt", "new")
        files = writer.commit()

    assert files[0].status == "replaced"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "new"
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_writer_refuses_a_plan_with_a_conflict_before_creating_anything(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.txt").write_text("old", encoding="utf-8")
    out = tmp_path / "out"

    with pytest.raises(ConflictError):
        Writer(plan_directory(tmp_path, ["a.txt"])).__enter__()

    assert not out.exists()
    assert not (tmp_path / STAGING_DIR).exists()


def test_staging_is_removed_when_the_block_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), Writer(plan_directory(tmp_path, ["a.txt"])) as w:
        _stage(w, "a.txt", "partial")
        raise RuntimeError("engine crashed")

    assert not (tmp_path / "a.txt").exists()
    assert not (tmp_path / STAGING_DIR).exists()


def test_staging_is_removed_on_keyboard_interrupt(tmp_path: Path) -> None:
    with pytest.raises(KeyboardInterrupt), Writer(plan_directory(tmp_path, ["a"])):
        raise KeyboardInterrupt

    assert not (tmp_path / STAGING_DIR).exists()


def test_the_sigterm_handler_unwinds_the_block_with_a_terminated_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(TerminatedError) as caught:
        Writer._on_terminate(signal.SIGTERM, None)

    assert caught.value.code == "terminated"
    assert caught.value.exit_code == 143


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM kills the process")
def test_a_real_sigterm_removes_the_staging_directory(tmp_path: Path) -> None:
    with (
        pytest.raises(TerminatedError),
        Writer(plan_directory(tmp_path, ["a.txt"])) as writer,
    ):
        _stage(writer, "a.txt", "partial")
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.5)  # the handler runs between bytecodes

    assert not (tmp_path / STAGING_DIR).exists()
    assert signal.getsignal(signal.SIGTERM) is not Writer._on_terminate


def test_missing_output_of_the_run_is_an_error_naming_the_file(tmp_path: Path) -> None:
    with (
        pytest.raises(OutputError) as caught,
        Writer(plan_directory(tmp_path, ["a.txt"])) as writer,
    ):
        writer.commit()

    assert caught.value.details["reason"] == "output_missing"
    assert not (tmp_path / "a.txt").exists()


def test_declared_size_is_checked_in_staging(tmp_path: Path) -> None:
    with (
        pytest.raises(OutputError) as caught,
        Writer(plan_directory(tmp_path, ["a.txt"])) as writer,
    ):
        _stage(writer, "a.txt", "abc")
        writer.commit({"a.txt": 10})

    assert caught.value.details["reason"] == "output_size_mismatch"
    assert not (tmp_path / "a.txt").exists()


def test_target_that_appears_during_the_run_is_not_overwritten(tmp_path: Path) -> None:
    with (
        pytest.raises(ConflictError),
        Writer(plan_directory(tmp_path, ["a.txt"])) as writer,
    ):
        _stage(writer, "a.txt", "mine")
        (tmp_path / "a.txt").write_text("theirs", encoding="utf-8")
        writer.commit()

    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "theirs"


def test_unplanned_file_cannot_be_staged(tmp_path: Path) -> None:
    with (
        Writer(plan_directory(tmp_path, ["a.txt"])) as writer,
        pytest.raises(InvalidInputError) as caught,
    ):
        writer.staged_path("b.txt")

    assert caught.value.details["reason"] == "unplanned_output"


def test_stale_staging_is_removed_on_the_next_run_and_fresh_staging_is_kept(
    tmp_path: Path,
) -> None:
    stale = tmp_path / STAGING_DIR / "old_1_aaaa"
    fresh = tmp_path / STAGING_DIR / "other_2_bbbb"
    stale.mkdir(parents=True)
    fresh.mkdir(parents=True)
    two_days_ago = time.time() - 48 * 3600
    os.utime(stale, (two_days_ago, two_days_ago))

    with Writer(plan_directory(tmp_path, ["a.txt"])) as writer:
        _stage(writer, "a.txt", "x")
        writer.commit()

    assert not stale.exists()
    assert fresh.exists()


def test_remove_stale_staging_reports_what_it_removed(tmp_path: Path) -> None:
    stale = tmp_path / STAGING_DIR / "old_1_aaaa"
    stale.mkdir(parents=True)

    removed = remove_stale_staging(tmp_path, now=time.time() + 25 * 3600)

    assert removed == [stale]


def test_staging_lives_inside_the_output_directory(tmp_path: Path) -> None:
    with Writer(plan_directory(tmp_path, ["a.txt"])) as writer:
        assert writer.staging.parent == tmp_path.resolve() / STAGING_DIR
        assert len(writer.staging.name.split("_")) >= 3
