"""Behaviour of the exception classes and of ``error_document``."""

import pytest

from hydraulik.exceptions import (
    ConflictError,
    EngineError,
    HydraulikError,
    InvalidInputError,
    NotFoundError,
    error_document,
)


def test_details_are_an_independent_copy() -> None:
    paths = ["a.nc"]
    exc = ConflictError("exists", details={"paths": paths})

    paths.append("b.nc")

    assert exc.details["paths"] == ["a.nc"]


def test_reason_is_stored_in_details() -> None:
    exc = ConflictError("exists", reason="output_exists", details={"paths": []})

    assert exc.details == {"paths": [], "reason": "output_exists"}


def test_unknown_code_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown error code"):
        HydraulikError("x", code="no_such_code")  # type: ignore[arg-type]


def test_rest_only_codes_are_refused_because_the_cli_has_no_exit_code_for_them() -> (
    None
):
    with pytest.raises(ValueError, match="Unknown error code"):
        HydraulikError("x", code="rate_limited")  # type: ignore[arg-type]


def test_exit_code_comes_from_the_registry() -> None:
    assert NotFoundError("x").exit_code == 3
    assert HydraulikError("x", code="no_data").exit_code == 14


def test_engine_error_defaults_to_the_engine_failed_reason() -> None:
    assert EngineError("exit 1").details == {"reason": "engine_failed"}
    assert EngineError("x", reason="timeout").details == {"reason": "timeout"}


def test_invalid_input_error_is_still_a_value_error() -> None:
    assert isinstance(InvalidInputError("x"), ValueError)


def test_error_document_of_a_bug_is_an_internal_error_with_a_hint() -> None:
    document = error_document(RuntimeError("boom"), command="engines check")

    assert document["code"] == "internal_error"
    assert document["details"] == {"exception": "RuntimeError"}
    assert "hint" in document
    assert document["command"] == "engines check"


def test_error_document_maps_a_missing_file_to_not_found_with_the_path() -> None:
    document = error_document(FileNotFoundError(2, "No such file", "dem.tif"))

    assert document["code"] == "not_found"
    assert document["details"]["path"] == "dem.tif"
    assert document["details"]["reason"] == "path_missing"


def test_error_document_title_follows_the_language_and_message_stays_english() -> None:
    en = error_document(NotFoundError("No such file"), lang="en")
    pl = error_document(NotFoundError("No such file"), lang="pl")

    assert en["title"] == "Not found"
    assert pl["title"] != en["title"]
    assert pl["message"] == en["message"]


def test_error_document_serialises_paths_and_sets_in_details() -> None:
    from pathlib import Path

    document = error_document(
        InvalidInputError("x", details={"path": Path("a/b"), "allowed": {"b", "a"}})
    )

    assert document["details"] == {"path": str(Path("a/b")), "allowed": ["a", "b"]}


def test_error_document_refuses_an_unknown_language() -> None:
    with pytest.raises(ValueError, match="Unknown language"):
        error_document(RuntimeError("x"), lang="de")  # type: ignore[arg-type]


def test_empty_message_falls_back_to_the_registry_title() -> None:
    assert error_document(InvalidInputError())["message"] == "Invalid input"
